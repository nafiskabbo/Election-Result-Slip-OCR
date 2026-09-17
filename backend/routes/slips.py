import os
import time
import uuid
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from backend.config import DATA_DIR, PRODUCTION_RAPIDOCR_MODEL, STORAGE_DIR, ensure_dirs
from backend.database import get_db_connection
from backend.grouping_engine import GroupingEngine
from backend.image_enhancer import ImageEnhancer
from backend.models import (
    SlipSummaryResponse, SlipDetailResponse, SlipFieldUpdate,
    PartyResultUpdate, SlipStatusAction, SlipStatusEnum
)
from backend.ocr_engine import LOW_VOTE_CONFIDENCE, OCREngine
from backend.page_pipeline import persist_enhanced_page
from backend.process_timing import iso_utc, make_event, ndjson_stream
from backend.validation_engine import ValidationEngine
from backend.audit_service import AuditService
from backend.routes.auth import ACTIVE_USER_STATE

router = APIRouter(prefix="/api/slips", tags=["Slips Management & Verification"])

validation_engine = ValidationEngine()
audit_service = AuditService()
grouping_engine = GroupingEngine()
enhancer = ImageEnhancer()
ocr_engine = OCREngine(rapidocr_model=PRODUCTION_RAPIDOCR_MODEL)


def _vote_related_flag(row) -> bool:
    if row.get("is_vote_related") is False:
        return False
    ref = str(row.get("slip_reference") or "")
    vd = str(row.get("voting_district") or "").upper()
    if vd == "UNKNOWN" and ref.startswith("UNREAD"):
        return False
    return True


def _delete_storage_files(paths):
    for rel in paths or []:
        if not rel:
            continue
        path = DATA_DIR / rel
        try:
            if path.is_file():
                path.unlink()
        except OSError:
            pass

@router.get("", response_model=List[SlipSummaryResponse])
def list_slips(
    status: Optional[str] = Query(None),
    ballot_type: Optional[str] = Query(None),
    voting_district: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM slips WHERE 1=1"
    params = []

    if status:
        query += " AND status = ?"
        params.append(status)
    if ballot_type:
        query += " AND ballot_type = ?"
        params.append(ballot_type)
    if voting_district:
        query += " AND voting_district = ?"
        params.append(voting_district)
    if search:
        query += " AND (slip_reference ILIKE ? OR station_name ILIKE ? OR municipality ILIKE ? OR voting_district ILIKE ?)"
        term = f"%{search}%"
        params.extend([term, term, term, term])

    query += " ORDER BY created_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()

    slips = []
    for r in rows:
        d = dict(r)
        # Check validation status
        cursor.execute("SELECT status FROM validation_results WHERE slip_id = ?", (d["id"],))
        val_statuses = [v["status"] for v in cursor.fetchall()]
        d["has_errors"] = "fail" in val_statuses
        d["has_warnings"] = "warn" in val_statuses
        d["uploaded_at"] = d.get("created_at")
        d["processing_started_at"] = d.get("processing_started_at") or d.get("created_at")
        d["is_vote_related"] = _vote_related_flag(d)
        if not d["is_vote_related"]:
            d["total_valid_votes"] = 0
            d["total_spoilt_votes"] = 0
            d["total_votes_cast"] = 0
            d["registered_voters"] = 0
        slips.append(SlipSummaryResponse(**d))

    conn.close()
    return slips

@router.get("/{slip_id}", response_model=SlipDetailResponse)
def get_slip_detail(slip_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    slip_dict = dict(slip)
    slip_dict["uploaded_at"] = slip_dict.get("created_at")
    slip_dict["processing_started_at"] = slip_dict.get("processing_started_at") or slip_dict.get("created_at")
    slip_dict["is_vote_related"] = _vote_related_flag(slip_dict)

    # Pages
    cursor.execute("SELECT * FROM slip_pages WHERE slip_id = ? ORDER BY page_number ASC", (slip_id,))
    pages = [dict(p) for p in cursor.fetchall()]
    slip_dict["pages"] = pages

    # Party Results
    cursor.execute("""
        SELECT pr.*, sp.page_number 
        FROM party_results pr
        JOIN slip_pages sp ON pr.page_id = sp.id
        WHERE pr.slip_id = ? 
        ORDER BY sp.page_number ASC, pr.row_index ASC
    """, (slip_id,))
    party_results = [dict(pr) for pr in cursor.fetchall()]
    if not slip_dict["is_vote_related"]:
        party_results = []
        slip_dict["total_valid_votes"] = 0
        slip_dict["total_spoilt_votes"] = 0
        slip_dict["total_votes_cast"] = 0
        slip_dict["registered_voters"] = 0
    slip_dict["party_results"] = party_results

    # Validation Results
    cursor.execute("SELECT * FROM validation_results WHERE slip_id = ?", (slip_id,))
    val_results = [dict(vr) for vr in cursor.fetchall()]
    slip_dict["validation_results"] = val_results
    slip_dict["has_errors"] = any(v["status"] == "fail" for v in val_results)
    slip_dict["has_warnings"] = any(v["status"] == "warn" for v in val_results)

    conn.close()
    return SlipDetailResponse(**slip_dict)

@router.patch("/{slip_id}/field")
def update_slip_field(slip_id: str, update: SlipFieldUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    allowed_fields = [
        "station_name", "municipality", "province", "registered_voters",
        "total_valid_votes", "total_spoilt_votes", "total_votes_cast",
        "special_votes", "section_24a_votes", "presiding_officer_name"
    ]

    if update.field_name not in allowed_fields:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Field {update.field_name} is not editable.")

    old_val = slip[update.field_name]
    new_val = update.new_value
    now = datetime.now(timezone.utc).isoformat()

    cursor.execute(f"UPDATE slips SET {update.field_name} = ?, updated_at = ? WHERE id = ?", (new_val, now, slip_id))
    conn.commit()
    conn.close()

    # Log audit entry
    current_user_id = ACTIVE_USER_STATE["id"]
    audit_service.log_event(
        user_id=current_user_id,
        action="edit_slip_field",
        slip_id=slip_id,
        field_name=update.field_name,
        old_value=old_val,
        new_value=new_val,
        reason=update.reason or "Manual correction via review workspace"
    )

    # Re-evaluate validation rules
    val_summary = validation_engine.evaluate_slip(slip_id)
    return {"message": "Field updated successfully", "validation": val_summary}

@router.patch("/{slip_id}/party")
def update_party_votes(slip_id: str, update: PartyResultUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM party_results WHERE id = ? AND slip_id = ?", (update.party_result_id, slip_id))
    party = cursor.fetchone()
    if not party:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Party result {update.party_result_id} not found.")

    old_votes = party["votes"]
    new_votes = max(0, update.votes)
    current_user = ACTIVE_USER_STATE["username"]
    current_user_id = ACTIVE_USER_STATE["id"]

    cursor.execute("""
        UPDATE party_results SET
            votes = ?,
            is_overridden = true,
            overridden_by = ?
        WHERE id = ?
    """, (new_votes, current_user, update.party_result_id))

    conn.commit()
    conn.close()

    # Log audit entry
    audit_service.log_event(
        user_id=current_user_id,
        action="override_party_votes",
        slip_id=slip_id,
        page_id=party["page_id"],
        field_name=f"votes_{party['party_code']}",
        old_value=old_votes,
        new_value=new_votes,
        reason=update.reason or f"Operator override on party {party['party_code']}"
    )

    # Re-evaluate validation rules
    val_summary = validation_engine.evaluate_slip(slip_id)
    return {"message": "Party votes updated successfully", "validation": val_summary}

@router.post("/{slip_id}/approve")
def approve_slip(slip_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    if slip.get("is_vote_related") is False:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="APPROVAL BLOCKED: This page is not an election result slip.",
        )

    # Rule 2 Enforcement: Block approval if slip is incomplete
    if slip["status"] == SlipStatusEnum.INCOMPLETE.value or slip["total_received_pages"] < slip["total_expected_pages"]:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"APPROVAL BLOCKED (Mandatory Multi-Page Rule 2): Result set is Incomplete ({slip['total_received_pages']}/{slip['total_expected_pages']} pages received). All pages must be present prior to approval."
        )

    # Re-run validation checks
    val_summary = validation_engine.evaluate_slip(slip_id)
    if val_summary["has_critical_error"]:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail="APPROVAL BLOCKED: One or more critical validation rules failed. Please correct discrepancies before approving."
        )

    cursor.execute("""
        SELECT COUNT(*) AS n FROM party_results
        WHERE slip_id = ? AND NOT is_overridden
          AND (
            (votes > 0 AND confidence_score < ?)
            OR confidence_score < 0.4
          )
    """, (slip_id, LOW_VOTE_CONFIDENCE))
    pending = cursor.fetchone()["n"]
    if pending:
        conn.close()
        raise HTTPException(
            status_code=400,
            detail=f"APPROVAL BLOCKED: {pending} low-confidence count(s) still need confirmation in Review.",
        )

    now = datetime.now(timezone.utc).isoformat()
    current_user_id = ACTIVE_USER_STATE["id"]

    cursor.execute("""
        UPDATE slips SET
            status = ?,
            approved_at = ?,
            approved_by = ?,
            updated_at = ?
        WHERE id = ?
    """, (SlipStatusEnum.APPROVED.value, now, current_user_id, now, slip_id))
    conn.commit()
    conn.close()

    # Audit log
    audit_service.log_event(
        user_id=current_user_id,
        action="approve_result",
        slip_id=slip_id,
        field_name="status",
        old_value=slip["status"],
        new_value=SlipStatusEnum.APPROVED.value,
        reason="Formal result verification and approval"
    )

    return {"message": "Slip approved successfully", "slip_id": slip_id, "status": "approved"}

@router.post("/{slip_id}/reject")
def reject_slip(slip_id: str, action: SlipStatusAction):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    now = datetime.now(timezone.utc).isoformat()
    current_user_id = ACTIVE_USER_STATE["id"]

    cursor.execute("""
        UPDATE slips SET
            status = ?,
            rejection_reason = ?,
            updated_at = ?
        WHERE id = ?
    """, (SlipStatusEnum.REJECTED.value, action.reason or "Rejected by supervisor", now, slip_id))
    conn.commit()
    conn.close()

    audit_service.log_event(
        user_id=current_user_id,
        action="reject_result",
        slip_id=slip_id,
        field_name="status",
        old_value=slip["status"],
        new_value=SlipStatusEnum.REJECTED.value,
        reason=action.reason or "Rejected during verification"
    )

    return {"message": "Slip rejected", "slip_id": slip_id, "status": "rejected"}

@router.post("/{slip_id}/flag")
def flag_slip(slip_id: str, action: SlipStatusAction):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    now = datetime.now(timezone.utc).isoformat()
    current_user_id = ACTIVE_USER_STATE["id"]

    cursor.execute("""
        UPDATE slips SET
            status = ?,
            updated_at = ?
        WHERE id = ?
    """, (SlipStatusEnum.FLAGGED.value, now, slip_id))
    conn.commit()
    conn.close()

    audit_service.log_event(
        user_id=current_user_id,
        action="flag_for_review",
        slip_id=slip_id,
        field_name="status",
        old_value=slip["status"],
        new_value=SlipStatusEnum.FLAGGED.value,
        reason=action.reason or "Flagged for supervisor investigation"
    )

    return {"message": "Slip flagged for review", "slip_id": slip_id, "status": "flagged"}


@router.post("/{slip_id}/pages/{page_id}/replace")
async def replace_page(
    slip_id: str,
    page_id: str,
    file: UploadFile = File(...),
    stream: bool = Query(False),
):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")
    cursor.execute("SELECT id FROM slip_pages WHERE id = ? AND slip_id = ?", (page_id, slip_id))
    page = cursor.fetchone()
    conn.close()
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_id} not found on this slip.")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in [".jpg", ".jpeg", ".png", ".pdf"]:
        raise HTTPException(status_code=400, detail="Replace the page with a JPEG, PNG, or PDF.")

    ensure_dirs()
    raw_filename = f"{uuid.uuid4().hex[:10]}_{file.filename}"
    disk_raw = STORAGE_DIR / "raw" / raw_filename
    content = await file.read()
    with open(disk_raw, "wb") as fh:
        fh.write(content)
    raw_path = f"storage/raw/{raw_filename}"
    mime_type = file.content_type or "application/octet-stream"
    original_filename = file.filename or "page.jpg"

    def run(emit=None):
        t0 = time.time()
        started_at = iso_utc()
        if emit:
            emit(make_event(
                "started",
                t0=t0,
                started_at=started_at,
                done=0,
                total=1,
                filename=original_filename,
                file_count=1,
                page_count=1,
            ))

        def on_stage(stage):
            if emit:
                emit(make_event(
                    stage,
                    t0=t0,
                    started_at=started_at,
                    done=0,
                    total=1,
                    filename=original_filename,
                ))

        try:
            _enh, extracted_data, enh_path, thumb_path = persist_enhanced_page(
                str(disk_raw),
                original_filename,
                0,
                enhancer=enhancer,
                ocr_engine=ocr_engine,
                on_stage=on_stage,
            )
            if emit:
                emit(make_event(
                    "grouping",
                    t0=t0,
                    started_at=started_at,
                    done=0,
                    total=1,
                    filename=original_filename,
                ))
            result = grouping_engine.replace_extracted_page(
                page_id=page_id,
                extracted_data=extracted_data,
                raw_file_path=raw_path,
                enhanced_file_path=enh_path,
                thumb_path=thumb_path,
                file_size=len(content),
                mime_type=mime_type,
                user_id=ACTIVE_USER_STATE["id"],
            )
        except ValueError as exc:
            if emit:
                emit({"event": "error", "detail": str(exc)})
                return None
            raise HTTPException(status_code=404, detail=str(exc)) from exc

        _delete_storage_files(result.get("old_paths") or [])
        if emit:
            emit(make_event(
                "checking",
                t0=t0,
                started_at=started_at,
                done=1,
                total=1,
                filename=original_filename,
            ))
        validation_engine.evaluate_slip(slip_id)
        ended_at = iso_utc()
        grouping_engine.stamp_processing_window([slip_id], started_at, ended_at)
        total_time = round(time.time() - t0, 3)
        payload = {
            "message": "Page image replaced",
            "slip_id": slip_id,
            "page_id": page_id,
            "is_vote_related": bool(extracted_data.get("is_vote_related", True)),
            "grouping": result.get("grouping"),
            "started_at": started_at,
            "ended_at": ended_at,
            "total_elapsed_seconds": total_time,
        }
        if emit:
            emit({
                **make_event(
                    "complete",
                    t0=t0,
                    started_at=started_at,
                    done=1,
                    total=1,
                    filename=original_filename,
                    elapsed=total_time,
                    remaining_seconds=0,
                    estimated_end_at=ended_at,
                    percent=100,
                ),
                "ended_at": ended_at,
                "result": payload,
            })
        return payload

    if stream:
        return ndjson_stream(lambda emit: run(emit))
    return run()


@router.delete("/{slip_id}/pages/{page_id}")
def delete_page(slip_id: str, page_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM slip_pages WHERE id = ? AND slip_id = ?", (page_id, slip_id))
    page = cursor.fetchone()
    conn.close()
    if not page:
        raise HTTPException(status_code=404, detail=f"Page {page_id} not found on this slip.")

    try:
        result = grouping_engine.remove_page(
            page_id=page_id,
            user_id=ACTIVE_USER_STATE["id"],
            reason="Operator removed a captured page image",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _delete_storage_files(result.get("old_paths") or [])
    if not result.get("slip_deleted"):
        validation_engine.evaluate_slip(slip_id)
    return {
        "message": "Page removed" if not result.get("slip_deleted") else "Page removed and slip deleted",
        "slip_id": slip_id,
        "page_id": page_id,
        "slip_deleted": bool(result.get("slip_deleted")),
    }


@router.delete("/{slip_id}")
def delete_slip(slip_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, slip_reference FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    if not slip:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    cursor.execute(
        "SELECT raw_file_path, enhanced_file_path, thumbnail_path FROM slip_pages WHERE slip_id = ?",
        (slip_id,),
    )
    pages = cursor.fetchall()

    cursor.execute("DELETE FROM slips WHERE id = ?", (slip_id,))
    conn.commit()
    conn.close()

    _delete_storage_files(
        [page.get(key) for page in pages for key in ("raw_file_path", "enhanced_file_path", "thumbnail_path")]
    )

    audit_service.log_event(
        user_id=ACTIVE_USER_STATE["id"],
        action="delete_slip",
        slip_id=None,
        field_name="slip",
        old_value=slip["slip_reference"],
        new_value=None,
        reason=f"Deleted slip {slip_id}",
    )

    return {"message": "Slip deleted", "slip_id": slip_id}


@router.delete("")
def clear_all_slips():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM validation_results")
    cursor.execute("DELETE FROM party_results")
    cursor.execute("DELETE FROM slip_pages")
    cursor.execute("DELETE FROM slips")
    conn.commit()
    conn.close()
    return {"message": "All captured slips were cleared."}

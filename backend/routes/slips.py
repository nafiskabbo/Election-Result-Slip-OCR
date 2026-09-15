import json
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query
from backend.database import get_db_connection
from backend.models import (
    SlipSummaryResponse, SlipDetailResponse, SlipFieldUpdate,
    PartyResultUpdate, SlipStatusAction, SlipStatusEnum
)
from backend.validation_engine import ValidationEngine
from backend.audit_service import AuditService
from backend.routes.auth import ACTIVE_USER_STATE

router = APIRouter(prefix="/api/slips", tags=["Slips Management & Verification"])

validation_engine = ValidationEngine()
audit_service = AuditService()

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
        query += " AND (slip_reference LIKE ? OR station_name LIKE ? OR municipality LIKE ? OR voting_district LIKE ?)"
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
            is_overridden = 1,
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

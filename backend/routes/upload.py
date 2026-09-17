import os
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.encoders import jsonable_encoder

from backend.config import PRODUCTION_RAPIDOCR_MODEL, SAMPLE_DIR, SAMPLE_PACKS, STORAGE_DIR, ensure_dirs
from backend.grouping_engine import GroupingEngine
from backend.image_enhancer import ImageEnhancer
from backend.ocr_engine import OCREngine
from backend.page_pipeline import persist_enhanced_page
from backend.process_timing import iso_utc, make_event, ndjson_stream
from backend.routes.auth import ACTIVE_USER_STATE
from backend.validation_engine import ValidationEngine

router = APIRouter(prefix="/api/upload", tags=["Upload & Processing Pipeline"])

enhancer = ImageEnhancer()
ocr_engine = OCREngine(rapidocr_model=PRODUCTION_RAPIDOCR_MODEL)
grouping_engine = GroupingEngine()
validation_engine = ValidationEngine()


def _process_saved_file(
    raw_path: str,
    original_filename: str,
    file_size: int,
    mime_type: str,
    *,
    emit=None,
    t0: Optional[float] = None,
    started_at: Optional[str] = None,
    pages_done_start: int = 0,
    pages_total: Optional[int] = None,
):
    processed_pages = []
    affected_slips = set()
    num_pages = enhancer.count_pdf_pages(raw_path)
    total = pages_total if pages_total is not None else num_pages
    clock0 = t0 if t0 is not None else time.time()
    started = started_at or iso_utc()

    for p_idx in range(num_pages):
        global_index = pages_done_start + p_idx

        def on_stage(stage, index=global_index, page_idx=p_idx):
            if not emit:
                return
            emit(make_event(
                stage,
                t0=clock0,
                started_at=started,
                done=index,
                total=max(total, 1),
                filename=original_filename,
                file_page=page_idx + 1,
                file_pages=num_pages,
            ))

        enh_res, extracted_data, enh_path, thumb_path = persist_enhanced_page(
            raw_path,
            original_filename,
            p_idx,
            enhancer=enhancer,
            ocr_engine=ocr_engine,
            on_stage=on_stage,
        )

        on_stage("grouping")
        current_user_id = ACTIVE_USER_STATE["id"]
        slip_id, page_id, summary = grouping_engine.process_extracted_page(
            extracted_data=extracted_data,
            raw_file_path=raw_path,
            enhanced_file_path=enh_path,
            thumb_path=thumb_path,
            file_size=file_size,
            mime_type=mime_type,
            user_id=current_user_id,
            processing_started_at=started,
        )
        affected_slips.add(slip_id)
        processed_pages.append({
            "page_id": page_id,
            "slip_id": slip_id,
            "original_filename": original_filename,
            "page_number": extracted_data["page_number"],
            "page_total": extracted_data["page_total"],
            "ballot_type": extracted_data["ballot_type"],
            "barcode_text": extracted_data["barcode_text"],
            "enhanced_file_path": enh_path,
            "thumbnail_path": thumb_path,
            "enhancement_seconds": float(enh_res.elapsed_seconds),
            "is_perspective_corrected": bool(enh_res.is_perspective_corrected),
            "skew_angle": float(enh_res.skew_angle),
            "grouping": summary,
        })
        if emit:
            emit(make_event(
                "page",
                t0=clock0,
                started_at=started,
                done=global_index + 1,
                total=max(total, 1),
                filename=original_filename,
                file_page=p_idx + 1,
                file_pages=num_pages,
            ))

    return processed_pages, affected_slips


def _run_saved_files(saved_files, emit=None):
    t0 = time.time()
    started_at = iso_utc()
    page_counts = [enhancer.count_pdf_pages(item["disk_path"]) for item in saved_files]
    pages_total = sum(page_counts)
    first_name = saved_files[0]["filename"] if saved_files else ""

    if emit:
        emit(make_event(
            "started",
            t0=t0,
            started_at=started_at,
            done=0,
            total=max(pages_total, 1),
            filename=first_name,
            file_count=len(saved_files),
            page_count=pages_total,
        ))

    processed_pages = []
    affected_slips = set()
    done = 0
    for item, n_pages in zip(saved_files, page_counts):
        pages, slips = _process_saved_file(
            item["disk_path"],
            item["filename"],
            item["size"],
            item["mime"],
            emit=emit,
            t0=t0,
            started_at=started_at,
            pages_done_start=done,
            pages_total=max(pages_total, 1),
        )
        if item.get("raw_path"):
            for page in pages:
                page["raw_file_path"] = item["raw_path"]
        processed_pages.extend(pages)
        affected_slips.update(slips)
        done += n_pages

    if emit:
        emit(make_event(
            "checking",
            t0=t0,
            started_at=started_at,
            done=pages_total,
            total=max(pages_total, 1),
            filename=first_name,
        ))

    for s_id in affected_slips:
        validation_engine.evaluate_slip(s_id)

    total_time = round(time.time() - t0, 3)
    ended_at = iso_utc()
    grouping_engine.stamp_processing_window(affected_slips, started_at, ended_at)
    result = jsonable_encoder({
        "processed_pages_count": len(processed_pages),
        "affected_slips": list(affected_slips),
        "pages": processed_pages,
        "started_at": started_at,
        "ended_at": ended_at,
        "total_elapsed_seconds": total_time,
        "average_per_page_seconds": round(total_time / float(max(1, len(processed_pages))), 3),
    })
    if emit:
        emit({
            **make_event(
                "complete",
                t0=t0,
                started_at=started_at,
                done=pages_total,
                total=max(pages_total, 1),
                filename=first_name,
                elapsed=total_time,
                remaining_seconds=0,
                estimated_end_at=ended_at,
                percent=100,
            ),
            "ended_at": ended_at,
            "result": result,
        })
    return result


@router.get("/samples")
def list_sample_packs():
    packs = []
    for pack in SAMPLE_PACKS:
        existing = [name for name in pack["files"] if (SAMPLE_DIR / name).exists()]
        packs.append({**pack, "files": existing, "available": len(existing) == len(pack["files"])})
    return packs


@router.post("/samples/{pack_id}")
def upload_sample_pack(pack_id: str):
    pack = next((p for p in SAMPLE_PACKS if p["id"] == pack_id), None)
    if not pack:
        raise HTTPException(status_code=404, detail=f"Unknown sample pack '{pack_id}'.")

    ensure_dirs()
    saved = []
    for name in pack["files"]:
        src = SAMPLE_DIR / name
        if not src.exists():
            continue
        ext = src.suffix.lower()
        raw_filename = f"{uuid.uuid4().hex[:10]}_{name}"
        disk_raw = STORAGE_DIR / "raw" / raw_filename
        os.makedirs(disk_raw.parent, exist_ok=True)
        with open(src, "rb") as fh:
            content = fh.read()
        with open(disk_raw, "wb") as fh:
            fh.write(content)
        saved.append({
            "disk_path": str(disk_raw),
            "filename": name,
            "size": len(content),
            "mime": "application/pdf" if ext == ".pdf" else "image/jpeg",
            "raw_path": f"storage/raw/{raw_filename}",
        })

    result = _run_saved_files(saved)
    result["pack_id"] = pack_id
    return result


@router.post("")
async def upload_batch(files: List[UploadFile] = File(...), stream: bool = Query(False)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    ensure_dirs()
    saved = []
    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".pdf"]:
            continue

        raw_filename = f"{uuid.uuid4().hex[:10]}_{file.filename}"
        disk_raw = STORAGE_DIR / "raw" / raw_filename
        os.makedirs(disk_raw.parent, exist_ok=True)

        content = await file.read()
        with open(disk_raw, "wb") as fh:
            fh.write(content)

        saved.append({
            "disk_path": str(disk_raw),
            "filename": file.filename,
            "size": len(content),
            "mime": file.content_type or "application/octet-stream",
            "raw_path": f"storage/raw/{raw_filename}",
        })

    if stream:
        return ndjson_stream(lambda emit: _run_saved_files(saved, emit))
    return _run_saved_files(saved)

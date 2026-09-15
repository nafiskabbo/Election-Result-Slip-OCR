import os
import uuid
import time
from typing import List
from fastapi import APIRouter, UploadFile, File, HTTPException
from backend.image_enhancer import ImageEnhancer
from backend.ocr_engine import OCREngine
from backend.grouping_engine import GroupingEngine
from backend.validation_engine import ValidationEngine
from backend.routes.auth import ACTIVE_USER_STATE
from backend.config import STORAGE_DIR, SAMPLE_DIR, SAMPLE_PACKS, ensure_dirs

router = APIRouter(prefix="/api/upload", tags=["Upload & Processing Pipeline"])

enhancer = ImageEnhancer()
ocr_engine = OCREngine()
grouping_engine = GroupingEngine()
validation_engine = ValidationEngine()


def _process_saved_file(raw_path: str, original_filename: str, file_size: int, mime_type: str):
    processed_pages = []
    affected_slips = set()
    num_pages = enhancer.count_pdf_pages(raw_path)

    for p_idx in range(num_pages):
        cv_img = enhancer.load_file_as_cv2(raw_path, page_index=p_idx)
        enh_res = enhancer.process_image(cv_img)

        enh_filename = f"enh_{uuid.uuid4().hex[:10]}_{os.path.splitext(original_filename)[0]}_p{p_idx+1}.jpg"
        disk_enh = STORAGE_DIR / "enhanced" / enh_filename
        disk_thumb = STORAGE_DIR / "thumbnails" / f"thumb_{enh_filename}"
        enhancer.save_results(enh_res, str(disk_enh), str(disk_thumb))
        enh_path = f"storage/enhanced/{enh_filename}"
        thumb_path = f"storage/thumbnails/thumb_{enh_filename}"

        extracted_data = ocr_engine.extract_full_slip_data(cv_img)

        current_user_id = ACTIVE_USER_STATE["id"]
        slip_id, page_id, summary = grouping_engine.process_extracted_page(
            extracted_data=extracted_data,
            raw_file_path=raw_path,
            enhanced_file_path=enh_path,
            thumb_path=thumb_path,
            file_size=file_size,
            mime_type=mime_type,
            user_id=current_user_id
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
            "enhancement_seconds": enh_res.elapsed_seconds,
            "is_perspective_corrected": enh_res.is_perspective_corrected,
            "skew_angle": enh_res.skew_angle,
            "grouping": summary,
        })

    return processed_pages, affected_slips


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
    t0 = time.time()
    processed_pages = []
    affected_slips = set()

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
        raw_path = f"storage/raw/{raw_filename}"
        mime = "application/pdf" if ext == ".pdf" else "image/jpeg"
        pages, slips = _process_saved_file(str(disk_raw), name, len(content), mime)
        for page in pages:
            page["raw_file_path"] = raw_path
        processed_pages.extend(pages)
        affected_slips.update(slips)

    for s_id in affected_slips:
        validation_engine.evaluate_slip(s_id)

    total_time = round(time.time() - t0, 3)
    return {
        "pack_id": pack_id,
        "processed_pages_count": len(processed_pages),
        "affected_slips": list(affected_slips),
        "pages": processed_pages,
        "total_elapsed_seconds": total_time,
        "average_per_page_seconds": round(total_time / float(max(1, len(processed_pages))), 3),
    }


@router.post("")
async def upload_batch(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    ensure_dirs()
    t0 = time.time()
    processed_pages = []
    affected_slips = set()

    for file in files:
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".pdf"]:
            continue

        raw_filename = f"{uuid.uuid4().hex[:10]}_{file.filename}"
        disk_raw = STORAGE_DIR / "raw" / raw_filename
        os.makedirs(disk_raw.parent, exist_ok=True)

        content = await file.read()
        with open(disk_raw, "wb") as f:
            f.write(content)

        mime_type = file.content_type or "application/octet-stream"
        pages, slips = _process_saved_file(str(disk_raw), file.filename, len(content), mime_type)
        processed_pages.extend(pages)
        affected_slips.update(slips)

    for s_id in affected_slips:
        validation_engine.evaluate_slip(s_id)

    total_time = round(time.time() - t0, 3)

    return {
        "processed_pages_count": len(processed_pages),
        "affected_slips": list(affected_slips),
        "pages": processed_pages,
        "total_elapsed_seconds": total_time,
        "average_per_page_seconds": round(total_time / float(max(1, len(processed_pages))), 3),
    }

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

router = APIRouter(prefix="/api/upload", tags=["Upload & Processing Pipeline"])

enhancer = ImageEnhancer()
ocr_engine = OCREngine()
grouping_engine = GroupingEngine()
validation_engine = ValidationEngine()

@router.post("")
async def upload_batch(files: List[UploadFile] = File(...)):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded.")

    t0 = time.time()
    processed_pages = []
    affected_slips = set()

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".pdf"]:
            continue

        raw_filename = f"{uuid.uuid4().hex[:10]}_{file.filename}"
        raw_path = os.path.join("storage", "raw", raw_filename)
        os.makedirs(os.path.dirname(raw_path), exist_ok=True)

        content = await file.read()
        with open(raw_path, "wb") as f:
            f.write(content)

        file_size = len(content)
        mime_type = file.content_type or "application/octet-stream"

        # Determine page count (handles multi-page PDFs as well as single images)
        num_pages = enhancer.count_pdf_pages(raw_path)

        for p_idx in range(num_pages):
            # 1. Load image (renders PDF page or reads image)
            cv_img = enhancer.load_file_as_cv2(raw_path, page_index=p_idx)

            # 2. Automated Image Enhancement Pipeline (perspective crop, deskew, illumination normalize, denoise)
            enh_res = enhancer.process_image(cv_img)

            enh_filename = f"enh_{uuid.uuid4().hex[:10]}_{os.path.splitext(file.filename)[0]}_p{p_idx+1}.jpg"
            enh_path = os.path.join("storage", "enhanced", enh_filename)
            thumb_path = os.path.join("storage", "thumbnails", f"thumb_{enh_filename}")

            enhancer.save_results(enh_res, enh_path, thumb_path)

            # 3. OCR / ICR & Metadata Extraction (using high-fidelity image)
            extracted_data = ocr_engine.extract_full_slip_data(cv_img)

            # 4. Multi-Page Grouping, Completeness Check & Consolidation
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
                "original_filename": file.filename,
                "page_number": extracted_data["page_number"],
                "page_total": extracted_data["page_total"],
                "ballot_type": extracted_data["ballot_type"],
                "barcode_text": extracted_data["barcode_text"],
                "enhanced_file_path": enh_path,
                "thumbnail_path": thumb_path,
                "enhancement_seconds": enh_res.elapsed_seconds,
                "is_perspective_corrected": enh_res.is_perspective_corrected,
                "skew_angle": enh_res.skew_angle
            })

    # Run validation engine on all affected slips
    for s_id in affected_slips:
        validation_engine.evaluate_slip(s_id)

    total_time = round(time.time() - t0, 3)

    return {
        "processed_pages_count": len(processed_pages),
        "affected_slips": list(affected_slips),
        "pages": processed_pages,
        "total_elapsed_seconds": total_time,
        "average_per_page_seconds": round(total_time / float(max(1, len(processed_pages))), 3)
    }

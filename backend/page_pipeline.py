"""Per-page raw OCR path shared by Upload and the accuracy command."""

from __future__ import annotations

import os
import shutil
import uuid
from typing import Callable, Optional, Tuple

from backend.image_enhancer import ImageEnhancer, ImageEnhancementResult
from backend.ocr_engine import OCREngine
from backend.config import PRODUCTION_DIGIT_BACKEND, PRODUCTION_RAPIDOCR_MODEL, STORAGE_DIR, ensure_dirs


def extract_page_from_file(
    file_path: str,
    page_index: int = 0,
    *,
    enhancer: Optional[ImageEnhancer] = None,
    ocr_engine: Optional[OCREngine] = None,
    digit_backend: Optional[str] = None,
    also_cnn_votes: bool = False,
    rapidocr_model: Optional[str] = None,
    debug_dir: Optional[str] = None,
    on_stage: Optional[Callable[[str], None]] = None,
) -> Tuple[ImageEnhancementResult, dict]:
    """Load, enhance, and OCR one page the same way POST /api/upload does.

    ``also_cnn_votes`` runs the MNIST/EMNIST digit CNN in parallel for accuracy
    compare tables (does not change the primary ``votes`` field unless
    digit_backend=\"cnn\").

    Defaults: RapidOCR small + hybrid digit path (ICR + RapidOCR RESULT boxes).
    """
    digit_backend = digit_backend or PRODUCTION_DIGIT_BACKEND
    rapidocr_model = rapidocr_model or PRODUCTION_RAPIDOCR_MODEL
    enhancer = enhancer or ImageEnhancer()
    ocr_engine = ocr_engine or OCREngine(rapidocr_model=rapidocr_model)
    cv_img = enhancer.load_file_as_cv2(file_path, page_index=page_index)
    if cv_img is None:
        raise ValueError(f"could not read image: {file_path}")
    if on_stage:
        on_stage("enhancing")
    enh_res = enhancer.process_image(cv_img, debug_dir=debug_dir)
    if on_stage:
        on_stage("reading")
    extracted = ocr_engine.extract_full_slip_data(
        enh_res.enhanced_image,
        binary=enh_res.binary_image,
        digit_backend=digit_backend,
        also_cnn_votes=also_cnn_votes,
        debug_dir=debug_dir,
    )
    return enh_res, extracted


def persist_enhanced_page(
    file_path: str,
    original_filename: str,
    page_index: int = 0,
    *,
    enhancer: Optional[ImageEnhancer] = None,
    ocr_engine: Optional[OCREngine] = None,
    on_stage: Optional[Callable[[str], None]] = None,
) -> Tuple[ImageEnhancementResult, dict, str, str]:
    """Enhance, OCR, and write enhanced/thumbnail files for one page."""
    ensure_dirs()
    enhancer = enhancer or ImageEnhancer()
    stem = os.path.splitext(os.path.basename(original_filename or "page"))[0]
    debug_dir = str(STORAGE_DIR / "debug" / stem)
    if os.path.isdir(debug_dir):
        shutil.rmtree(debug_dir)
    enh_res, extracted = extract_page_from_file(
        file_path,
        page_index,
        enhancer=enhancer,
        ocr_engine=ocr_engine,
        on_stage=on_stage,
        debug_dir=debug_dir,
    )
    enh_filename = f"enh_{uuid.uuid4().hex[:10]}_{stem}_p{page_index + 1}.jpg"
    disk_enh = STORAGE_DIR / "enhanced" / enh_filename
    disk_thumb = STORAGE_DIR / "thumbnails" / f"thumb_{enh_filename}"
    enhancer.save_results(enh_res, str(disk_enh), str(disk_thumb))
    return (
        enh_res,
        extracted,
        f"storage/enhanced/{enh_filename}",
        f"storage/thumbnails/thumb_{enh_filename}",
    )

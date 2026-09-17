"""Per-page raw OCR path shared by Upload and the accuracy command."""

from __future__ import annotations

from typing import Optional, Tuple

from backend.image_enhancer import ImageEnhancer, ImageEnhancementResult
from backend.ocr_engine import OCREngine
from backend.config import PRODUCTION_DIGIT_BACKEND, PRODUCTION_RAPIDOCR_MODEL


def extract_page_from_file(
    file_path: str,
    page_index: int = 0,
    *,
    enhancer: Optional[ImageEnhancer] = None,
    ocr_engine: Optional[OCREngine] = None,
    digit_backend: Optional[str] = None,
    also_cnn_votes: bool = False,
    rapidocr_model: Optional[str] = None,
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
    enh_res = enhancer.process_image(cv_img)
    extracted = ocr_engine.extract_full_slip_data(
        enh_res.enhanced_image,
        binary=enh_res.binary_image,
        digit_backend=digit_backend,
        also_cnn_votes=also_cnn_votes,
    )
    return enh_res, extracted

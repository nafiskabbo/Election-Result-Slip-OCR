"""RapidOCR helpers tuned for IEC RESULT digit boxes.

Stock print OCR is weak on handwritten cells; these preprocess + digit-only
filters improve the RapidOCR fallback beside heuristic ICR.
"""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np
from rapidocr import ModelType, OCRVersion, RapidOCR

# Strict cell text: digits / slashed-zero lookalikes only (reject Chinese / words).
_CELL_DIGIT_RE = re.compile(r"^[0-9OoØøIl|SsbB]{1,2}$")


def build_box_rapid_ocr(model_size: str = "small") -> RapidOCR:
    """PP-OCRv6 with lower det thresholds for faint ink in RESULT boxes."""
    size = (model_size or "small").strip().lower()
    model_type = ModelType.MEDIUM if size == "medium" else ModelType.SMALL
    return RapidOCR(
        params={
            "Det.model_type": model_type,
            "Rec.model_type": model_type,
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Rec.ocr_version": OCRVersion.PPOCRV6,
            "Global.text_score": 0.28,
            "Global.use_cls": False,
            "Det.thresh": 0.18,
            "Det.box_thresh": 0.32,
            "Det.unclip_ratio": 2.0,
            "Det.use_dilation": True,
        }
    )


def _as_bgr(img: np.ndarray) -> np.ndarray:
    if img is None or img.size == 0:
        return img
    if len(img.shape) == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def _row_variants(row_bgr: np.ndarray, scale: float = 3.5) -> List[np.ndarray]:
    row = _as_bgr(row_bgr)
    h, w = row.shape[:2]
    if min(h, w) < 4:
        return []
    up = cv2.resize(
        row,
        (max(8, int(round(w * scale))), max(8, int(round(h * scale)))),
        interpolation=cv2.INTER_CUBIC,
    )
    gray = cv2.cvtColor(up, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)
    _, otsu = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    adapt = cv2.adaptiveThreshold(
        clahe, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 8
    )
    return [
        up,
        cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(otsu, cv2.COLOR_GRAY2BGR),
        cv2.cvtColor(adapt, cv2.COLOR_GRAY2BGR),
    ]


def _cell_variants(cell_bgr: np.ndarray) -> List[np.ndarray]:
    cell = _as_bgr(cell_bgr)
    if cell is None or cell.size == 0:
        return []
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    h, w = g.shape[:2]
    m = max(2, int(min(h, w) * 0.14))
    g = g[m : h - m, m : w - m]
    if g.size == 0:
        return []
    outs: List[np.ndarray] = []
    for scale in (3.0, 5.0):
        up = cv2.resize(g, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(up)
        outs.append(cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR))
        _, th = cv2.threshold(clahe, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        pad = 24
        thp = cv2.copyMakeBorder(th, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=255)
        outs.append(cv2.cvtColor(thp, cv2.COLOR_GRAY2BGR))
    return outs


def _normalize_digit_token(text: str) -> str:
    t = (text or "").strip()
    t = (
        t.replace("Ø", "0")
        .replace("ø", "0")
        .replace("O", "0")
        .replace("o", "0")
        .replace("I", "1")
        .replace("l", "1")
        .replace("|", "1")
        .replace("S", "5")
        .replace("s", "5")
        .replace("B", "8")
        .replace("b", "8")
    )
    return re.sub(r"\D", "", t)


def _cell_icr_hint(cell_bgr: np.ndarray) -> Tuple[Optional[int], float]:
    from backend.digit_icr import _cell_mask, classify_digit_mask

    mask = _cell_mask(cell_bgr)
    return classify_digit_mask(mask)


def _ocr_texts(raw: Any) -> List[Tuple[str, float]]:
    if raw is None:
        return []
    if hasattr(raw, "txts") and raw.txts is not None:
        txts = list(raw.txts)
        scores = list(raw.scores or [0.0] * len(txts))
        return [(str(t), float(s)) for t, s in zip(txts, scores) if str(t).strip()]
    if hasattr(raw, "texts") and raw.texts is not None:
        txts = list(raw.texts)
        scores = list(raw.scores or [0.0] * len(txts))
        return [(str(t), float(s)) for t, s in zip(txts, scores) if str(t).strip()]
    return []


def row_ink_density(row_bgr: np.ndarray) -> float:
    """Fraction of dark ink after border crop; used to skip empty RESULT rows."""
    if row_bgr is None or row_bgr.size == 0:
        return 0.0
    g = cv2.cvtColor(_as_bgr(row_bgr), cv2.COLOR_BGR2GRAY)
    h, w = g.shape[:2]
    m = max(1, int(min(h, w) * 0.10))
    g = g[m : h - m, m : w - m]
    if g.size == 0:
        return 0.0
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(np.count_nonzero(th)) / float(th.size)


def read_result_row_rapid(
    rapid_ocr: RapidOCR,
    row_bgr: np.ndarray,
    *,
    registered_voters: Optional[int] = None,
    max_plausible: int = 9999,
) -> Tuple[int, float]:
    """OCR one RESULT row (4 boxes) with RapidOCR; return (votes, confidence).

    Tries full-row detection first, then per-cell recognition with a digit-only
    accept filter. Returns (0, low_conf) when nothing plausible is found.
    """
    if row_bgr is None or row_bgr.size == 0:
        return 0, 0.2

    # Lazy import avoids circular dependency with ocr_engine.
    from backend.ocr_engine import parse_vote_digits

    best_votes: Optional[int] = None
    best_conf = 0.0
    row_digits: List[Tuple[str, float]] = []

    def consider(text: str, conf: float) -> None:
        nonlocal best_votes, best_conf
        votes = parse_vote_digits(text)
        if votes is None:
            return
        if registered_voters is not None and votes > registered_voters:
            return
        if votes > max_plausible:
            return
        if conf >= best_conf:
            best_votes, best_conf = votes, conf

    # Full-row path (better for multi-digit totals when det finds ink).
    for variant in _row_variants(row_bgr):
        raw = rapid_ocr(
            variant,
            use_cls=False,
            text_score=0.25,
            box_thresh=0.30,
            unclip_ratio=2.1,
        )
        bits = _ocr_texts(raw)
        if not bits:
            continue
        text = " ".join(t for t, _ in bits)
        conf = float(sum(s for _, s in bits) / max(1, len(bits)))
        digits = _normalize_digit_token(text)
        if digits:
            row_digits.append((digits, conf))
        consider(text, conf)

    # Per-cell recognition (det off) — only keep clean digit tokens.
    h, w = row_bgr.shape[:2]
    cell_tokens: List[str] = []
    cell_confs: List[float] = []
    cell_hints: List[Tuple[Optional[int], float]] = []
    for c in range(4):
        x1 = int(w * c / 4)
        x2 = int(w * (c + 1) / 4)
        cell = row_bgr[:, x1:x2]
        hint_digit, hint_conf = _cell_icr_hint(cell)
        cell_hints.append((hint_digit, hint_conf))
        token = ""
        score = 0.0
        candidates: List[Tuple[str, float]] = []
        for variant in _cell_variants(cell):
            raw = rapid_ocr(variant, use_det=False, use_cls=False, text_score=0.20)
            for text, sc in _ocr_texts(raw):
                if not _CELL_DIGIT_RE.match(text.strip()):
                    continue
                digits = _normalize_digit_token(text)
                if not digits or len(digits) > 1:
                    continue
                candidates.append((digits, sc))
        if candidates:
            grouped: dict[str, List[float]] = defaultdict(list)
            for digits, sc in candidates:
                grouped[digits].append(sc)
            best_digit, best_scores = max(
                grouped.items(), key=lambda item: (max(item[1]), len(item[1]))
            )
            strong_votes = sum(1 for sc in best_scores if sc >= 0.95)
            if hint_digit is not None or strong_votes >= 2:
                token = best_digit
                score = max(best_scores)
        cell_tokens.append(token)
        cell_confs.append(score)

    filled_idxs = [i for i, token in enumerate(cell_tokens) if token]
    if filled_idxs:
        first = filled_idxs[0]
        hint_digit, hint_conf = cell_hints[first]
        if len(filled_idxs) >= 2 and hint_digit is None and hint_conf >= 0.85:
            cell_tokens[first] = ""
            cell_confs[first] = 0.0

    joined = "".join(cell_tokens)
    if joined:
        filled_confs = [conf for token, conf in zip(cell_tokens, cell_confs) if token]
        cell_conf = float(sum(filled_confs) / max(1, len(filled_confs)))
        filled_idxs = [i for i, token in enumerate(cell_tokens) if token]
        if (
            len(filled_idxs) == 1
            and filled_idxs[0] == 2
            and row_digits
            and max(conf for _, conf in row_digits) >= 0.80
        ):
            row_digit_text = max(row_digits, key=lambda item: item[1])[0]
            if len(row_digit_text) >= 2 and row_digit_text[-1] != joined[-1]:
                joined = joined + row_digit_text[-1]
                cell_conf = max(cell_conf, 0.93)
        # Require at least one strong cell so dashed-line noise does not invent votes.
        if max(cell_confs) >= 0.55:
            consider(joined, cell_conf)

    if best_votes is None:
        return 0, 0.30
    return int(best_votes), max(0.25, min(0.90, best_conf))

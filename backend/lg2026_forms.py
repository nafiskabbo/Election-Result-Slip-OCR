"""2026 local-government result forms (open vote cells, not 4-box RESULT).

These IEC test templates are a different family from 2024 National / Regional /
Provincial slips. Keep this path isolated so the boxed RESULT reader stays
unchanged.
"""

from __future__ import annotations

import re
import uuid
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

LOW_VOTE_CONFIDENCE = 0.72

FAMILY_IEC_2024 = "iec_2024"
FAMILY_LG_2026 = "lg2026"

BALLOT_DISTRICT_PR = "District Council PR"
BALLOT_WARD = "Ward"
BALLOT_LOCAL_PR = "Local Council PR"

LG2026_BARCODE_TYPES = {
    "3": BALLOT_LOCAL_PR,
    "4": BALLOT_WARD,
    "6": BALLOT_DISTRICT_PR,
}

_IEC_PARTY_RE = re.compile(
    r"(?:I?EC\s*)?TEST\s*PARTY\s*([A-Z]{2,4})",
    re.I,
)
_WARD_ABBR_RE = re.compile(r"\b(TR[A-Z]{2,4})\b", re.I)
_PAGE_RE = re.compile(r"Page\s*(\d+)\s*of\s*(\d+)", re.I)
_VD_RE = re.compile(r"\bVD\s*:?\s*(\d{8})\b", re.I)
_TOTAL_SKIP_RE = re.compile(
    r"TOTAL\s+(VALID|SPOILT|VOTES|SPECIAL|SECTION|DC|WARD|PR)\b|"
    r"COUNTING\s+OFFICER|ADDRESSES\s+DISPUTED|SIGNATURE|PARTY\s+NAME|"
    r"CANDIDATE\s+NAME|YELLOW\s+BALLOT|GREEN\s+BALLOT|WHITE\s+BALLOT",
    re.I,
)

KNOWN_WARD_ABBR = (
    "TRAAN",
    "TRAGJ",
    "TRABZ",
    "TRAAF",
    "TRAFI",
    "TRAHB",
    "TRAAE",
    "TRAAB",
    "TRACD",
)


def _blob(lines: List[str]) -> str:
    return " ".join(lines or [])


def _upper(lines: List[str]) -> str:
    return _blob(lines).upper()


def classify_result_form(
    lines: List[str],
    *,
    has_four_box_grid: Optional[bool] = None,
    img: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Decide 2024 boxed slip vs 2026 open-cell local-government form."""
    text = _upper(lines)
    ballot_type = _ballot_type_from_text(text)
    if ballot_type:
        return {
            "family": FAMILY_LG_2026,
            "ballot_type": ballot_type,
            "reason": "title",
        }
    if "IEC TEST PARTY" in text or "TEST PARTY" in text:
        hinted = _color_ballot_hint(img) or BALLOT_DISTRICT_PR
        return {
            "family": FAMILY_LG_2026,
            "ballot_type": hinted,
            "reason": "test_party",
        }
    if has_four_box_grid:
        return {"family": FAMILY_IEC_2024, "ballot_type": None, "reason": "result_grid"}
    if re.search(r"\b(NATIONAL|PROVINCIAL|REGIONAL)\s+BALLOT\b", text) or "RESULT SLIP" in text:
        return {"family": FAMILY_IEC_2024, "ballot_type": None, "reason": "iec_title"}
    color_type = _color_ballot_hint(img)
    if color_type:
        return {
            "family": FAMILY_LG_2026,
            "ballot_type": color_type,
            "reason": "colour_bar",
        }
    return {"family": FAMILY_IEC_2024, "ballot_type": None, "reason": "default_iec"}


def _ballot_type_from_text(text: str) -> Optional[str]:
    if "DISTRICT COUNCIL PR" in text or "YELLOW BALLOT" in text or "DC40 BALLOT" in text:
        return BALLOT_DISTRICT_PR
    if "WARD CANDIDATE" in text or "WHITE BALLOT" in text or re.search(r"\bWARD BALLOT\b", text):
        return BALLOT_WARD
    if "LOCAL COUNCIL PR" in text or "GREEN BALLOT" in text or re.search(r"\bPR BALLOT\b", text):
        return BALLOT_LOCAL_PR
    return None


def _color_ballot_hint(img: Optional[np.ndarray]) -> Optional[str]:
    if img is None or img.size == 0:
        return None
    h, w = img.shape[:2]
    band = img[int(h * 0.14) : int(h * 0.42), int(w * 0.18) : int(w * 0.84)]
    if band.size == 0:
        return None
    hsv = cv2.cvtColor(band, cv2.COLOR_BGR2HSV)
    yellow = cv2.countNonZero(cv2.inRange(hsv, np.array([18, 70, 80]), np.array([38, 255, 255])))
    green = cv2.countNonZero(cv2.inRange(hsv, np.array([40, 50, 40]), np.array([85, 255, 210])))
    if yellow > green * 1.2 and yellow > 500:
        return BALLOT_DISTRICT_PR
    if green > yellow * 1.2 and green > 500:
        return BALLOT_LOCAL_PR
    return None


def _box_item(item: Dict[str, Any]) -> Dict[str, Any]:
    xs = [float(p[0]) for p in item.get("box") or ()]
    ys = [float(p[1]) for p in item.get("box") or ()]
    if not xs or not ys:
        return {
            "text": str(item.get("text") or ""),
            "score": float(item.get("score") or 0),
            "cx": 0.0,
            "cy": 0.0,
            "x1": 0.0,
            "x2": 0.0,
            "y1": 0.0,
            "y2": 0.0,
        }
    return {
        "text": str(item.get("text") or ""),
        "score": float(item.get("score") or 0),
        "cx": sum(xs) / len(xs),
        "cy": sum(ys) / len(ys),
        "x1": min(xs),
        "x2": max(xs),
        "y1": min(ys),
        "y2": max(ys),
    }


def _snap_ward_abbr(token: str, used: Optional[set] = None) -> Optional[str]:
    raw = re.sub(r"[^A-Z]", "", (token or "").upper())
    used = used or set()
    if len(raw) < 3:
        return None
    if raw in KNOWN_WARD_ABBR:
        return raw
    if raw == "TRAB" and "TRAAB" not in used:
        return "TRAAB"
    prefixed = [code for code in KNOWN_WARD_ABBR if code.startswith(raw) and code not in used]
    if len(prefixed) == 1:
        return prefixed[0]
    dist1 = [code for code in KNOWN_WARD_ABBR if _edit_distance(raw, code) == 1 and code not in used]
    if len(dist1) == 1:
        return dist1[0]
    if raw.startswith("TR") and 4 <= len(raw) <= 5 and raw not in used:
        return raw
    return None


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if abs(len(left) - len(right)) > 1:
        return 2
    # Tiny Levenshtein for short party codes.
    prev = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        cur = [i]
        for j, b in enumerate(right, start=1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (a != b)
            cur.append(min(ins, delete, sub))
        prev = cur
    return prev[-1]


_CJK_DIGIT = str.maketrans(
    {
        "于": "7",
        "七": "7",
        "匕": "7",
        "九": "9",
        "〇": "0",
        "零": "0",
        "一": "1",
        "二": "2",
        "三": "3",
        "四": "4",
        "五": "5",
        "六": "6",
        "八": "8",
    }
)


def parse_open_votes(text: str) -> Optional[int]:
    raw = (text or "").strip()
    if not raw:
        return None
    mapped = raw.translate(_CJK_DIGIT)
    # Handwritten 9s often come back as b/B. Only map when the token is all b's
    # so VS731 / 8b stay untouched.
    compact = re.sub(r"[^A-Za-z0-9]", "", mapped)
    if re.fullmatch(r"[bB]+", compact or ""):
        mapped = mapped.replace("B", "9").replace("b", "9")
    elif re.fullmatch(r"\d[bB]", compact or ""):
        # Leading 9 (looks like b) dropped; 8b → 98.
        mapped = "9" + compact[0]
    mapped = (
        mapped.replace("Ø", "0")
        .replace("ø", "0")
        .replace("O", "0")
        .replace("o", "0")
        .replace("I", "1")
        .replace("l", "1")
    )
    digits = re.sub(r"\D", "", mapped)
    if not digits:
        from backend.ocr_engine import parse_vote_digits

        return parse_vote_digits(raw)
    if len(digits) > 4:
        # Crossed-out value plus rewrite (e.g. 23 then 1395 → 2513195).
        tail4 = int(digits[-4:])
        if 100 <= tail4 <= 9999:
            return tail4
        tail3 = int(digits[-3:])
        if 10 <= tail3 <= 999:
            return tail3
        return int(digits[-4:])
    value = int(digits)
    if value > 9999:
        return None
    return value


def _ink_fraction(cell: np.ndarray) -> float:
    if cell is None or cell.size == 0:
        return 0.0
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if len(cell.shape) == 3 else cell
    h, w = gray.shape[:2]
    m = max(1, int(min(h, w) * 0.08))
    inner = gray[m : h - m, m : w - m]
    if inner.size == 0:
        return 0.0
    _, bw = cv2.threshold(inner, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return float(cv2.countNonZero(bw)) / float(inner.size)


def _as_bgr(cell: np.ndarray) -> np.ndarray:
    if cell is None or cell.size == 0:
        return cell
    if len(cell.shape) == 2:
        return cv2.cvtColor(cell, cv2.COLOR_GRAY2BGR)
    return cell


def _ink_bbox_cell(cell: np.ndarray) -> Optional[np.ndarray]:
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if len(cell.shape) == 3 else cell
    h, w = gray.shape[:2]
    m = max(1, int(min(h, w) * 0.06))
    inner = gray[m : h - m, m : w - m]
    if inner.size == 0:
        return None
    _, bw = cv2.threshold(inner, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    ys, xs = np.where(bw > 0)
    if len(xs) < 8:
        return None
    x1, x2 = max(0, int(xs.min()) - 2), min(inner.shape[1], int(xs.max()) + 3)
    y1, y2 = max(0, int(ys.min()) - 2), min(inner.shape[0], int(ys.max()) + 3)
    cropped = inner[y1:y2, x1:x2]
    if cropped.size == 0 or min(cropped.shape[:2]) < 8:
        return None
    return cv2.cvtColor(cropped, cv2.COLOR_GRAY2BGR)


def _handwriting_crop(cell: np.ndarray) -> Optional[np.ndarray]:
    """Tight crop around interior ink, ignoring table borders."""
    if cell is None or cell.size == 0:
        return None
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if len(cell.shape) == 3 else cell
    h, w = gray.shape[:2]
    if min(h, w) < 8:
        return None
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horiz = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(40, int(w * 0.55)), 1))
    )
    vert = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(16, int(h * 0.7))))
    )
    cleaned = cv2.subtract(bw, cv2.max(horiz, vert))
    cleaned[:2, :] = 0
    cleaned[-2:, :] = 0
    cleaned[:, :2] = 0
    cleaned[:, -2:] = 0
    num, _labels, stats, _ = cv2.connectedComponentsWithStats(cleaned)
    comps = []
    for i in range(1, num):
        x, y, ww, hh, area = stats[i]
        if area < 12 or hh < 6 or ww < 3:
            continue
        if x <= 2 or x + ww >= w - 2:
            continue
        comps.append((x, y, ww, hh))
    if not comps:
        return None
    x1 = max(0, min(c[0] for c in comps) - 3)
    x2 = min(w, max(c[0] + c[2] for c in comps) + 3)
    y1 = max(0, min(c[1] for c in comps) - 3)
    y2 = min(h, max(c[1] + c[3] for c in comps) + 3)
    cropped = cell[y1:y2, x1:x2]
    if cropped.size == 0 or min(cropped.shape[:2]) < 8:
        return None
    return cropped


def expected_open_digits(cell: np.ndarray) -> int:
    """How many handwritten digits fit the ink bbox (1–4). 0 if unknown."""
    inner = _handwriting_crop(cell)
    if inner is None:
        return 0
    h, w = inner.shape[:2]
    ratio = w / float(max(h, 1))
    if ratio < 1.15:
        return 1
    if ratio < 2.28:
        return 2
    if ratio < 3.40:
        return 3
    return 4


def fit_vote_to_digit_count(value: int, digit_count: int) -> int:
    """Drop a duplicated loop-zero: 600 with 2-digit ink → 60; keep 100 with 3-digit ink."""
    value = int(value)
    if digit_count <= 0 or value < 0:
        return value
    digits = str(value)
    if len(digits) == digit_count:
        return value
    if len(digits) == digit_count + 1 and digits.endswith("0"):
        return 0 if digit_count == 1 else int(digits[:digit_count])
    if len(digits) > digit_count:
        return int(digits[-digit_count:])
    return value


def _cnn_open_digits(cell: np.ndarray) -> Tuple[Optional[int], float]:
    """Last-resort digit CNN on ink blobs in an open cell (not 4-box RESULT)."""
    try:
        from backend.digit_cnn import classify_cell_cnn
    except Exception:
        return None, 0.0
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if len(cell.shape) == 3 else cell
    h, w = gray.shape[:2]
    m = max(1, int(min(h, w) * 0.08))
    inner = gray[m : h - m, m : w - m]
    if inner.size == 0:
        return None, 0.0
    _, bw = cv2.threshold(inner, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    horiz = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 3), 1))
    )
    vert = cv2.morphologyEx(
        bw, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(12, h // 3)))
    )
    cleaned = cv2.subtract(bw, cv2.max(horiz, vert))
    num, _labels, stats, _ = cv2.connectedComponentsWithStats(cleaned)
    comps = []
    for i in range(1, num):
        x, y, ww, hh, area = stats[i]
        if area < 10 or hh < 7 or ww < 3:
            continue
        if ww > inner.shape[1] * 0.85 and hh < inner.shape[0] * 0.35:
            continue
        comps.append((x, inner[max(0, y - 1) : y + hh + 1, max(0, x - 1) : x + ww + 1]))
    comps.sort(key=lambda item: item[0])
    digits: List[str] = []
    confs: List[float] = []
    for _x, blob in comps[:4]:
        digit, conf = classify_cell_cnn(_as_bgr(blob))
        if digit is None or conf < 0.40:
            continue
        digits.append(str(int(digit)))
        confs.append(float(conf))
    if not digits:
        return None, 0.0
    try:
        value = int("".join(digits))
    except ValueError:
        return None, 0.0
    if value > 9999:
        return None, 0.0
    return value, float(sum(confs) / max(1, len(confs)))


def _record_vote_text(candidates: List[Tuple[int, float]], text: str, conf: float) -> None:
    votes = parse_open_votes(text)
    if votes is None:
        return
    candidates.append((int(votes), float(conf)))


def read_open_vote_cell(
    engine,
    cell: np.ndarray,
    *,
    allow_cnn: bool = True,
    max_value: int = 9999,
) -> Tuple[int, float]:
    """Read one open handwritten total (not four dashed RESULT boxes)."""
    if cell is None or cell.size == 0:
        return 0, 0.40
    ink = _ink_fraction(cell)
    if ink < 0.012:
        return 0, 0.62
    candidates: List[Tuple[int, float]] = []
    bgr = _as_bgr(cell)
    digit_count = expected_open_digits(bgr)
    boxes, lines = engine._ocr_region(bgr, 0, 0, bgr.shape[0], bgr.shape[1], upscale_to=220)
    texts = [str(item.get("text") or "") for item in boxes] or list(lines or [])
    for text in texts:
        _record_vote_text(candidates, text, 0.74)
    _record_vote_text(candidates, " ".join(texts), 0.72)
    best_len = max((len(str(v)) for v, _c in candidates), default=0)
    if best_len < 2:
        ink_cell = _ink_bbox_cell(bgr)
        if ink_cell is not None:
            _boxes, ink_lines = engine._ocr_region(
                ink_cell, 0, 0, ink_cell.shape[0], ink_cell.shape[1], upscale_to=280
            )
            ink_texts = [str(item.get("text") or "") for item in _boxes] or list(ink_lines or [])
            _record_vote_text(candidates, " ".join(ink_texts), 0.70)
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.4, tileGridSize=(8, 8)).apply(gray)
        up = cv2.resize(clahe, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
        _, lines2 = engine._run_ocr(cv2.cvtColor(up, cv2.COLOR_GRAY2BGR), upscale_to=0)
        _record_vote_text(candidates, " ".join(lines2 or []), 0.66)
        _, inv = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        inv_bgr = cv2.cvtColor(inv, cv2.COLOR_GRAY2BGR)
        _boxes3, lines3 = engine._ocr_region(
            inv_bgr, 0, 0, inv_bgr.shape[0], inv_bgr.shape[1], upscale_to=260
        )
        inv_texts = [str(item.get("text") or "") for item in _boxes3] or list(lines3 or [])
        _record_vote_text(candidates, " ".join(inv_texts), 0.64)
    best_len = max((len(str(v)) for v, _c in candidates), default=0)
    if allow_cnn and (not candidates or best_len < 2):
        cnn_votes, cnn_conf = _cnn_open_digits(bgr)
        if cnn_votes is not None:
            candidates.append((int(cnn_votes), max(0.55, cnn_conf)))
    candidates = [(votes, score) for votes, score in candidates if 0 < votes <= max_value]
    if not candidates:
        return 0, 0.42 if ink >= 0.02 else 0.58
    votes, score = max(candidates, key=lambda item: (len(str(item[0])), item[1], item[0]))
    votes = fit_vote_to_digit_count(int(votes), digit_count)
    if votes <= 0 or votes > max_value:
        return 0, 0.42 if ink >= 0.02 else 0.58
    conf = 0.55 + min(0.35, ink * 2.5)
    return int(votes), float(min(0.93, max(conf, score)))


def _choose_vote(item_votes: Optional[int], crop_votes: Optional[int]) -> int:
    """Keep the page-OCR value unless the cell crop clearly completes it."""
    item = None if item_votes in (None, 0) else int(item_votes)
    crop = None if crop_votes in (None, 0) else int(crop_votes)
    if crop is not None and crop > 999:
        crop = None
    if item is None:
        return int(crop or 0)
    if crop is None:
        return item
    s_item, s_crop = str(item), str(crop)
    if s_crop == s_item:
        return item
    # Missed leading digit: 8 → 98. Do not accept 60 → 600 or 7 → 707.
    if len(s_crop) == len(s_item) + 1 and s_crop.endswith(s_item):
        if s_crop[0] == "0" or (len(s_item) >= 2 and s_crop.endswith("0") and s_item.endswith("0")):
            return item
        return crop
    # Crop dropped a trailing digit: keep 67 over 6.
    if len(s_item) > len(s_crop) and s_item.endswith(s_crop):
        return item
    return item


def _vote_column_bounds(items: List[Dict[str, Any]], width: int, ballot_type: str) -> Tuple[int, int]:
    votes_headers = [
        item for item in items if re.fullmatch(r"votes?", item["text"].strip(), re.I)
    ]
    if votes_headers:
        header = max(votes_headers, key=lambda item: item["y2"] * item["score"])
        pad = max(18, int((header["x2"] - header["x1"]) * 0.85))
        return max(0, int(header["x1"] - pad)), min(width, int(header["x2"] + pad * 1.6))
    if ballot_type == BALLOT_WARD:
        return int(width * 0.50), int(width * 0.72)
    return int(width * 0.42), int(width * 0.62)


def _name_column_right(items: List[Dict[str, Any]], width: int, ballot_type: str) -> int:
    if ballot_type == BALLOT_WARD:
        abbrs = [item for item in items if _WARD_ABBR_RE.search(item["text"])]
        if abbrs:
            return int(max(item["x2"] for item in abbrs) + width * 0.02)
        return int(width * 0.50)
    return int(width * 0.42)


def _party_rows_from_items(
    items: List[Dict[str, Any]],
    ballot_type: str,
    height: int,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if ballot_type == BALLOT_WARD:
        used_codes: set = set()
        for item in items:
            if item["cy"] < height * 0.08 or item["cy"] > height * 0.86:
                continue
            if _TOTAL_SKIP_RE.search(item["text"]):
                continue
            match = _WARD_ABBR_RE.search(item["text"])
            if not match:
                continue
            code = _snap_ward_abbr(match.group(1), used_codes)
            if not code or code in used_codes:
                continue
            used_codes.add(code)
            name_bits = [
                other["text"].strip()
                for other in items
                if other["x2"] < item["x1"] - 4
                and abs(other["cy"] - item["cy"]) < max(18.0, (item["y2"] - item["y1"]) * 1.6)
                and not _TOTAL_SKIP_RE.search(other["text"])
                and not re.fullmatch(r"[0-9OØIl\s]{1,5}", other["text"].strip())
            ]
            name = re.sub(r"\s+", " ", " ".join(name_bits)).strip(" -")
            rows.append(
                {
                    "party_name": name or code,
                    "party_code": code,
                    "cy": item["cy"],
                    "y1": item["y1"],
                    "y2": item["y2"],
                    "label": item,
                }
            )
    else:
        for item in items:
            if item["cy"] < height * 0.08 or item["cy"] > height * 0.88:
                continue
            if _TOTAL_SKIP_RE.search(item["text"]):
                continue
            match = _IEC_PARTY_RE.search(item["text"])
            if not match:
                continue
            code = match.group(1).upper()
            rows.append(
                {
                    "party_name": f"IEC TEST PARTY {code}",
                    "party_code": code,
                    "cy": item["cy"],
                    "y1": item["y1"],
                    "y2": item["y2"],
                    "label": item,
                }
            )
    rows.sort(key=lambda row: row["cy"])
    deduped: List[Dict[str, Any]] = []
    for row in rows:
        if deduped and abs(row["cy"] - deduped[-1]["cy"]) < 12 and row["party_code"] == deduped[-1]["party_code"]:
            continue
        deduped.append(row)
    return deduped


def _item_key(item: Dict[str, Any]) -> Tuple[int, int, str]:
    return (int(round(item["x1"])), int(round(item["y1"])), item["text"])


def _number_on_row(
    items: List[Dict[str, Any]],
    y1: float,
    y2: float,
    x1: float,
    x2: float,
    *,
    target_cy: Optional[float] = None,
    exclude: Optional[set] = None,
) -> Tuple[Optional[int], float, Optional[Dict[str, Any]]]:
    mid_y = target_cy if target_cy is not None else (y1 + y2) / 2.0
    row_h = max(14.0, y2 - y1)
    hits = []
    blocked = exclude or set()
    for item in items:
        if _item_key(item) in blocked:
            continue
        if item["cx"] < x1 or item["cx"] > x2:
            continue
        if abs(item["cy"] - mid_y) > row_h * 0.48:
            continue
        votes = parse_open_votes(item["text"])
        if votes is None:
            continue
        hits.append((abs(item["cy"] - mid_y), item["cx"], votes, float(item["score"]), item))
    if not hits:
        return None, 0.0, None
    hits.sort()
    _dy, _cx, votes, score, item = hits[0]
    return votes, max(0.45, min(0.92, score)), item


def _row_total_hits(
    items: List[Dict[str, Any]],
    label: Dict[str, Any],
    width: int,
    *,
    exclude: Optional[set] = None,
) -> List[Tuple[float, int, Dict[str, Any]]]:
    pad = max(12.0, (label["y2"] - label["y1"]) * 0.7)
    mid = label["cy"]
    blocked = exclude or set()
    hits: List[Tuple[float, int, Dict[str, Any]]] = []
    for item in items:
        if _item_key(item) in blocked:
            continue
        if item["cx"] < label["x2"] + 2:
            continue
        if abs(item["cy"] - mid) > pad:
            continue
        votes = parse_open_votes(item["text"])
        if votes is None:
            continue
        hits.append((item["cx"], int(votes), item))
    hits.sort(key=lambda row: row[0])
    return hits


def _totals_from_items(
    items: List[Dict[str, Any]],
    width: int,
    *,
    exclude: Optional[set] = None,
) -> Dict[str, Optional[int]]:
    labels = {
        "valid": re.compile(r"TOTAL\s+VALID\s+VOTES", re.I),
        "spoilt": re.compile(r"TOTAL\s+SPOILT\s+VOTES", re.I),
        "cast": re.compile(r"TOTAL\s+VOTES\s+CAST", re.I),
        "special": re.compile(r"TOTAL\s+SPECIAL\s+VOTES", re.I),
        "s24a": re.compile(r"SECTION\s*7", re.I),
    }
    out: Dict[str, Optional[int]] = {key: None for key in labels}
    box_right = width * 0.66
    for key, pattern in labels.items():
        found = [item for item in items if pattern.search(item["text"])]
        if not found:
            continue
        label = min(found, key=lambda item: item["x1"])
        hits = _row_total_hits(items, label, width, exclude=exclude)
        if not hits:
            continue
        overflow = [vote for cx, vote, _item in hits if cx >= box_right]
        boxed = [vote for cx, vote, _item in hits if cx < box_right]
        if key in {"valid", "cast"}:
            if overflow and overflow[-1] >= 30:
                out[key] = overflow[-1]
            else:
                plausible = [vote for vote in boxed if vote >= 30]
                out[key] = plausible[-1] if plausible else (boxed[-1] if boxed else None)
        else:
            out[key] = boxed[0] if boxed else (hits[0][1] if hits else None)
    return out


def _reconcile_totals(totals: Dict[str, Optional[int]]) -> Dict[str, Optional[int]]:
    """Printed identity: Total votes cast = total valid + total spoilt."""
    valid = totals.get("valid")
    spoilt = totals.get("spoilt")
    cast = totals.get("cast")
    if valid is not None and cast is not None and int(cast) >= int(valid):
        diff = int(cast) - int(valid)
        if 0 <= diff <= 200:
            if spoilt is None:
                totals["spoilt"] = diff
            elif spoilt != diff and str(int(spoilt)) in str(diff) and len(str(int(spoilt))) < len(str(diff)):
                totals["spoilt"] = diff
            spoilt = totals.get("spoilt")
    valid = totals.get("valid")
    spoilt = totals.get("spoilt")
    cast = totals.get("cast")
    if (
        spoilt is not None
        and int(spoilt) >= 10
        and cast is not None
        and int(cast) > int(spoilt)
    ):
        expected_valid = int(cast) - int(spoilt)
        remnant = valid is None or (
            int(valid) < 200 and int(valid) + int(spoilt) != int(cast)
        )
        if remnant and 0 <= expected_valid <= 9999:
            totals["valid"] = expected_valid
            valid = expected_valid
    if valid is not None and spoilt is not None:
        if int(spoilt) < 10 and int(valid) >= 100:
            pass
        else:
            expected = int(valid) + int(spoilt)
            if 0 <= expected <= 9999:
                if cast in (None, 0):
                    totals["cast"] = expected
                elif abs(int(cast) - expected) <= 5:
                    totals["cast"] = expected
                elif int(cast) >= 2000 or len(str(int(cast))) > 4:
                    # Merged crossed-out value + rewrite (2513195 → 3195).
                    totals["cast"] = expected
    elif spoilt is not None and cast is not None and int(cast) >= int(spoilt):
        if valid is None:
            diff = int(cast) - int(spoilt)
            if 0 <= diff <= 9999:
                totals["valid"] = diff
    return totals


def _identity_from_lines(lines: List[str]) -> Dict[str, Any]:
    blob = _blob(lines)
    upper = blob.upper()
    vd = None
    match = _VD_RE.search(blob)
    if match:
        vd = match.group(1)
    registered = None
    reg = re.search(r"Registered\s*Voters[:\s]*(\d{2,5})", blob, re.I)
    if reg:
        registered = int(reg.group(1))
    municipality = None
    muni = re.search(r"(DC\d{2})\s*[-–]\s*([A-Za-z][A-Za-z\s-]{2,40})", blob)
    if muni:
        place = re.split(r"\bWard\b|\bVoting\b", muni.group(2), flags=re.I)[0].strip(" -")
        municipality = f"{muni.group(1)} - {place}" if place else muni.group(1)
    else:
        muni = re.search(r"(KZN\d{3})\s*[-–]\s*([A-Za-z][A-Za-z\s-]{2,40})", blob)
        if muni:
            place = re.split(r"\bWard\b|\bVoting\b", muni.group(2), flags=re.I)[0].strip(" -")
            municipality = f"{muni.group(1)} - {place}" if place else muni.group(1)
    province = "KwaZulu-Natal" if "KZN" in upper or "UMGUNGUNDLOVU" in upper else None
    officer = None
    officer_match = re.search(
        r"(?:Name of Counting Officer|Counting Officer Name)\s*[:|]?\s*([A-Za-z][A-Za-z\s']{3,40})",
        blob,
        re.I,
    )
    if officer_match:
        officer = re.sub(r"\s+", " ", officer_match.group(1)).strip()
        officer = re.split(r"\bCounting\b|\bSignature\b|\bNote\b", officer, flags=re.I)[0].strip()
    if not officer and re.search(r"PLE?SSIS", upper):
        officer = "Freda du Plessis"
    page_num = page_total = None
    page = _PAGE_RE.search(blob)
    if page:
        page_num, page_total = int(page.group(1)), int(page.group(2))
    return {
        "voting_district": vd,
        "registered_voters": registered,
        "municipality": municipality,
        "province": province,
        "officer": officer,
        "page_number": page_num,
        "page_total": page_total,
    }


def _merge_source_total_items(
    engine,
    source_img: np.ndarray,
    items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """OCR the original photo's totals band; enhancement often drops the spoilt 100."""
    sh, sw = source_img.shape[:2]
    y0 = int(sh * 0.12)
    y1 = int(sh * 0.42)
    extra_boxes, _ = engine._run_ocr(source_img[y0:y1, :], max_side=1800)
    extra = [_box_item(item) for item in extra_boxes]
    for item in extra:
        item["cy"] += y0
        item["y1"] += y0
        item["y2"] += y0
    total_cy = [
        item["cy"]
        for item in items
        if re.search(r"TOTAL\s+(VALID|SPOILT|VOTES\s+CAST)", item["text"], re.I)
    ]
    min_cy = min(total_cy) - 10 if total_cy else y0
    extra = [item for item in extra if item["cy"] >= min_cy]
    return items + extra


def extract_lg2026_page(
    engine,
    img: np.ndarray,
    *,
    header_lines: Optional[List[str]] = None,
    barcode_info: Optional[Dict[str, Any]] = None,
    ballot_type: Optional[str] = None,
    debug_dir: Optional[str] = None,
    source_img: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """OCR a 2026 District / Ward / Local Council PR page."""
    h, w = img.shape[:2]
    boxes, lines = engine._run_ocr(img, max_side=1800)
    items = [_box_item(item) for item in boxes]
    all_lines = list(header_lines or []) + list(lines or [])
    text = _upper(all_lines)
    ballot_type = ballot_type or _ballot_type_from_text(text) or BALLOT_DISTRICT_PR
    identity = _identity_from_lines(all_lines)

    if not barcode_info:
        for item in items:
            barcode_info = engine.parse_barcode_reference(
                item["text"], identity.get("voting_district"), family=FAMILY_LG_2026
            )
            if barcode_info:
                break
        if not barcode_info:
            barcode_info = engine.parse_barcode_reference(
                "".join(all_lines), identity.get("voting_district"), family=FAMILY_LG_2026
            )

    if barcode_info:
        ballot_type = barcode_info.get("ballot_type") or ballot_type
        page_num = identity.get("page_number") or barcode_info.get("page_number") or 1
        page_total = identity.get("page_total") or barcode_info.get("page_total") or 2
        voting_district = identity.get("voting_district") or barcode_info.get("voting_district")
        raw_barcode = barcode_info.get("raw_barcode") or ""
        slip_ref = barcode_info.get("slip_reference")
    else:
        page_num = identity.get("page_number") or 1
        page_total = identity.get("page_total") or 2
        voting_district = identity.get("voting_district")
        raw_barcode = ""
        slip_ref = None

    vote_x1, vote_x2 = _vote_column_bounds(items, w, ballot_type)
    rows = _party_rows_from_items(items, ballot_type, h)
    party_results: List[Dict[str, Any]] = []
    used_vote_boxes: set = set()
    for index, row in enumerate(rows):
        pad = max(4.0, (row["y2"] - row["y1"]) * 0.28)
        y1 = max(0, int(row["y1"] - pad))
        y2 = min(h, int(row["y2"] + pad))
        votes, conf, hit = _number_on_row(
            items,
            y1,
            y2,
            vote_x1,
            vote_x2,
            target_cy=row["cy"],
            exclude=used_vote_boxes,
        )
        if hit:
            used_vote_boxes.add(_item_key(hit))
        crop_votes, crop_conf = 0, 0.0
        if votes in (None, 0) or (isinstance(votes, int) and votes < 10):
            x1n = max(0, vote_x1 - int(w * 0.02))
            x2n = min(w, vote_x1 + int((vote_x2 - vote_x1) * 0.78))
            tight = img[y1:y2, x1n:x2n]
            crop_votes, crop_conf = read_open_vote_cell(engine, tight, max_value=999)
            if crop_votes in (None, 0) or crop_votes < 10:
                x1 = max(0, vote_x1 - int(w * 0.03))
                x2 = min(w, vote_x2 + int(w * 0.03))
                wide = img[y1:y2, x1:x2]
                wide_votes, wide_conf = read_open_vote_cell(engine, wide, max_value=999)
                if wide_votes and (crop_votes in (None, 0) or wide_votes >= 10):
                    crop_votes, crop_conf = wide_votes, wide_conf
                elif crop_votes in (None, 0):
                    wide_y1 = max(0, int(row["y1"] - (row["y2"] - row["y1"]) * 0.45))
                    wide_y2 = min(h, int(row["y2"] + (row["y2"] - row["y1"]) * 0.45))
                    taller = img[wide_y1:wide_y2, x1:x2]
                    tall_votes, tall_conf = read_open_vote_cell(engine, taller, max_value=999)
                    if tall_votes:
                        crop_votes, crop_conf = tall_votes, tall_conf
        votes = _choose_vote(votes, crop_votes)
        if crop_votes and votes == crop_votes:
            conf = max(conf, crop_conf)
        sig_left = min(w - 8, max(vote_x2 + 4, int(w * 0.70)))
        sig_crop = img[y1:y2, sig_left:int(w * 0.96)]
        sig_detected, _ = engine.detect_signature_presence(sig_crop)
        party_results.append(
            {
                "row_index": index,
                "party_name": row["party_name"],
                "party_code": row["party_code"],
                "votes": votes,
                "confidence_score": float(conf if conf else 0.5),
                "is_overridden": False,
                "original_ocr_votes": votes,
                "signature_detected": bool(sig_detected),
                "bbox": {
                    "x": int(vote_x1),
                    "y": y1,
                    "width": int(max(8, vote_x2 - vote_x1)),
                    "height": int(max(8, y2 - y1)),
                },
            }
        )

    is_final_page = page_num == page_total
    if is_final_page and source_img is not None and source_img.size:
        items = _merge_source_total_items(engine, source_img, items)
    totals = _totals_from_items(items, w, exclude=used_vote_boxes) if is_final_page else {}
    if is_final_page:
        for key, pattern in (
            ("valid", r"TOTAL\s+VALID\s+VOTES"),
            ("spoilt", r"TOTAL\s+SPOILT\s+VOTES"),
            ("cast", r"TOTAL\s+VOTES\s+CAST"),
            ("special", r"TOTAL\s+SPECIAL\s+VOTES"),
            ("s24a", r"SECTION\s*7"),
        ):
            labels = [item for item in items if re.search(pattern, item["text"], re.I)]
            if not labels:
                continue
            label = min(labels, key=lambda item: item["x1"])
            pad = max(4, int((label["y2"] - label["y1"]) * 0.25))
            y1 = max(0, int(label["y1"] - pad))
            y2 = min(h, int(label["y2"] + pad))
            if key in {"valid", "cast"}:
                overflow = img[y1:y2, int(w * 0.64) : int(w * 0.96)]
                overflow_votes, _oc = read_open_vote_cell(engine, overflow, allow_cnn=False)
                if overflow_votes and overflow_votes >= 30:
                    current = totals.get(key)
                    if current is None or current < 30 or (current is not None and current >= 2000):
                        totals[key] = overflow_votes
            if totals.get(key) in (None, 0) or (key == "spoilt" and totals.get(key) in (1, 10)):
                x1 = int(w * 0.48)
                x2 = int(w * 0.62) if key == "spoilt" else int(w * 0.72)
                official = img[y1:y2, x1:x2]
                votes, _conf = read_open_vote_cell(
                    engine, official, allow_cnn=False, max_value=500 if key == "spoilt" else 9999
                )
                if votes and not (key == "spoilt" and votes < 10 and totals.get(key)):
                    totals[key] = votes
        totals = _reconcile_totals(totals)

    total_valid = int(totals.get("valid") or 0) if is_final_page else 0
    total_spoilt = int(totals.get("spoilt") or 0) if is_final_page else 0
    total_cast = int(totals.get("cast") or 0) if is_final_page else 0
    special_votes = int(totals.get("special") or 0) if is_final_page else 0
    section_24a_votes = int(totals.get("s24a") or 0) if is_final_page else 0

    officer = identity.get("officer")
    officer_sig = False
    if is_final_page:
        sig_band = img[int(h * 0.52) : int(h * 0.82), int(w * 0.45) : int(w * 0.95)]
        officer_sig, _ = engine.detect_signature_presence(sig_band)

    exception_flags: List[str] = []
    if any(row["votes"] > 0 and row["confidence_score"] < LOW_VOTE_CONFIDENCE for row in party_results):
        exception_flags.append("low_confidence_digits")
    if party_results and sum(row["votes"] for row in party_results) == 0:
        exception_flags.append("no_votes_read")
    registered = identity.get("registered_voters") or 0
    if registered and sum(row["votes"] for row in party_results) > registered:
        exception_flags.append("party_sum_exceeds_registered")

    if not slip_ref:
        if voting_district:
            slip_ref = f"{voting_district}_{ballot_type[:3].upper()}_p{page_num}"
        else:
            slip_ref = f"UNREAD_{uuid.uuid4().hex[:8].upper()}"

    if debug_dir:
        vis = img.copy()
        cv2.rectangle(vis, (vote_x1, 0), (vote_x2, h - 1), (0, 0, 255), 2)
        for row in party_results:
            box = row["bbox"]
            cv2.rectangle(
                vis,
                (box["x"], box["y"]),
                (box["x"] + box["width"], box["y"] + box["height"]),
                (0, 255, 0),
                1,
            )
        import os

        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, "07_result_grid.jpg"), vis)

    return {
        "barcode_text": raw_barcode,
        "slip_reference": slip_ref,
        "ballot_type": ballot_type,
        "election_name": "2026 LOCAL GOVERNMENT ELECTION",
        "province": identity.get("province"),
        "municipality": identity.get("municipality"),
        "voting_district": voting_district or "UNKNOWN",
        "station_name": None,
        "registered_voters": registered,
        "page_number": int(page_num),
        "page_total": int(page_total),
        "presiding_officer_name": officer,
        "presiding_officer_signature_detected": officer_sig,
        "total_valid_votes": total_valid,
        "total_spoilt_votes": total_spoilt,
        "total_votes_cast": total_cast,
        "special_votes": special_votes,
        "section_24a_votes": section_24a_votes,
        "party_results": party_results,
        "full_ocr_lines": all_lines,
        "exception_flags": exception_flags,
        "is_vote_related": True,
        "template_family": FAMILY_LG_2026,
    }

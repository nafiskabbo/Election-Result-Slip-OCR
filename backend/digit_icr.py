"""Segmented 4-block result-column digit ICR for IEC tally slips.

IEC result slips write each party total as up to four handwritten digits in
dashed boxes: [d1][d2][d3][d4], left-aligned (trailing boxes stay empty).
Slashed zeros (Ø) count as 0.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

import cv2
import numpy as np

RESULT_BOXES = 4


def detect_table_row_lines(gray: np.ndarray, x1: int, x2: int, y1: int, y2: int) -> List[int]:
    """Return absolute Y positions of horizontal table rules in a band."""
    h, w = gray.shape[:2]
    y1 = max(0, min(h - 1, y1))
    y2 = max(y1 + 1, min(h, y2))
    x1 = max(0, min(w - 1, x1))
    x2 = max(x1 + 1, min(w, x2))
    roi = gray[y1:y2, x1:x2]
    if roi.size == 0:
        return []
    _, bw = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(24, (x2 - x1) // 8), 1))
    horiz = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    proj = horiz.sum(axis=1).astype(float)
    if proj.max() <= 0:
        return []
    proj_s = np.convolve(proj, np.ones(3) / 3.0, mode="same")
    thr = proj_s.max() * 0.25
    peaks: List[int] = []
    for y in range(1, len(proj_s) - 1):
        if proj_s[y] > thr and proj_s[y] >= proj_s[y - 1] and proj_s[y] >= proj_s[y + 1]:
            if not peaks or y - peaks[-1] > 6:
                peaks.append(y)
            elif proj_s[y] > proj_s[peaks[-1]]:
                peaks[-1] = y
    return [y + y1 for y in peaks]


def detect_result_column_bounds(gray: np.ndarray, y1: int, y2: int) -> Tuple[int, int]:
    """Locate the RESULT 4-box column from strong vertical rules."""
    h, w = gray.shape[:2]
    y1 = max(0, min(h - 1, y1))
    y2 = max(y1 + 1, min(h, y2))
    roi = gray[y1:y2, :]
    _, bw = cv2.threshold(roi, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(20, (y2 - y1) // 20)))
    vert = cv2.morphologyEx(bw, cv2.MORPH_OPEN, kernel)
    proj = vert.sum(axis=0).astype(float)
    proj_s = np.convolve(proj, np.ones(11) / 11.0, mode="same")
    thr = proj_s.max() * 0.30
    peaks: List[int] = []
    for x in range(1, len(proj_s) - 1):
        if proj_s[x] > thr and proj_s[x] >= proj_s[x - 1] and proj_s[x] >= proj_s[x + 1]:
            if not peaks or x - peaks[-1] > 18:
                peaks.append(x)
            elif proj_s[x] > proj_s[peaks[-1]]:
                peaks[-1] = x

    # Prefer the pair that sits in the right half and spans ~15–22% of width
    # (logo | RESULT | signature). Fallback to fixed ratios.
    best = None
    for i in range(len(peaks) - 1):
        for j in range(i + 1, len(peaks)):
            left, right = peaks[i], peaks[j]
            width_frac = (right - left) / float(w)
            mid = (left + right) / 2.0 / w
            if 0.12 <= width_frac <= 0.28 and 0.55 <= mid <= 0.78:
                score = -abs(width_frac - 0.18) - abs(mid - 0.69)
                if best is None or score > best[0]:
                    best = (score, left, right)
    if best:
        left, right = best[1], best[2]
        inset = max(2, int((right - left) * 0.02))
        return left + inset, right - inset
    return int(w * 0.605), int(w * 0.775)


def _cell_mask(cell: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    hh, ww = g.shape
    m = max(2, int(min(hh, ww) * 0.14))
    g = g[m : hh - m, m : ww - m]
    if g.size == 0:
        return np.zeros((40, 30), dtype=np.uint8)
    g = cv2.resize(g, (120, 160), interpolation=cv2.INTER_CUBIC)
    g = cv2.GaussianBlur(g, (3, 3), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    num, labels, stats, _ = cv2.connectedComponentsWithStats(th)
    out = np.zeros_like(th)
    for i in range(1, num):
        x, y, bw, bh, area = stats[i]
        if area < 35:
            continue
        aspect = bh / float(max(1, bw))
        # Drop thin vertical dashed dividers and short horizontal border crumbs.
        if bw <= 7 and aspect > 2.5:
            continue
        if bh <= 7 and bw > 35:
            continue
        out[labels == i] = 255
    return out


def _zones(comp: np.ndarray) -> List[float]:
    h, w = comp.shape
    zones = []
    for i in range(3):
        for j in range(3):
            z = comp[i * h // 3 : (i + 1) * h // 3, j * w // 3 : (j + 1) * w // 3]
            zones.append(cv2.countNonZero(z) / float(max(1, z.size)))
    return zones


def _component_stats(mask: np.ndarray):
    ink = cv2.countNonZero(mask)
    ratio = ink / float(max(1, mask.size))
    if ink < 70:
        return None
    num, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    if num <= 1:
        return None
    areas = stats[1:, cv2.CC_STAT_AREA]
    idx = 1 + int(np.argmax(areas))
    _, _, bw, bh, area = stats[idx]
    if area < 70:
        return None
    comp = (labels == idx).astype(np.uint8) * 255
    cnts, hier = cv2.findContours(comp, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    holes = 0
    if hier is not None:
        for i in range(len(cnts)):
            if hier[0][i][3] >= 0:
                holes += 1
    h, w = comp.shape
    cx = float(centroids[idx][0]) / w
    cy = float(centroids[idx][1]) / h
    aspect = bh / float(max(1, bw))
    zones = _zones(comp)
    mid = comp[int(0.42 * h) : int(0.58 * h), :]
    mid_ratio = cv2.countNonZero(mid) / float(max(1, mid.size))
    top = float(comp[: h // 3].sum())
    bot = float(comp[2 * h // 3 :].sum())
    return {
        "ratio": ratio,
        "area": int(area),
        "bw": int(bw),
        "bh": int(bh),
        "aspect": aspect,
        "holes": holes,
        "cx": cx,
        "cy": cy,
        "zones": zones,
        "mid_ratio": mid_ratio,
        "top_bot": top / max(1.0, bot),
        "width_frac": bw / float(w),
    }


def _is_noise(s: dict) -> bool:
    z = s["zones"]
    # Horizontal border remnant: ink only in the top band.
    if sum(z[0:3]) > 0.45 and sum(z[3:9]) < 0.18:
        return True
    # Horizontal border remnant: short fat blob spanning the cell width.
    if s["aspect"] < 0.35 and s["width_frac"] > 0.75:
        return True
    # Ink glued to the bottom rule only.
    if s["cy"] > 0.72 and sum(z[0:6]) < 0.08 and sum(z[6:9]) > 0.15:
        return True
    # Ink glued to the top rule only.
    if s["cy"] < 0.28 and sum(z[3:9]) < 0.08 and sum(z[0:3]) > 0.15:
        # Still allow a real digit that sits high (e.g. Ø); require flat aspect.
        if s["aspect"] < 0.55 or s["width_frac"] > 0.7:
            return True
    # Vertical edge remnant (signature bleed / dashed divider).
    right = z[2] + z[5] + z[8]
    left = z[0] + z[3] + z[6]
    if s["cx"] >= 0.78 and right > 0.55 and left < 0.25:
        return True
    if s["cx"] <= 0.22 and left > 0.55 and right < 0.25:
        return True
    # Too filled to be a single handwritten digit in a box.
    if s["ratio"] > 0.38:
        return True
    # Thin edge stroke mistaken for 1.
    if s["aspect"] >= 4.0 and (s["cx"] < 0.18 or s["cx"] > 0.82):
        return True
    return False


def classify_digit_mask(mask: np.ndarray) -> Tuple[Optional[int], float]:
    """Return (digit or None for empty, confidence)."""
    s = _component_stats(mask)
    if s is None:
        return None, 0.92
    if _is_noise(s):
        return None, 0.88

    z = s["zones"]
    aspect = s["aspect"]
    holes = s["holes"]
    cx = s["cx"]
    top_sum = sum(z[0:3])
    mid_sum = sum(z[3:6])
    bot_sum = sum(z[6:9])

    # 1 — tall thin stroke (may sit slightly left in the box).
    if aspect >= 4.0 and 0.14 <= cx <= 0.78 and s["width_frac"] < 0.32:
        return 1, 0.90

    # 8 vs slashed-zero: a Ø slash drives mid_ratio up; a true 8 is two stacked loops.
    if 0.9 <= aspect <= 2.5 and 0.25 <= cx <= 0.75 and holes >= 1:
        stacked = z[1] > 0.12 and z[7] > 0.12 and z[4] > 0.10
        slashed = s["mid_ratio"] > 0.22 and holes >= 2
        if slashed:
            return 0, 0.88
        if holes >= 2 and stacked and s["mid_ratio"] <= 0.22:
            return 8, 0.86
        if holes == 1 and stacked and aspect >= 1.45 and s["mid_ratio"] <= 0.20:
            return 8, 0.74

    # 0 / ordinary or lightly-slashed zero.
    if holes >= 1 and 0.85 <= aspect <= 2.2 and 0.25 <= cx <= 0.75:
        ring = (z[0] + z[2] + z[6] + z[8]) >= (z[1] + z[7]) * 0.65
        if holes >= 2:
            return 0, 0.86
        if holes == 1 and (s["mid_ratio"] > 0.16 or ring):
            return 0, 0.84
        if ring:
            return 0, 0.78

    # 5 before 4: empty top band, ink mid/low with bottom-right weight.
    # Reject flat border fragments (already mostly handled in _is_noise).
    if (
        holes == 0
        and top_sum < 0.12
        and mid_sum + bot_sum > 0.30
        and 0.55 <= aspect < 2.1
        and s["width_frac"] < 0.85
    ):
        if z[8] > 0.10 or (z[5] > 0.05 and bot_sum > 0.12):
            return 5, 0.76

    # 7 — hook / crossbar; bottom-left usually open.
    if holes == 0 and aspect < 2.2 and z[6] < 0.10:
        if s["top_bot"] > 1.15 and (z[1] + z[2]) > 0.05:
            return 7, 0.74
        # Compact handwritten 7 with little top bar: mid-center + mid-bottom stem.
        if top_sum < 0.15 and z[4] > 0.20 and z[7] > 0.12 and z[3] < 0.20 and z[8] < 0.08:
            return 7, 0.66

    # 4 — open top-right, strong mid cross, left stem.
    if holes == 0 and 1.1 <= aspect <= 2.3 and z[2] < 0.08 and z[4] > 0.15:
        if z[3] + z[6] > 0.28 and top_sum > 0.02:
            return 4, 0.74

    # 2 — more ink bottom-right / mid.
    if holes == 0 and aspect < 1.9 and z[8] > 0.15 and z[0] < 0.12 and s["top_bot"] < 1.1:
        return 2, 0.55

    # 3 — right-heavy stack.
    if holes == 0 and aspect < 2.0 and z[2] + z[5] + z[8] > z[0] + z[3] + z[6] + 0.15:
        return 3, 0.50

    # 6 / 9 only when clearly bottom- or top-heavy (avoid eating zeros).
    if holes == 1 and aspect < 2.0 and 0.3 <= cx <= 0.7:
        if z[7] > z[1] + 0.12 and bot_sum > top_sum + 0.15:
            return 6, 0.55
        if z[1] > z[7] + 0.12 and top_sum > bot_sum + 0.15:
            return 9, 0.55
        return 0, 0.60

    # Prefer empty over inventing a zero for leftover blobs.
    if 0.04 <= s["ratio"] <= 0.20 and 0.3 <= cx <= 0.7 and aspect < 2.5 and holes >= 1:
        return 0, 0.45

    return None, 0.35


def digits_to_votes(digits: List[Optional[int]], *, leading_zeros: bool = False) -> Tuple[int, float]:
    """4-box digits → integer votes + confidence.

    Empty leading boxes (no written zero) are ignored so right-aligned totals
    like ``[_, _, _, 9]`` read as 9 and ``[_, 8, 1, 6]`` as 816.

    ``leading_zeros=True`` (CNN) also drops leading literal 0s that come from
    Ø/blank cells misclassified as zero.
    """
    raw = list(digits[:RESULT_BOXES])
    while len(raw) < RESULT_BOXES:
        raw.append(None)

    idxs = [i for i, d in enumerate(raw) if d is not None]
    if not idxs:
        return 0, 0.90

    # Interior gaps are almost always dashed-line noise, not real digits.
    for i in range(idxs[0], idxs[-1] + 1):
        if raw[i] is None:
            return 0, 0.40

    vals = [int(raw[i]) for i in range(idxs[0], idxs[-1] + 1)]

    # Lone 5–9 only in the leftmost box is nearly always a misread slashed zero (Ø).
    # A lone digit in a later box (no zero in front) is a real single-digit total.
    if len(vals) == 1 and vals[0] in {5, 6, 7, 8, 9} and idxs[0] == 0:
        return 0, 0.55

    # Drop leading zeros so Ø/blank-as-0 does not inflate place value.
    # Empty leading boxes stay None and are already excluded via idxs.
    while len(vals) > 1 and vals[0] == 0:
        vals.pop(0)

    if all(p == 0 for p in vals):
        return 0, 0.88
    return int("".join(str(p) for p in vals)), 0.80


def read_four_blocks(
    row_bgr: np.ndarray,
    backend: str = "heuristic",
) -> Tuple[int, float, List[Optional[int]]]:
    """OCR one RESULT row that contains four digit boxes.

    backend:
      - \"heuristic\": topology ICR (production hybrid path)
      - \"cnn\": MNIST/EMNIST+blank ONNX digit classifier
      - \"rapid\": skip cell ICR (caller uses RapidOCR only)
    """
    if backend == "rapid":
        return 0, 0.90, [None, None, None, None]
    if row_bgr is None or row_bgr.size == 0:
        return 0, 0.2, [None, None, None, None]
    h, w = row_bgr.shape[:2]
    digits: List[Optional[int]] = []
    confs: List[float] = []
    use_cnn = backend == "cnn"
    for c in range(RESULT_BOXES):
        x1 = int(w * c / RESULT_BOXES)
        x2 = int(w * (c + 1) / RESULT_BOXES)
        cell = row_bgr[:, x1:x2]
        if use_cnn:
            from backend.digit_cnn import classify_cell_cnn

            digit, conf = classify_cell_cnn(cell)
        else:
            mask = _cell_mask(cell)
            digit, conf = classify_digit_mask(mask)
        digits.append(digit)
        confs.append(conf)
    votes, base = digits_to_votes(digits, leading_zeros=use_cnn)
    conf = float(sum(confs) / max(1, len(confs)))
    # Prefer lower confidence when any cell was uncertain.
    conf = min(conf, base)
    if votes > 0 and conf < 0.45:
        conf = max(0.30, conf)
    return votes, max(0.25, min(0.95, conf)), digits


def align_rows_to_template(
    row_lines: List[int],
    num_rows: int,
) -> List[Tuple[int, int]]:
    """Map detected horizontal rules onto the expected party row count."""
    if num_rows <= 0:
        return []
    if len(row_lines) >= num_rows + 1:
        # Pick the densest contiguous band with num_rows intervals.
        best = None
        for i in range(0, len(row_lines) - num_rows):
            band = row_lines[i : i + num_rows + 1]
            gaps = np.diff(band)
            if gaps.min() <= 0:
                continue
            score = -float(np.std(gaps)) - abs(float(np.median(gaps)) - float(np.mean(gaps)))
            if best is None or score > best[0]:
                best = (score, band)
        if best:
            band = best[1]
            return [(int(band[i]), int(band[i + 1])) for i in range(num_rows)]

    if len(row_lines) >= 2:
        top, bottom = row_lines[0], row_lines[-1]
        step = (bottom - top) / float(num_rows)
        return [(int(top + i * step), int(top + (i + 1) * step)) for i in range(num_rows)]
    return []

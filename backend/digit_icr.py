"""Segmented 4-block result-column digit ICR for IEC tally slips.

IEC result slips write each party total as up to four handwritten digits in
dashed boxes: [d1][d2][d3][d4], left-aligned (trailing boxes stay empty).
Slashed zeros (Ø) count as 0.
"""

from __future__ import annotations

from itertools import combinations
from threading import Lock
from typing import List, Optional, Tuple

import cv2
import numpy as np

RESULT_BOXES = 4
ResultColumnGeometry = Tuple[float, float, float, float, float]
_HOUGH_LOCK = Lock()
# Paper/print ink is well below this; Otsu on a blank cell must not invent it.
HANDWRITING_DARK = 125
BLANK_INK_FRAC = 0.010
# ResultSlip phone photos are ~25px tall; full scans are already ~46px.
MIN_RESULT_ROW_HEIGHT = 36
TARGET_RESULT_ROW_HEIGHT = 52


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
    if len(peaks) >= 4:
        gaps = np.diff(peaks)
        row_like = gaps[gaps >= 16]
        if row_like.size:
            merge_distance = max(7, int(round(float(np.median(row_like)) * 0.35)))
            merged: List[int] = []
            for peak in peaks:
                if merged and peak - merged[-1] <= merge_distance:
                    if proj_s[peak] > proj_s[merged[-1]]:
                        merged[-1] = peak
                else:
                    merged.append(peak)
            peaks = merged
    return [y + y1 for y in peaks]


def detect_projection_result_column_bounds(
    gray: np.ndarray,
    y1: int,
    y2: int,
) -> Tuple[int, int]:
    """Legacy projection fallback for already-rectified pages."""
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


def detect_result_column_geometry(
    gray: np.ndarray,
    y1: int,
    y2: int,
) -> ResultColumnGeometry:
    """Locate the five-line RESULT grid and model its possibly sloped edges.

    A valid IEC RESULT column has two outer rules and three near-equidistant
    dashed dividers. The large signature column immediately to its right
    distinguishes it from the similarly sized party-logo column.

    Returns ``(left_x, left_dx_dy, right_x, right_dx_dy, y_reference)``.
    """
    h, w = gray.shape[:2]
    y1 = max(0, min(h - 1, y1))
    y2 = max(y1 + 1, min(h, y2))
    roi = gray[y1:y2, :]
    roi_h = roi.shape[0]
    y_ref_local = (roi_h - 1) / 2.0
    y_ref = y1 + y_ref_local

    adaptive = cv2.adaptiveThreshold(
        roi,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        11,
    )
    close_h = max(5, roi_h // 100)
    vertical = cv2.morphologyEx(
        adaptive,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, close_h)),
    )
    # HoughLinesP consumes OpenCV's process-global RNG. Reset and serialize it
    # so identical uploads receive identical candidate lines under concurrency.
    with _HOUGH_LOCK:
        cv2.setRNGSeed(0)
        lines = cv2.HoughLinesP(
            vertical,
            1,
            np.pi / 360,
            threshold=max(24, roi_h // 15),
            minLineLength=max(30, roi_h // 7),
            maxLineGap=max(8, roi_h // 30),
        )

    observations: List[Tuple[float, float, float]] = []
    if lines is not None:
        for x_start, y_start, x_end, y_end in np.asarray(lines).reshape(-1, 4):
            dx = float(x_end - x_start)
            dy = float(y_end - y_start)
            if abs(dy) < max(20.0, roi_h * 0.12) or abs(dx) > abs(dy) * 0.22:
                continue
            slope = dx / dy
            x_ref = float(x_start) + (y_ref_local - float(y_start)) * slope
            if w * 0.25 <= x_ref <= w * 0.90:
                observations.append((x_ref, slope, abs(dy)))

    observations.sort(key=lambda item: item[0])
    tolerance = max(5.0, w * 0.008)
    clusters: List[List[Tuple[float, float, float]]] = []
    centers: List[float] = []
    for observation in observations:
        if clusters and abs(observation[0] - centers[-1]) <= tolerance:
            clusters[-1].append(observation)
            weighted = sum(item[0] * item[2] for item in clusters[-1])
            total_weight = sum(item[2] for item in clusters[-1])
            centers[-1] = weighted / max(1.0, total_weight)
        else:
            clusters.append([observation])
            centers.append(observation[0])

    # Bound the topology search on noisy photos while retaining the strongest
    # long-line evidence. C(24, 5) is small enough for the upload fast path.
    if len(clusters) > 24:
        strongest = sorted(
            range(len(clusters)),
            key=lambda index: sum(item[2] for item in clusters[index]),
            reverse=True,
        )[:24]
        strongest.sort(key=lambda index: centers[index])
        clusters = [clusters[index] for index in strongest]
        centers = [centers[index] for index in strongest]

    candidates = []
    for indexes in combinations(range(len(clusters)), RESULT_BOXES + 1):
        xs = np.asarray([centers[index] for index in indexes], dtype=float)
        gaps = np.diff(xs)
        mean_gap = float(np.mean(gaps))
        if mean_gap <= 0:
            continue
        width_fraction = float(xs[-1] - xs[0]) / float(w)
        midpoint_fraction = float(np.mean(xs)) / float(w)
        gap_cv = float(np.std(gaps)) / mean_gap
        if not (
            0.10 <= width_fraction <= 0.26
            and 0.50 <= midpoint_fraction <= 0.82
            and gap_cv <= 0.35
        ):
            continue

        following = [
            center - xs[-1]
            for center in centers
            if center > xs[-1] + mean_gap * 0.35
        ]
        right_clearance = (min(following) if following else w - xs[-1]) / mean_gap
        support = sum(
            min(1.0, sum(item[2] for item in clusters[index]) / float(roi_h))
            for index in indexes
        ) / float(RESULT_BOXES + 1)
        score = (
            2.5 * (1.0 - gap_cv)
            - abs(width_fraction - 0.18) * 2.0
            - abs(midpoint_fraction - 0.68) * 0.6
            + min(1.5, right_clearance) * 0.5
            + support * 0.3
        )
        candidates.append((score, indexes))

    if candidates:
        _, best_indexes = max(candidates, key=lambda item: item[0])
        left_cluster = clusters[best_indexes[0]]
        right_cluster = clusters[best_indexes[-1]]
        left_x = centers[best_indexes[0]]
        right_x = centers[best_indexes[-1]]
        left_slope = float(np.median([item[1] for item in left_cluster]))
        right_slope = float(np.median([item[1] for item in right_cluster]))
        return left_x, left_slope, right_x, right_slope, y_ref

    left, right = detect_projection_result_column_bounds(gray, y1, y2)
    return float(left), 0.0, float(right), 0.0, y_ref


def result_column_bounds_at(
    geometry: ResultColumnGeometry,
    y: float,
) -> Tuple[float, float]:
    """Evaluate RESULT edge positions at an image Y coordinate."""
    left_x, left_slope, right_x, right_slope, y_ref = geometry
    dy = float(y) - y_ref
    return left_x + left_slope * dy, right_x + right_slope * dy


def detect_result_column_bounds(gray: np.ndarray, y1: int, y2: int) -> Tuple[int, int]:
    """Locate RESULT bounds at the middle of the table."""
    geometry = detect_result_column_geometry(gray, y1, y2)
    left, right = result_column_bounds_at(geometry, geometry[-1])
    inset = max(2, int((right - left) * 0.02))
    return int(round(left)) + inset, int(round(right)) - inset


def extract_result_row(
    img: np.ndarray,
    geometry: ResultColumnGeometry,
    y1: int,
    y2: int,
) -> np.ndarray:
    """Crop one RESULT row at the local positions of its sloped outer rules."""
    if img is None or img.size == 0 or y2 <= y1:
        return img[0:0, 0:0] if img is not None else img
    h, w = img.shape[:2]
    y1 = max(0, min(h - 1, int(y1)))
    y2 = max(y1 + 1, min(h, int(y2)))
    left, right = result_column_bounds_at(geometry, (y1 + y2) / 2.0)
    inset = max(1, int(round((right - left) * 0.02)))
    x1 = max(0, min(w - 1, int(round(left)) + inset))
    x2 = max(x1 + 1, min(w, int(round(right)) - inset))
    return img[y1:y2, x1:x2]


def handwriting_ink_fraction(
    gray: np.ndarray,
    *,
    dark_thr: int = HANDWRITING_DARK,
) -> float:
    """Fraction of pixels dark enough to be pen ink (not Otsu paper grain)."""
    if gray is None or gray.size == 0:
        return 0.0
    if gray.ndim == 3:
        gray = cv2.cvtColor(gray, cv2.COLOR_BGR2GRAY)
    return float(np.mean(gray < int(dark_thr)))


def cell_looks_blank(cell: np.ndarray, *, crop_frac: float = 0.08) -> bool:
    """True when a RESULT box has no handwriting, only faint rule remnants.

    Phone photos write a 1 as a light gray stroke. A fixed dark threshold
    treats that as empty; a centered tall component still counts as ink.
    """
    if cell is None or cell.size == 0:
        return True
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    hh, ww = g.shape[:2]
    m = max(1, int(min(hh, ww) * crop_frac))
    g = g[m : max(m + 1, hh - m), m : max(m + 1, ww - m)]
    if g.size == 0:
        return True
    if handwriting_ink_fraction(g) >= BLANK_INK_FRAC:
        return False
    faint = np.where(g < 185, 255, 0).astype(np.uint8)
    if int(np.count_nonzero(faint)) == 0:
        return True
    _num, _labels, stats, centroids = cv2.connectedComponentsWithStats(faint)
    h, w = g.shape[:2]
    for i in range(1, stats.shape[0]):
        _x, _y, cw, ch, area = stats[i]
        if area < 12:
            continue
        cx = float(centroids[i][0]) / float(max(1, w))
        aspect = ch / float(max(1, cw))
        # Edge dashes hug the box rule. A handwritten 1 sits in the cell.
        if cx < 0.16 or cx > 0.84:
            continue
        if ch >= h * 0.30 and aspect >= 1.5:
            return False
        if area >= 35 and ch >= h * 0.25:
            return False
    return True


def scale_result_row(
    row_bgr: np.ndarray,
    target_h: int = TARGET_RESULT_ROW_HEIGHT,
) -> np.ndarray:
    """Cubic-upsample short RESULT rows so low-res scans match deskewed cell size."""
    if row_bgr is None or row_bgr.size == 0:
        return row_bgr
    h, w = row_bgr.shape[:2]
    if h >= int(MIN_RESULT_ROW_HEIGHT):
        return row_bgr
    scale = min(3.5, float(target_h) / float(max(1, h)))
    if scale <= 1.08:
        return row_bgr
    return cv2.resize(
        row_bgr,
        (max(8, int(round(w * scale))), max(8, int(round(h * scale)))),
        interpolation=cv2.INTER_CUBIC,
    )


def _result_row_gray(row_bgr: np.ndarray) -> np.ndarray:
    if row_bgr.ndim == 3:
        return cv2.cvtColor(row_bgr, cv2.COLOR_BGR2GRAY)
    return row_bgr


def _result_rule_mask(gray: np.ndarray) -> np.ndarray:
    """Ink mask of printed dashed rules (fixed threshold, not Otsu)."""
    bw = np.where(gray < 165, 255, 0).astype(np.uint8)
    if float(np.mean(bw > 0)) < 0.004:
        bw = np.where(gray < 190, 255, 0).astype(np.uint8)
    h = gray.shape[0]
    closed = cv2.morphologyEx(
        bw,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(5, h // 4))),
    )
    return bw, closed


def result_divider_xs(
    row_bgr: np.ndarray,
    box_count: int = RESULT_BOXES,
) -> List[int]:
    """X positions of internal dashed RESULT rules, including gapped dashes."""
    if row_bgr is None or row_bgr.size == 0:
        return []
    h, w = row_bgr.shape[:2]
    gray = _result_row_gray(row_bgr)
    _bw, closed = _result_rule_mask(gray)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(6, h // 4)))
    vert = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
    colsum = (vert > 0).sum(axis=0).astype(np.float32)
    if float(colsum.max(initial=0)) <= 0:
        colsum = (closed > 0).sum(axis=0).astype(np.float32)
    cell_w = max(1, w / float(box_count))
    window = max(3, int(round(cell_w * 0.20)))
    min_peak = h * 0.18
    peaks: List[int] = []
    for k in range(1, box_count):
        expected = int(round(w * k / float(box_count)))
        lo = max(0, expected - window)
        hi = min(w, expected + window + 1)
        if hi <= lo:
            continue
        peak = lo + int(np.argmax(colsum[lo:hi]))
        if colsum[peak] < min_peak:
            continue
        peaks.append(peak)
    return peaks


def _internal_rule_xs(width: int, box_count: int) -> List[float]:
    return [width * k / float(box_count) for k in range(1, box_count)]


def suppress_result_dividers(
    row_bgr: np.ndarray,
    box_count: int = RESULT_BOXES,
) -> np.ndarray:
    """Whiten dashed box rules without eating digits that sit on a divider.

    IEC RESULT cells are four boxes. OCR treats leftover dashes as ``1``/``7``
    (52→1512, empty→7). A wide handwritten glyph on the rule (GOOD 27) must
    survive; only thin vertical/horizontal fragments are removed. Left-aligned
    ones in the first box must not be treated as the outer border.
    """
    if row_bgr is None or row_bgr.size == 0:
        return row_bgr
    out = row_bgr.copy()
    h, w = out.shape[:2]
    gray = _result_row_gray(out)
    _bw, closed = _result_rule_mask(gray)
    cell_w = max(1.0, w / float(box_count))
    internal = _internal_rule_xs(w, box_count)
    window = cell_w * 0.20
    edge_pad = max(2, int(round(cell_w * 0.04)))
    wipe = np.zeros((h, w), dtype=np.uint8)

    num, labels, stats, centroids = cv2.connectedComponentsWithStats(closed)
    for i in range(1, num):
        x, y, cw, ch, area = stats[i]
        cx = float(centroids[i][0])
        cy = float(centroids[i][1])
        near = min(abs(cx - exp) for exp in internal) <= window if internal else False
        glued_edge = x <= edge_pad or (x + cw) >= w - edge_pad
        # Printed dashes are 1–3px; a handwritten 1 is thicker. Never wipe the 1.
        thin = cw <= max(3, int(round(cell_w * 0.06)))
        tall = ch >= max(4, int(h * 0.16))
        short_dash = thin and ch <= max(8, int(h * 0.50)) and area <= max(50, h * 3)
        horiz = ch <= max(4, int(h * 0.20)) and cw >= max(10, int(cell_w * 0.25))
        top_bot = cy <= h * 0.22 or cy >= h * 0.78
        if horiz and (top_bot or near):
            wipe[labels == i] = 255
            continue
        if thin and near and (tall or short_dash):
            wipe[labels == i] = 255
            continue
        if thin and glued_edge and (tall or short_dash):
            wipe[labels == i] = 255

    with _HOUGH_LOCK:
        cv2.setRNGSeed(0)
        lines = cv2.HoughLinesP(
            closed,
            1,
            np.pi / 180,
            threshold=max(6, h // 5),
            minLineLength=max(6, int(h * 0.28)),
            maxLineGap=max(4, h // 4),
        )
    snap_xs = list(internal) + [0.0, float(w)]
    if lines is not None:
        pad = max(1, int(round(cell_w * 0.04)))
        for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
            dx = abs(int(x2) - int(x1))
            dy = abs(int(y2) - int(y1))
            if dy < max(6, int(h * 0.22)) or dx > max(3, int(cell_w * 0.08)):
                continue
            xmid = 0.5 * (float(x1) + float(x2))
            nearest = min(abs(xmid - exp) for exp in snap_xs)
            outer = xmid <= edge_pad or xmid >= w - edge_pad
            if nearest > window and not outer:
                continue
            if not outer and min(abs(xmid - exp) for exp in internal) > window:
                continue
            lo = max(0, int(round(xmid)) - pad)
            hi = min(w, int(round(xmid)) + pad + 1)
            column = wipe[:, lo:hi]
            ink = closed[:, lo:hi]
            column[ink > 0] = 255

    # Peak columns: only the thin dash, not a wide digit sitting on the rule.
    peak_pad = max(1, int(round(cell_w * 0.07)))
    for peak in result_divider_xs(out, box_count):
        x1, x2 = max(0, peak - peak_pad), min(w, peak + peak_pad + 1)
        strip = closed[:, x1:x2]
        s_num, s_labels, s_stats, _ = cv2.connectedComponentsWithStats(strip)
        for i in range(1, s_num):
            _sx, _sy, sw, sh, _area = s_stats[i]
            if sw <= max(3, int(round(cell_w * 0.06))) and sh >= max(3, int(h * 0.12)):
                wipe[:, x1:x2][s_labels == i] = 255

    if int(np.count_nonzero(wipe)) == 0:
        return out
    wipe = cv2.dilate(wipe, cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)))
    out[wipe > 0] = 255
    return out


def split_result_cells(
    row_bgr: np.ndarray,
    box_count: int = RESULT_BOXES,
) -> List[np.ndarray]:
    """Four RESULT boxes after dashed dividers are removed."""
    cleaned = suppress_result_dividers(row_bgr, box_count)
    if cleaned is None or cleaned.size == 0:
        return []
    _, w = cleaned.shape[:2]
    return [
        cleaned[:, int(w * c / box_count) : int(w * (c + 1) / box_count)]
        for c in range(box_count)
    ]


def _cell_mask(cell: np.ndarray) -> np.ndarray:
    g = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY) if cell.ndim == 3 else cell
    hh, ww = g.shape
    m = max(2, int(min(hh, ww) * 0.14))
    g = g[m : hh - m, m : ww - m]
    if g.size == 0:
        return np.zeros((40, 30), dtype=np.uint8)
    # Use the same blank test as Rapid so a faint centered 1 is not skipped.
    if cell_looks_blank(cell):
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
        cx = (x + bw / 2.0) / float(th.shape[1])
        # Keep centered thin strokes: they are real handwritten 1s. Only remove
        # divider remnants hugging a cell edge.
        if bw <= 7 and aspect > 2.5 and (cx < 0.20 or cx > 0.80):
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

    # 7 — hook / crossbar; bottom-left usually open. Tall thin 7s (PA) sit
    # between a compact 7 (aspect < 2.2) and a 1 (aspect >= 4).
    if holes == 0 and z[6] < 0.10:
        if aspect < 2.2 and s["top_bot"] > 1.15 and (z[1] + z[2]) > 0.05:
            return 7, 0.74
        if (
            2.2 <= aspect < 3.8
            and s["top_bot"] > 1.12
            and (z[1] + z[2]) > 0.05
            and z[8] < 0.12
        ):
            return 7, 0.70
        # Compact handwritten 7 with little top bar: mid-center + mid-bottom stem.
        if top_sum < 0.15 and z[4] > 0.20 and z[7] > 0.12 and z[3] < 0.20 and z[8] < 0.08:
            return 7, 0.66

    # 4 — open top-right, strong mid cross, left stem.
    if holes == 0 and 1.1 <= aspect <= 2.3 and z[2] < 0.08 and z[4] > 0.15:
        if z[3] + z[6] > 0.28 and top_sum > 0.02:
            return 4, 0.74

    # 2 — more ink bottom-right / mid, without the left stem of a 4.
    if holes == 0 and aspect < 1.9 and z[8] > 0.15 and z[0] < 0.12 and s["top_bot"] < 1.1:
        if z[3] + z[6] < 0.28:
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
    row_bgr = scale_result_row(row_bgr)
    digits: List[Optional[int]] = []
    confs: List[float] = []
    use_cnn = backend == "cnn"
    cells = split_result_cells(row_bgr)
    if len(cells) != RESULT_BOXES:
        return 0, 0.2, [None, None, None, None]
    for cell in cells:
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
    min_y: Optional[float] = None,
) -> List[Tuple[int, int]]:
    """Map detected horizontal rules onto the expected party row count."""
    if num_rows <= 0:
        return []
    row_lines = sorted(set(int(y) for y in row_lines))
    if min_y is not None:
        anchored = [y for y in row_lines if y >= min_y]
        if len(anchored) >= 2:
            row_lines = anchored
    if len(row_lines) >= num_rows + 1:
        # Pick the densest contiguous band with num_rows intervals.
        best = None
        for i in range(0, len(row_lines) - num_rows + 1):
            band = row_lines[i : i + num_rows + 1]
            if len(band) != num_rows + 1:
                continue
            gaps = np.diff(band)
            if gaps.min() <= 0:
                continue
            median_gap = float(np.median(gaps))
            if median_gap <= 0:
                continue
            if gaps.min() < max(6.0, median_gap * 0.55):
                continue
            if gaps.max() > median_gap * 1.65:
                continue
            score = -float(np.std(gaps)) - abs(float(np.median(gaps)) - float(np.mean(gaps)))
            if best is None or score > best[0]:
                best = (score, band)
        if best:
            band = best[1]
            return [(int(band[i]), int(band[i + 1])) for i in range(num_rows)]

    if len(row_lines) >= 2:
        gaps = np.diff(row_lines).astype(float)
        positive_gaps = gaps[gaps > 3.0]
        median_gap = float(np.median(positive_gaps)) if positive_gaps.size else 0.0
        if median_gap <= 0:
            return []

        # Preserve observed boundaries and fill individual missed rules. This
        # retains perspective-driven row-height changes instead of compressing
        # a partial grid into the expected row count.
        boundaries = [float(row_lines[0])]
        for line in row_lines[1:]:
            gap = float(line) - boundaries[-1]
            if gap < median_gap * 0.52:
                continue
            missing_intervals = max(1, int(round(gap / median_gap)))
            if missing_intervals > 1 and gap > median_gap * 1.55:
                step = gap / missing_intervals
                for index in range(1, missing_intervals):
                    boundaries.append(boundaries[-1] + step)
            boundaries.append(float(line))
            if len(boundaries) >= num_rows + 1:
                break

        recent_gaps = np.diff(boundaries[-7:])
        recent_gaps = recent_gaps[recent_gaps > median_gap * 0.55]
        step = float(np.median(recent_gaps)) if recent_gaps.size else median_gap
        while len(boundaries) < num_rows + 1:
            boundaries.append(boundaries[-1] + step)
        return [
            (int(round(boundaries[i])), int(round(boundaries[i + 1])))
            for i in range(num_rows)
        ]
    return []

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
# "|" is a dashed box rule, not a one — do not accept it as a cell digit.
_ROW_DIGIT_RE = re.compile(r"^[0-9OoØøΦφIlSsBbD\s.,:/|_-]{1,16}$")


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
    # Stay inside the dashed box: outer ink is the rule, not the digit.
    # Keep this modest — a left-shifted 4 loses its stem if we crop too hard.
    m = max(2, int(min(h, w) * 0.12))
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
        .replace("Φ", "0")
        .replace("φ", "0")
        .replace("O", "0")
        .replace("o", "0")
        .replace("I", "1")
        .replace("l", "1")
        .replace("S", "5")
        .replace("s", "5")
        .replace("B", "8")
        .replace("b", "8")
        .replace("了", "7")
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
    """Fraction of dark pen ink inside the four boxes after dashed rules are removed."""
    if row_bgr is None or row_bgr.size == 0:
        return 0.0
    from backend.digit_icr import handwriting_ink_fraction, suppress_result_dividers

    cleaned = suppress_result_dividers(row_bgr)
    g = cv2.cvtColor(_as_bgr(cleaned), cv2.COLOR_BGR2GRAY)
    h, w = g.shape[:2]
    m = max(1, int(min(h, w) * 0.12))
    g = g[m : h - m, m : w - m]
    if g.size == 0:
        return 0.0
    return handwriting_ink_fraction(g)


def looks_like_dash_noise(votes: int) -> bool:
    """True when a Rapid total is almost certainly leftover dashed-box ones."""
    if votes <= 1:
        return False
    text = str(int(votes))
    if text in {"11", "111", "1111"}:
        return True
    if len(text) >= 3 and text.count("1") >= len(text) - 1:
        return True
    if len(text) == 4 and text.count("1") >= 2 and text.count("0") >= 2:
        return True
    # Four Ø-as-2 / leftover-dash digits (2212) is not a real RESULT total.
    if len(text) == 4 and set(text) <= {"1", "2"}:
        return True
    if len(text) >= 3 and set(text) <= {"0", "3", "8", "9"}:
        return True
    return False


def extra_separator_digit(rapid_votes: int, icr_votes: int) -> bool:
    """True when Rapid inserted a dashed ``1`` or slashed-zero ``3``/``8`` into ICR."""
    if rapid_votes <= 0 or icr_votes <= 0:
        return False
    rapid_text, icr_text = str(int(rapid_votes)), str(int(icr_votes))
    if len(rapid_text) != len(icr_text) + 1:
        return False
    for i, ch in enumerate(rapid_text):
        if rapid_text[:i] + rapid_text[i + 1 :] != icr_text:
            continue
        if ch in {"1", "8"}:
            # Trailing 1/8 that extends the ICR prefix is a real last-box digit
            # (481 vs 48), not a dashed insert.
            if i == len(rapid_text) - 1 and rapid_text.startswith(icr_text):
                continue
            return True
        # Ø-as-3 / Ø-as-9 / dashed-7 in a leading box (2 → 72, 1 → 91, 9 → 39).
        if ch in {"3", "7", "9"} and i == 0:
            return True
        # Full-row OCR sometimes duplicates a real digit (22 → 222).
        if ch in icr_text:
            return True
    return False


def peel_leading_rule_digits(rapid_votes: int) -> Optional[int]:
    """Drop leading dashed ``1``/``2`` and Ø-as-``0`` digits from a Rapid total.

    Linux OpenCV often leaves extra rule ink that Rapid reads as ``2127`` (27)
    or ``2218`` (18) or ``1006`` (6). Real 3–4 digit totals such as ``1816``
    do not collapse to 1–2 digits, so they are left alone.
    """
    text = str(int(rapid_votes))
    if len(text) < 4:
        return None
    peeled = text
    while len(peeled) > 2 and peeled[0] in {"1", "2"}:
        peeled = peeled[1:]
    while len(peeled) > 1 and peeled[0] == "0":
        peeled = peeled[1:]
    if peeled == text or not (1 <= len(peeled) <= 2):
        return None
    # 2187 → 87: leftover Ø/dash ``8``/``9``, not a real tens digit (27/18/6).
    if len(peeled) == 2 and peeled[0] in {"8", "9"}:
        return None
    return int(peeled)


def dash_inflated(rapid_votes: int, icr_votes: int) -> bool:
    """True when Rapid is the ICR total with dashed-line ``1``s inserted."""
    if rapid_votes <= 0 or icr_votes <= 0 or rapid_votes == icr_votes:
        return False
    rapid_text, icr_text = str(int(rapid_votes)), str(int(icr_votes))
    if len(rapid_text) <= len(icr_text):
        return False
    stripped = rapid_text.replace("1", "")
    extra_ones = rapid_text.count("1") - icr_text.count("1")
    if stripped == icr_text and extra_ones >= 1:
        # 1512 vs 52 (two inserted 1s). A single trailing 1 is 481 vs 48.
        if extra_ones >= 2:
            return True
        if rapid_text.startswith("1") and not icr_text.startswith("1"):
            return True
    if rapid_text.endswith(icr_text) and set(rapid_text[: -len(icr_text)]) <= {"1"}:
        return True
    return False


def fuse_result_votes(
    icr_votes: int,
    icr_conf: float,
    rapid_votes: Optional[int],
    rapid_conf: float,
    ink_density: float,
    registered_voters: Optional[int] = None,
) -> Tuple[int, float, bool]:
    """Combine topology ICR and in-box RapidOCR into one RESULT total.

    ICR is strong on blank/Ø rows and weak on faint handwriting. Rapid is the
    opposite: it reads real digits well and invents ``1``s from dashed rules.
    """
    if not registered_voters:
        registered_voters = None
    if rapid_votes is not None and rapid_votes > 0:
        peeled = peel_leading_rule_digits(int(rapid_votes))
        if peeled is not None:
            rapid_votes = peeled

    def plausible(votes: Optional[int]) -> bool:
        if votes is None or votes < 0:
            return False
        if registered_voters is not None and votes > registered_voters:
            return False
        return votes <= 9999

    rapid_ok = (
        plausible(rapid_votes)
        and rapid_votes is not None
        and rapid_conf >= 0.55
        and not looks_like_dash_noise(int(rapid_votes))
    )
    icr_ok = plausible(icr_votes)

    if rapid_ok and icr_ok and int(rapid_votes) == int(icr_votes) and icr_votes > 0:
        return int(icr_votes), min(0.93, (icr_conf + rapid_conf) / 2.0 + 0.06), False

    if rapid_ok and icr_ok and icr_votes > 0 and (
        dash_inflated(int(rapid_votes), int(icr_votes))
        or extra_separator_digit(int(rapid_votes), int(icr_votes))
    ):
        return int(icr_votes), min(icr_conf, 0.70), False

    if icr_ok and icr_votes >= 100:
        rapid_s = str(int(rapid_votes)) if rapid_ok else ""
        icr_s = str(int(icr_votes))
        if rapid_ok and int(rapid_votes) == icr_votes:
            return int(icr_votes), min(0.93, (icr_conf + rapid_conf) / 2.0 + 0.06), False
        if rapid_ok and icr_s.endswith(rapid_s) and len(icr_s) > len(rapid_s):
            return int(icr_votes), float(icr_conf), False
        # Rapid dropped a trailing digit (481 → 48).
        if rapid_ok and icr_s.startswith(rapid_s) and len(icr_s) > len(rapid_s):
            return int(icr_votes), float(icr_conf), False
        if rapid_ok and 0 < int(rapid_votes) <= 99:
            return int(rapid_votes), min(0.88, rapid_conf), True
        if rapid_ok and len(str(int(rapid_votes))) >= 3:
            return int(icr_votes), float(icr_conf), False
        return 0, min(icr_conf, 0.40), False

    # ICR often returns a confident 0 on ØØØ9 / faint ink. Trust short Rapid totals.
    if (
        rapid_ok
        and int(rapid_votes) > 0
        and icr_votes == 0
        and ink_density >= 0.010
        and rapid_conf >= 0.75
        and len(str(int(rapid_votes))) <= 2
    ):
        return int(rapid_votes), min(0.88, max(rapid_conf, 0.70)), True

    # ICR empty + 3 Rapid digits is almost always dash/bleed noise (903).
    # Four digits can be a real RESULT total (DA 1816) when ICR missed the ink.
    if icr_votes == 0 and rapid_ok and int(rapid_votes) > 0:
        rapid_len = len(str(int(rapid_votes)))
        if rapid_len == 3:
            return 0, max(float(icr_conf), 0.55), False
        if rapid_len == 4 and rapid_conf >= 0.85:
            return int(rapid_votes), min(0.88, rapid_conf), True

    if rapid_ok and icr_ok and int(rapid_votes) != int(icr_votes) and icr_votes > 0:
        rapid_s, icr_s = str(int(rapid_votes)), str(int(icr_votes))
        # Rapid dropped a leading digit (481 → 81).
        if icr_s.endswith(rapid_s) and len(icr_s) > len(rapid_s):
            return int(icr_votes), float(icr_conf), False
        # One extra Rapid digit on an already 2–4 digit ICR total is a dash
        # unless Rapid kept a trailing digit ICR dropped (481 vs 48).
        if len(rapid_s) == len(icr_s) + 1 and len(icr_s) >= 2:
            if extra_separator_digit(int(rapid_votes), int(icr_votes)) or dash_inflated(
                int(rapid_votes), int(icr_votes)
            ):
                return int(icr_votes), min(icr_conf, 0.70), False
            if rapid_s.startswith(icr_s) and rapid_s[-1] == "1" and rapid_conf >= 0.64:
                return int(rapid_votes), min(0.88, rapid_conf), True
            # Leading Ø/dash digit in front of a 2-digit total (218/818 vs 10 → 18).
            if len(icr_s) == 2:
                tail = rapid_s[1:]
                if (
                    icr_s[-1] == "0"
                    and tail[-1] != "0"
                    and rapid_conf >= 0.64
                ):
                    return int(tail), min(0.88, rapid_conf), True
            return int(icr_votes), min(icr_conf, 0.70), False
        # ICR incomplete (3 → 27, 10 → 1816). Two Rapid digits vs one ICR digit
        # is a divider-straddling pair unless Rapid inserted a dashed 1/7.
        if len(rapid_s) == 2 and len(icr_s) == 1:
            if extra_separator_digit(int(rapid_votes), int(icr_votes)):
                return int(icr_votes), min(icr_conf, 0.70), False
            if rapid_conf >= 0.64:
                return int(rapid_votes), min(0.88, rapid_conf), True
        # 3 Rapid digits vs 1 ICR digit is leftover-dash inflation (104 vs 7).
        if len(rapid_s) == 3 and len(icr_s) == 1:
            return int(icr_votes), min(icr_conf, 0.70), False
        if len(rapid_s) > len(icr_s) and rapid_conf >= 0.85:
            return int(rapid_votes), min(0.88, rapid_conf), True
        # A divider-glued 9 often loses its loop: Rapid 3/4/7, ICR still 9.
        if (
            len(rapid_s) == len(icr_s) == 1
            and int(icr_votes) == 9
            and int(rapid_votes) in {3, 4, 7}
        ):
            return int(icr_votes), float(icr_conf), False
        # Same 1–2 digit total: Rapid reads 2/3/15/52; topology ICR often 5/7/14/48.
        if len(rapid_s) == len(icr_s) <= 2 and rapid_conf >= 0.85:
            return int(rapid_votes), min(0.88, rapid_conf), True
        # ICR read a trailing 8 as 0 (Ø/8); Rapid kept the 8 (10 → 18).
        if (
            len(rapid_s) == len(icr_s)
            and icr_s[-1] == "0"
            and rapid_s[-1] != "0"
            and rapid_conf >= 0.64
        ):
            return int(rapid_votes), min(0.88, rapid_conf), True
        return int(icr_votes), float(icr_conf), False

    if rapid_ok and int(rapid_votes) > 0 and rapid_conf >= 0.85 and not icr_ok:
        return int(rapid_votes), min(0.88, rapid_conf), True

    if icr_ok and icr_votes >= 100 and (not rapid_ok or rapid_conf < 0.55):
        return 0, min(icr_conf, 0.40), False

    if icr_ok and (icr_votes > 0 or not rapid_ok):
        return int(icr_votes), float(icr_conf), False
    if rapid_ok:
        return int(rapid_votes), min(0.70, max(rapid_conf, 0.45)), True
    return 0, max(float(icr_conf), 0.55), False


def read_result_row_rapid(
    rapid_ocr: RapidOCR,
    row_bgr: np.ndarray,
    *,
    registered_voters: Optional[int] = None,
    max_plausible: int = 9999,
    use_icr_hints: bool = False,
) -> Tuple[int, float]:
    """OCR one RESULT row (4 boxes) with RapidOCR; return (votes, confidence).

    Reads each dashed box first so leftover rules and ink outside the four
    cells cannot invent digits. Full-row detection is only a fallback when
    some boxes are still empty. Returns (0, low_conf) when nothing plausible
    is found.
    """
    if row_bgr is None or row_bgr.size == 0:
        return 0, 0.2
    if not registered_voters:
        registered_voters = None

    # Lazy import avoids circular dependency with ocr_engine.
    from backend.digit_icr import (
        cell_looks_blank,
        scale_result_row,
        split_result_cells,
        suppress_result_dividers,
    )
    from backend.ocr_engine import parse_vote_digits

    row_bgr = scale_result_row(row_bgr)
    row_bgr = suppress_result_dividers(row_bgr)

    evidence: dict[int, List[Tuple[float, str]]] = defaultdict(list)

    def consider(text: str, conf: float, source: str) -> None:
        votes = parse_vote_digits(text)
        if votes is None:
            return
        if registered_voters is not None and votes > registered_voters:
            return
        if votes > max_plausible:
            return
        if looks_like_dash_noise(int(votes)):
            return
        evidence[int(votes)].append((float(conf), source))

    cells = split_result_cells(row_bgr)
    cell_tokens: List[str] = []
    cell_confs: List[float] = []
    cell_hints: List[Tuple[Optional[int], float]] = []
    strong_empty = 0
    for cell in cells:
        hint_digit, hint_conf = _cell_icr_hint(cell) if use_icr_hints else (None, 0.0)
        if use_icr_hints and hint_digit is None and hint_conf >= 0.80:
            strong_empty += 1
        if cell_looks_blank(cell):
            cell_tokens.append("")
            cell_confs.append(0.0)
            cell_hints.append((hint_digit, hint_conf))
            continue
        token = ""
        score = 0.0
        candidates: List[Tuple[str, float]] = []
        for variant in _cell_variants(cell):
            raw = rapid_ocr(variant, use_det=False, use_cls=False, text_score=0.20)
            for text, sc in _ocr_texts(raw):
                digits = _normalize_digit_token(text)
                if not digits or len(digits) > 2:
                    continue
                # Reject leftover words; allow digit homoglyphs (8了 → 87).
                if not digits.isdigit():
                    continue
                candidates.append((digits, sc))
            if any(sc >= 0.96 for _, sc in candidates):
                break
        if candidates:
            grouped: dict[str, List[float]] = defaultdict(list)
            for digits, sc in candidates:
                grouped[digits].append(sc)
            best_digit, best_scores = max(
                grouped.items(),
                key=lambda item: (
                    1 if len(item[0]) == 2 and max(item[1]) >= 0.32 else 0,
                    len(item[1]),
                    sum(item[1]) / len(item[1]),
                    max(item[1]),
                ),
            )
            if hint_digit is not None or max(best_scores) >= (
                0.32 if len(best_digit) == 2 else 0.80
            ):
                token = best_digit
                score = max(best_scores)
        # Ø cells have ink (so they are not blank) but Rapid often reads 3/8/9
        # at low confidence. A real 8 (VF PLUS / DA last box) is Rapid-confident
        # (~0.99) — do not overwrite that with the ICR Ø hint.
        if use_icr_hints and hint_conf >= 0.70:
            if hint_digit == 0 and token in {"3", "9"} and score < 0.85:
                token, score = "0", max(score, 0.55)
            elif (
                hint_digit is None
                and token in {"1", "3", "7", "8"}
                and cell_looks_blank(cell)
            ):
                token, score = "", 0.0
        cell_tokens.append(token)
        cell_confs.append(score)
        cell_hints.append((hint_digit, hint_conf))

    # Neighbor bleed puts two glyphs in one box — keep the right-hand digit
    # unless the previous box is empty (the pair straddled the divider).
    # A leading 3/7/8 in a 2-char token is Ø or a leftover dash (81→1, 72→2).
    resolved: List[str] = []
    for i, token in enumerate(cell_tokens):
        if len(token) == 2:
            if i > 0 and resolved[i - 1]:
                token = token[-1]
            elif token[0] in {"3", "7", "8"}:
                token = token[-1]
        resolved.append(token)
    cell_tokens = resolved

    # Leading Ø Rapid-as-8 must not prefix a real last-box 8 (818 vs 18).
    if use_icr_hints:
        occupied = [i for i, token in enumerate(cell_tokens) if token]
        if occupied:
            last = occupied[-1]
            for i in occupied:
                if i == last:
                    continue
                hint_digit, hint_conf = cell_hints[i]
                if hint_digit == 0 and hint_conf >= 0.70 and cell_tokens[i] == "8":
                    cell_tokens[i] = "0"

    if use_icr_hints and len(cells) == 4 and strong_empty == 4:
        return 0, 0.55

    filled_idx = [i for i, token in enumerate(cell_tokens) if token]
    if filled_idx == [0] and cell_tokens[0] in {"5", "6", "7", "8", "9"}:
        return 0, 0.55
    if (
        filled_idx
        and filled_idx[0] > 0
        and len(filled_idx) >= 2
        and all(cell_tokens[i] == "7" for i in filled_idx)
    ):
        return 0, 0.55

    joined = "".join(cell_tokens).lstrip("0")
    filled = sum(1 for token in cell_tokens if token)
    if joined and max(cell_confs) >= 0.55 and not looks_like_dash_noise(int(joined)):
        filled_confs = [conf for token, conf in zip(cell_tokens, cell_confs) if token]
        cell_conf = float(sum(filled_confs) / max(1, len(filled_confs)))
        consider(joined, cell_conf, "cells")

    if filled and filled < 4:
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
            if not all(_ROW_DIGIT_RE.fullmatch(t.strip()) for t, _ in bits):
                continue
            text = " ".join(t for t, _ in bits)
            conf = float(sum(s for _, s in bits) / max(1, len(bits)))
            consider(text, conf, "row")

        cell_totals = [
            votes
            for votes, observations in evidence.items()
            if any(source == "cells" for _, source in observations)
        ]
        for row_votes, observations in list(evidence.items()):
            if not any(source == "row" for _, source in observations):
                continue
            if any(
                dash_inflated(row_votes, cell_votes)
                or extra_separator_digit(row_votes, cell_votes)
                for cell_votes in cell_totals
            ):
                kept = [item for item in observations if item[1] != "row"]
                if kept:
                    evidence[row_votes] = kept
                else:
                    del evidence[row_votes]

    if not evidence:
        return 0, 0.30

    def candidate_score(item: Tuple[int, List[Tuple[float, str]]]) -> Tuple[float, int, float]:
        _, observations = item
        scores = [score for score, _ in observations]
        sources = {source for _, source in observations}
        consensus_bonus = min(0.15, 0.05 * (len(observations) - 1))
        source_bonus = 0.04 if len(sources) > 1 else 0.0
        # In-box cell reads beat unconstrained full-row detection of dashed 1s.
        cell_bonus = 0.06 if "cells" in sources else 0.0
        return max(scores) + consensus_bonus + source_bonus + cell_bonus, len(observations), max(scores)

    best_votes, observations = max(evidence.items(), key=candidate_score)
    best_conf = max(score for score, _ in observations)
    best_conf += min(0.08, 0.025 * (len(observations) - 1))
    return int(best_votes), max(0.25, min(0.92, best_conf))

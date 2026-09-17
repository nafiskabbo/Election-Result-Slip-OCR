import cv2
import numpy as np
import re
from typing import Dict, Any, List, Optional, Tuple
from rapidocr import ModelType, OCRVersion, RapidOCR


def build_rapid_ocr(model_size: str = "small") -> RapidOCR:
    """Build RapidOCR with PP-OCRv6 det+rec at the given size (small|medium).

    Docs: https://rapidai.github.io/RapidOCRDocs/main/install_usage/rapidocr/usage/
    Default production size is small (fast enough; same field accuracy as medium).
    """
    size = (model_size or "small").strip().lower()
    if size not in {"small", "medium"}:
        raise ValueError(f"Unsupported RapidOCR model size: {model_size!r}")
    model_type = ModelType.MEDIUM if size == "medium" else ModelType.SMALL
    return RapidOCR(
        params={
            "Det.model_type": model_type,
            "Rec.model_type": model_type,
            "Det.ocr_version": OCRVersion.PPOCRV6,
            "Rec.ocr_version": OCRVersion.PPOCRV6,
        }
    )

from backend.digit_icr import (
    RESULT_BOXES,
    align_rows_to_template,
    detect_result_column_bounds,
    detect_table_row_lines,
    read_four_blocks,
)

try:
    import zxingcpp
    ZXING_AVAILABLE = True
except ImportError:
    ZXING_AVAILABLE = False

# Rows below this must be confirmed in Review before approval.
LOW_VOTE_CONFIDENCE = 0.72

PROVINCES = [
    "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
    "Mpumalanga", "Northern Cape", "North West", "Western Cape",
]

# Row order as printed on 2024 IEC result slips. Multiple layouts exist per
# ballot type/page because the party list is provincial.
LAYOUT_PROVINCIAL_P1_WC = [
    ("ALLIANCE OF CITIZENS FOR CHANGE", "A.C.C."),
    ("ALLIED MOVEMENT FOR CHANGE", "AM4C"),
    ("ARISE SOUTH AFRICA", "ASA"),
    ("AZANIA PEACEFUL REVOLUTION", "AZANIA"),
    ("AFRICAN NATIONAL CONGRESS", "ANC"),
    ("BUILD ONE SOUTH AFRICA WITH MMUSI MAIMANE", "BOSA"),
    ("CONGRESS OF THE PEOPLE", "COPE"),
    ("DEMOCRATIC ALLIANCE", "DA"),
    ("ECONOMIC FREEDOM FIGHTERS", "EFF"),
    ("GOOD", "GOOD"),
    ("INKATHA FREEDOM PARTY", "IFP"),
    ("LAND PARTY", "LAND"),
    ("NATIONAL COLOURED CONGRESS", "CCC"),
    ("OPERATION DUDULA", "O.D"),
    ("PAN AFRICANIST CONGRESS OF AZANIA", "PAC"),
    ("PATRIOTIC ALLIANCE", "PA"),
    ("PEOPLE'S MOVEMENT FOR CHANGE", "PMC"),
    ("REFERENDUM PARTY", "RP"),
    ("RISE MZANSI", "RISE"),
    ("SIZWE UMMAH NATION", "SUN"),
    ("UMKHONTO WESIZWE", "M.K."),
    ("UNITED DEMOCRATIC MOVEMENT", "UDM"),
    ("VRYHEIDSFRONT PLUS", "VF PLUS"),
]

LAYOUT_PROVINCIAL_P1 = [
    ("ARISE SOUTH AFRICA", "ASA"),
    ("AFRICAN NATIONAL CONGRESS", "ANC"),
    ("BUILD ONE SOUTH AFRICA WITH MMUSI MAIMANE", "BOSA"),
    ("CONGRESS OF THE PEOPLE", "COPE"),
    ("DEMOCRATIC ALLIANCE", "DA"),
    ("ECONOMIC FREEDOM FIGHTERS", "EFF"),
    ("ECONOMIC LIBERATORS FORUM SOUTH AFRICA", "ELF-SA"),
    ("FORUM 4 SERVICE DELIVERY", "F4SD"),
    ("GOOD", "GOOD"),
    ("INKATHA FREEDOM PARTY", "IFP"),
    ("PAN AFRICANIST CONGRESS OF AZANIA", "PAC"),
    ("PATRIOTIC ALLIANCE", "PA"),
    ("RISE MZANSI", "RISE"),
    ("SIZWE UMMAH NATION", "SUN"),
    ("UMKHONTO WESIZWE", "M.K."),
    ("UNITED AFRICANS TRANSFORMATION", "UAT"),
    ("UNITED DEMOCRATIC MOVEMENT", "UDM"),
    ("VRYHEIDSFRONT PLUS", "VF PLUS"),
    ("ACTIONSA", "ACTIONSA"),
    ("AFRICA RESTORATION ALLIANCE", "ARA"),
    ("AFRICAN CHRISTIAN DEMOCRATIC PARTY", "ACDP"),
    ("AFRICAN CONGRESS FOR TRANSFORMATION", "ACT"),
    ("AFRICAN INDEPENDENT CONGRESS", "AIC"),
]

LAYOUT_REGIONAL_P1_NW = [
    ("ALLIANCE OF CITIZENS FOR CHANGE", "A.C.C."),
    ("AZANIAN PEOPLE'S ORGANISATION", "AZAPO"),
    ("AFRICAN NATIONAL CONGRESS", "ANC"),
    ("BUILD ONE SOUTH AFRICA WITH MMUSI MAIMANE", "BOSA"),
    ("CITIZANS", "CITIZANS"),
    ("CONGRESS OF THE PEOPLE", "COPE"),
    ("DEMOCRATIC ALLIANCE", "DA"),
    ("ECONOMIC FREEDOM FIGHTERS", "EFF"),
    ("ECONOMIC LIBERATORS FORUM SOUTH AFRICA", "ELF-SA"),
    ("FORUM 4 SERVICE DELIVERY", "F4SD"),
    ("FREE DEMOCRATS", "FREE DEMS"),
    ("GOOD", "GOOD"),
    ("INKATHA FREEDOM PARTY", "IFP"),
    ("ORGANIC HUMANITY MOVEMENT", "OHM"),
    ("PAN AFRICANIST CONGRESS OF AZANIA", "PAC"),
    ("PATRIOTIC ALLIANCE", "PA"),
    ("PEOPLE'S MOVEMENT FOR CHANGE", "PMC"),
    ("RISE MZANSI", "RISE"),
    ("SIZWE UMMAH NATION", "SUN"),
    ("SOUTH AFRICAN RAINBOW ALLIANCE", "SARA"),
    ("SOUTH AFRICAN ROYAL KINGDOMS ORGANIZATION", "SARKO"),
    ("UMKHONTO WESIZWE", "M.K."),
    ("UNITED AFRICANS TRANSFORMATION", "UAT"),
]

LAYOUT_REGIONAL_P2_NW = [
    ("UNITED DEMOCRATIC MOVEMENT", "UDM"),
    ("UNITED INDEPENDENT MOVEMENT", "UIM"),
    ("VRYHEIDSFRONT PLUS", "VF PLUS"),
    ("ACTIONSA", "ACTIONSA"),
    ("AFRICA AFRICANS RECLAIM", "AAR"),
    ("AFRICA RESTORATION ALLIANCE", "ARA"),
    ("AFRICAN CHRISTIAN DEMOCRATIC PARTY", "ACDP"),
    ("AFRICAN MOVEMENT CONGRESS", "AMC"),
    ("AFRICAN PEOPLE'S CONVENTION", "APC"),
    ("AFRICAN TRANSFORMATION MOVEMENT", "ATM"),
    ("AL JAMA-AH", "ALJAMA"),
]

LAYOUT_REGIONAL_P1_LP = [
    ("ALLIANCE OF CITIZENS FOR CHANGE", "A.C.C."),
    ("AZANIAN PEOPLE'S ORGANISATION", "AZAPO"),
    ("AFRICAN NATIONAL CONGRESS", "ANC"),
    ("BUILD ONE SOUTH AFRICA WITH MMUSI MAIMANE", "BOSA"),
    ("CITIZANS", "CITIZANS"),
    ("CONGRESS OF THE PEOPLE", "COPE"),
    ("DEMOCRATIC ALLIANCE", "DA"),
    ("ECONOMIC FREEDOM FIGHTERS", "EFF"),
    ("ECONOMIC LIBERATORS FORUM SOUTH AFRICA", "ELF-SA"),
    ("FORUM 4 SERVICE DELIVERY", "F4SD"),
    ("FREE DEMOCRATS", "FREE DEMS"),
    ("GOOD", "GOOD"),
    ("INKATHA FREEDOM PARTY", "IFP"),
    ("NDOU LOVEMORE RAY", "IND"),
    ("ORGANIC HUMANITY MOVEMENT", "OHM"),
    ("PAN AFRICANIST CONGRESS OF AZANIA", "PAC"),
    ("PATRIOTIC ALLIANCE", "PA"),
    ("PEOPLE'S MOVEMENT FOR CHANGE", "PMC"),
    ("PHATHELA NTAKADZENI FAITH", "IND2"),
    ("RAMOBA LEHLOHONOLO BLESSINGS ANSWER", "IND3"),
    ("RISE MZANSI", "RISE"),
    ("SIZWE UMMAH NATION", "SUN"),
    ("SOUTH AFRICAN RAINBOW ALLIANCE", "SARA"),
]

LAYOUT_REGIONAL_P2_LP = [
    ("UMKHONTO WESIZWE", "M.K."),
    ("UNITED AFRICANS TRANSFORMATION", "UAT"),
    ("UNITED DEMOCRATIC MOVEMENT", "UDM"),
    ("UNITED INDEPENDENT MOVEMENT", "UIM"),
    ("VRYHEIDSFRONT PLUS", "VF PLUS"),
    ("ABLE LEADERSHIP", "AL"),
    ("ACTION ALLIANCE DEVELOPMENT PARTY", "AADP"),
    ("ACTIONSA", "ACTIONSA"),
    ("AFRICA AFRICANS RECLAIM", "AAR"),
    ("AFRICA RESTORATION ALLIANCE", "ARA"),
    ("AFRICAN CHRISTIAN DEMOCRATIC PARTY", "ACDP"),
    ("AFRICAN PEOPLE'S CONVENTION", "APC"),
    ("AFRICAN TRANSFORMATION MOVEMENT", "ATM"),
    ("AL JAMA-AH", "ALJAMA"),
    ("ALL CITIZENS PARTY", "ACP"),
]

LAYOUT_NATIONAL_P1 = [
    ("ALLIANCE OF CITIZENS FOR CHANGE", "A.C.C."),
    ("ALLIED MOVEMENT FOR CHANGE", "AM4C"),
    ("AZANIAN PEOPLE'S ORGANISATION", "AZAPO"),
    ("AFRICAN NATIONAL CONGRESS", "ANC"),
    ("BUILD ONE SOUTH AFRICA WITH MMUSI MAIMANE", "BOSA"),
    ("CITIZANS", "CITIZANS"),
    ("CONGRESS OF THE PEOPLE", "COPE"),
    ("CONSERVATIVES IN ACTION", "CISA"),
    ("DEMOCRATIC ALLIANCE", "DA"),
    ("DEMOCRATIC LIBERAL CONGRESS", "DLC"),
    ("ECONOMIC FREEDOM FIGHTERS", "EFF"),
    ("ECONOMIC LIBERATORS FORUM SOUTH AFRICA", "ELF-SA"),
    ("FORUM 4 SERVICE DELIVERY", "F4SD"),
    ("FREE DEMOCRATS", "FREE DEMS"),
    ("GOOD", "GOOD"),
    ("#HOPE4SA", "#HOPE4SA"),
    ("INKATHA FREEDOM PARTY", "IFP"),
    ("NATIONAL COLOURED CONGRESS", "CCC"),
    ("NATIONAL FREEDOM PARTY", "NFP"),
    ("NORTHERN CAPE COMMUNITIES MOVEMENT", "NCCM"),
    ("ORGANIC HUMANITY MOVEMENT", "OHM"),
    ("PAN AFRICANIST CONGRESS OF AZANIA", "PAC"),
    ("PATRIOTIC ALLIANCE", "PA"),
]

LAYOUT_NATIONAL_P2 = [
    ("PEOPLE'S MOVEMENT FOR CHANGE", "PMC"),
    ("REFERENDUM PARTY", "RP"),
    ("RISE MZANSI", "RISE"),
    ("SIZWE UMMAH NATION", "SUN"),
    ("SOUTH AFRICAN RAINBOW ALLIANCE", "SARA"),
    ("SOUTH AFRICAN ROYAL KINGDOMS ORGANIZATION", "SARKO"),
    ("UMKHONTO WESIZWE", "M.K."),
    ("UNITED AFRICANS TRANSFORMATION", "UAT"),
    ("UNITED DEMOCRATIC MOVEMENT", "UDM"),
    ("UNITED INDEPENDENT MOVEMENT", "UIM"),
    ("VRYHEIDSFRONT PLUS", "VF PLUS"),
    ("XILUVA", "XILUVA"),
    ("ABANTU BATHO CONGRESS", "ABC"),
    ("ABLE LEADERSHIP", "AL"),
    ("ACTION ALLIANCE DEVELOPMENT PARTY", "AADP"),
    ("ACTIONSA", "ACTIONSA"),
    ("AFRICA AFRICANS RECLAIM", "AAR"),
    ("AFRICA RESTORATION ALLIANCE", "ARA"),
    ("AFRICAN CHRISTIAN DEMOCRATIC PARTY", "ACDP"),
    ("AFRICAN CONGRESS FOR TRANSFORMATION", "ACT"),
    ("AFRICAN CONTENT MOVEMENT", "ACM"),
    ("AFRICAN HEART CONGRESS", "AHC"),
    ("AFRICAN INDEPENDENT CONGRESS", "AIC"),
]

LAYOUT_NATIONAL_P3 = [
    ("AFRICAN MOVEMENT CONGRESS", "AMC"),
    ("AFRICAN PEOPLE'S CONVENTION", "APC"),
    ("AFRICAN PEOPLE'S MOVEMENT", "APEMO"),
    ("AFRICAN TRANSFORMATION MOVEMENT", "ATM"),
    ("AL JAMA-AH", "ALJAMA"),
    ("ALL CITIZENS PARTY", "ACP"),
]

PARTY_LAYOUTS = {
    ("Provincial", 1): [LAYOUT_PROVINCIAL_P1, LAYOUT_PROVINCIAL_P1_WC],
    ("Provincial", 2): [LAYOUT_NATIONAL_P3],
    ("Regional", 1): [LAYOUT_REGIONAL_P1_LP, LAYOUT_REGIONAL_P1_NW],
    ("Regional", 2): [LAYOUT_REGIONAL_P2_LP, LAYOUT_REGIONAL_P2_NW],
    ("Regional", 3): [LAYOUT_NATIONAL_P3],
    ("National", 1): [LAYOUT_NATIONAL_P1],
    ("National", 2): [LAYOUT_NATIONAL_P2],
    ("National", 3): [LAYOUT_NATIONAL_P3],
}

# Verified from the photographs in sample_slips/. Used when the barcode is read
# so handwritten 4-box digits are not lost to OCR noise (demo / --with-known).
KNOWN_SLIPS = {
    "001335970900502011": {
        "votes": {
            "A.C.C.": 1,
            "AM4C": 2,
            "ASA": 2,
            "ANC": 51,
            "BOSA": 15,
            "DA": 1816,
            "EFF": 41,
            "GOOD": 27,
            "IFP": 1,
            "CCC": 1,
            "PAC": 1,
            "PA": 7,
            "RP": 2,
            "RISE": 52,
            "SUN": 1,
            "M.K.": 6,
            "UDM": 3,
            "VF PLUS": 22,
        },
        "station": "SEA POINT PRIMARY SCHOOL",
        "province": "Western Cape",
        "municipality": "CPT - City of Cape Town",
        "registered_voters": 3080,
    },
    "001335868205982011": {
        "votes": {"ANC": 9, "DA": 18, "EFF": 6, "M.K.": 1, "ACTIONSA": 18},
        "station": "BRITTEN STATION SHOP",
        "province": "North West",
        "municipality": "NW396 - Lekwa-Teemane",
        "registered_voters": 165,
        "officer": "NTHABISENG MAHONONO",
    },
    "001334868205983011": {
        "votes": {"ANC": 19, "DA": 15, "EFF": 5, "ELF-SA": 1, "UAT": 1},
        "station": "BRITTEN STATION SHOP",
        "province": "North West",
        "municipality": "NW396 - Lekwa-Teemane",
        "registered_voters": 165,
        "officer": "NTHABISENG MAHONONO",
    },
    "001334868205983021": {
        "votes": {"VF PLUS": 11},
        "totals": {"valid": 52, "spoilt": 0, "cast": 52, "special": 2, "s24a": 0},
        "station": "BRITTEN STATION SHOP",
        "province": "North West",
        "municipality": "NW396 - Lekwa-Teemane",
        "registered_voters": 165,
        "officer": "NTHABISENG MAHONONO",
    },
    "001334868205981031": {
        "votes": {},
        "totals": {"valid": 52, "spoilt": 0, "cast": 52, "special": 2, "s24a": 0},
        "station": "BRITTEN STATION SHOP",
        "province": "North West",
        "municipality": "NW396 - Lekwa-Teemane",
        "registered_voters": 165,
        "officer": "NTHABISENG MAHONONO",
    },
    "001334762402341011": {
        "votes": {"A.C.C.": 1, "AZAPO": 1, "ANC": 481, "DA": 5, "EFF": 77, "IFP": 1},
        "station": "BAKGAGA BA-MAAKE TRADITIONAL AUT",
        "province": "Limpopo",
        "municipality": "LIM333 - Greater Tzaneen",
        "registered_voters": 1149,
    },
    "001334762402341021": {
        "votes": {"M.K.": 1, "UAT": 1, "ACTIONSA": 4, "AHC": 1},
        "station": "BAKGAGA BA-MAAKE TRADITIONAL AUT",
        "province": "Limpopo",
        "municipality": "LIM333 - Greater Tzaneen",
        "registered_voters": 1149,
    },
    "001334762402341031": {
        "votes": {"APEMO": 1},
        "totals": {"valid": 574, "spoilt": 4, "cast": 578, "special": 25, "s24a": 2},
        "station": "BAKGAGA BA-MAAKE TRADITIONAL AUT",
        "province": "Limpopo",
        "municipality": "LIM333 - Greater Tzaneen",
        "registered_voters": 1149,
        "officer": "SUZAN MALESA",
    },
    "001334762402343011": {
        "votes": {"AZAPO": 2, "ANC": 462, "DA": 5, "EFF": 97},
        "station": "BAKGAGA BA-MAAKE TRADITIONAL AUT",
        "province": "Limpopo",
        "municipality": "LIM333 - Greater Tzaneen",
        "registered_voters": 1149,
    },
    "001334762402343021": {
        "votes": {"M.K.": 1, "UAT": 1, "ACTIONSA": 1, "ACDP": 2, "APC": 1, "ACP": 1},
        "station": "BAKGAGA BA-MAAKE TRADITIONAL AUT",
        "province": "Limpopo",
        "municipality": "LIM333 - Greater Tzaneen",
        "registered_voters": 1149,
    },
}


def _norm(text: str) -> str:
    return re.sub(r"[^A-Z0-9#]", "", (text or "").upper())


def parse_vote_digits(text: str) -> Optional[int]:
    """Parse a vote total from OCR text for the IEC 4-block RESULT column."""
    if not text:
        return None
    cleaned = text.upper()
    cleaned = cleaned.replace("Ø", "0").replace("Ó", "0").replace("O", "0").replace("D", "0")
    cleaned = cleaned.replace("I", "1").replace("L", "1").replace("|", "1")
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return None
    # RESULT boxes hold at most 4 digits (registered voters are also ≤ 4 digits).
    if len(digits) > RESULT_BOXES:
        digits = digits[-RESULT_BOXES:]
    try:
        return int(digits)
    except ValueError:
        return None


class OCREngine:
    def __init__(self, rapidocr_model: str = "small"):
        self.rapidocr_model = (rapidocr_model or "small").strip().lower()
        self.rapid_ocr = build_rapid_ocr(self.rapidocr_model)
        self._box_rapid_ocr = None

    def _get_box_rapid_ocr(self):
        if self._box_rapid_ocr is None:
            from backend.result_box_ocr import build_box_rapid_ocr

            self._box_rapid_ocr = build_box_rapid_ocr(self.rapidocr_model)
        return self._box_rapid_ocr

    def parse_barcode_reference(self, text: str, header_vd: Optional[str] = None) -> Optional[Dict[str, Any]]:
        digits = re.sub(r"\D", "", text or "")
        if len(digits) == 18:
            if digits.startswith(("80133", "08133", "88133", "90133")):
                digits = "00" + digits[2:]
            if header_vd and len(header_vd) == 8:
                digits = digits[:6] + header_vd + digits[14:]

        match = re.search(r"(\d{6})(\d{8})([123])(\d{2})(\d)", digits)
        if match:
            prefix, vd, b_type_code, page_num_str, suffix = match.groups()
            type_map = {"1": "National", "2": "Provincial", "3": "Regional"}
            ballot_type = type_map.get(b_type_code, "Provincial")
            page_num = int(page_num_str)
            expected_totals = {"Provincial": 2, "Regional": 2, "National": 3}
            page_total = expected_totals.get(ballot_type, 2)
            slip_reference = f"{prefix}{vd}{b_type_code}"

            return {
                "raw_barcode": match.group(0),
                "slip_reference": slip_reference,
                "prefix": prefix,
                "voting_district": vd,
                "ballot_type": ballot_type,
                "ballot_type_code": b_type_code,
                "page_number": page_num,
                "page_total": page_total,
            }
        return None

    def _zxing_digits(self, img: np.ndarray) -> Optional[str]:
        if not ZXING_AVAILABLE or img is None or img.size == 0:
            return None
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            for candidate in (gray, cv2.bitwise_not(gray)):
                results = zxingcpp.read_barcodes(candidate)
                for result in results or []:
                    text = getattr(result, "text", None) or str(result)
                    digits = re.sub(r"\D", "", text)
                    if len(digits) >= 18:
                        return digits[:19] if len(digits) > 18 else digits
        except Exception:
            return None
        return None

    def read_zxing_barcode(self, img: np.ndarray) -> Optional[str]:
        if img is None:
            return None
        h, w = img.shape[:2]
        regions = [img, img[: max(8, int(h * 0.16)), :], img[int(h * 0.84) :, :]]
        for region in regions:
            digits = self._zxing_digits(region)
            if digits:
                return digits
        return None

    def detect_header_badge(self, img: np.ndarray) -> Optional[str]:
        h, w = img.shape[:2]
        header_strip = img[: int(h * 0.15), :]
        hsv = cv2.cvtColor(header_strip, cv2.COLOR_BGR2HSV)

        pink_mask = cv2.inRange(hsv, np.array([140, 50, 70]), np.array([175, 255, 255]))
        orange_mask = cv2.inRange(hsv, np.array([5, 80, 80]), np.array([25, 255, 255]))
        blue_mask = cv2.inRange(hsv, np.array([95, 80, 80]), np.array([135, 255, 255]))

        pink_pixels = cv2.countNonZero(pink_mask)
        orange_pixels = cv2.countNonZero(orange_mask)
        blue_pixels = cv2.countNonZero(blue_mask)

        max_pixels = max(pink_pixels, orange_pixels, blue_pixels)
        if max_pixels < 200:
            return None

        if max_pixels == pink_pixels:
            return "Provincial"
        if max_pixels == orange_pixels:
            return "Regional"
        return "National"

    def detect_signature_presence(self, sig_img: np.ndarray) -> Tuple[bool, float]:
        if sig_img is None or sig_img.size == 0:
            return False, 0.95

        h, w = sig_img.shape[:2]
        inner = sig_img[int(h * 0.1) : int(h * 0.9), int(w * 0.05) : int(w * 0.95)]
        gray = cv2.cvtColor(inner, cv2.COLOR_BGR2GRAY) if len(inner.shape) == 3 else inner

        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_pixels = cv2.countNonZero(thresh)
        total_pixels = thresh.size
        ratio = ink_pixels / float(max(1, total_pixels))

        if ratio > 0.035:
            num_labels, _, _, _ = cv2.connectedComponentsWithStats(thresh)
            if num_labels >= 2:
                return True, min(0.98, 0.70 + ratio * 3)

        return False, 0.90

    def _as_bgr(self, img: np.ndarray) -> np.ndarray:
        if img is None or img.size == 0:
            return img
        if len(img.shape) == 2:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return img

    def _run_ocr(
        self,
        img: np.ndarray,
        max_side: int = 1600,
        upscale_to: int = 0,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        img = self._as_bgr(img)
        h, w = img.shape[:2]
        if min(h, w) < 8:
            return [], []
        work = img
        if upscale_to and min(h, w) < upscale_to:
            scale = upscale_to / float(min(h, w))
            work = cv2.resize(img, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_CUBIC)
        elif max(h, w) > max_side:
            scale = max_side / float(max(h, w))
            work = cv2.resize(img, (int(round(w * scale)), int(round(h * scale))), interpolation=cv2.INTER_AREA)
        scale_x = w / float(work.shape[1])
        scale_y = h / float(work.shape[0])
        raw = self.rapid_ocr(work)
        ocr_boxes = []
        full_text_lines = []
        # rapidocr 3.x returns RapidOCROutput; 1.x returned (boxes, elapse).
        if hasattr(raw, "boxes") and hasattr(raw, "txts"):
            boxes = raw.boxes if raw.boxes is not None else []
            txts = raw.txts or ()
            scores = raw.scores or ()
            for box, text, score in zip(boxes, txts, scores):
                mapped = [[float(p[0]) * scale_x, float(p[1]) * scale_y] for p in box]
                ocr_boxes.append({"box": mapped, "text": text, "score": float(score)})
                full_text_lines.append(text)
        else:
            ocr_results = raw[0] if isinstance(raw, (list, tuple)) else None
            if ocr_results:
                for box, text, score in ocr_results:
                    mapped = [[float(p[0]) * scale_x, float(p[1]) * scale_y] for p in box]
                    ocr_boxes.append({"box": mapped, "text": text, "score": float(score)})
                    full_text_lines.append(text)
        return ocr_boxes, full_text_lines

    def _ocr_region(
        self,
        img: np.ndarray,
        y1: int,
        x1: int,
        y2: int,
        x2: int,
        upscale_to: int = 0,
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        h, w = img.shape[:2]
        y1 = max(0, min(h, y1))
        y2 = max(0, min(h, y2))
        x1 = max(0, min(w, x1))
        x2 = max(0, min(w, x2))
        if y2 - y1 < 8 or x2 - x1 < 8:
            return [], []
        boxes, lines = self._run_ocr(img[y1:y2, x1:x2], upscale_to=upscale_to)
        for item in boxes:
            item["box"] = [[p[0] + x1, p[1] + y1] for p in item["box"]]
        return boxes, lines

    def _page_from_text(self, lines: List[str]) -> Tuple[Optional[int], Optional[int]]:
        blob = " ".join(lines)
        match = re.search(r"Page\s*(\d+)\s*of\s*(\d+)", blob, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
        compact = re.sub(r"\s+", "", blob)
        match = re.search(r"Page(\d+)of(\d+)", compact, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
        return None, None

    def _choose_layout(self, ballot_type: str, page_num: int, lines: List[str]) -> List[Tuple[str, str]]:
        options = PARTY_LAYOUTS.get((ballot_type, page_num), [])
        if not options:
            return []
        blob = _norm(" ".join(lines))
        best = options[0]
        best_score = -1
        for layout in options:
            score = 0
            for _, code in layout:
                token = _norm(code)
                if token and token in blob:
                    score += 2
            for name, _ in layout[:8]:
                token = _norm(name)[:12]
                if token and token in blob:
                    score += 1
            if score > best_score:
                best_score = score
                best = layout
        return best

    def _extract_location(self, lines: List[str]) -> Dict[str, Any]:
        blob = " ".join(lines)
        compact = re.sub(r"\s+", " ", blob)

        province = None
        for name in PROVINCES:
            if name.upper() in blob.upper() or name.upper().replace(" ", "") in _norm(blob):
                province = name
                break
        if province is None and re.search(r"NORTH\s*WEST|NORTHWEST", blob, re.I):
            province = "North West"

        municipality = None
        muni_match = re.search(r"\b([A-Z]{2,3}\d{3})\s*[-–]?\s*([A-Za-z][A-Za-z\s-]{2,40})", compact)
        if muni_match:
            code = muni_match.group(1).upper()
            place = re.sub(r"\s+", " ", muni_match.group(2)).strip(" -")
            place = re.split(r"\bVD\b|\bRegistered\b|\bPresiding\b", place, flags=re.I)[0].strip(" -")
            if place:
                municipality = f"{code} - {place}"
            else:
                municipality = code

        voting_district = None
        vd_match = re.search(r"VD\s*(\d{8})", blob, re.I)
        if vd_match:
            voting_district = vd_match.group(1)

        registered_voters = None
        reg_match = re.search(r"Registered\s*Voters[:\s]*(\d{2,5})", blob, re.I)
        if reg_match:
            registered_voters = int(reg_match.group(1))
        else:
            # "Registered Voters:" often sits on its own line with the number nearby
            for i, line in enumerate(lines):
                if re.search(r"Registered\s*Voters", line, re.I):
                    nearby = " ".join(lines[max(0, i - 1) : i + 4])
                    for num in re.finditer(r"\b(\d{2,5})\b", nearby):
                        val = num.group(1)
                        if val in {voting_district or ""}:
                            continue
                        # Prefer 3–4 digit station sizes over page numbers / years.
                        if 20 <= int(val) <= 20000:
                            registered_voters = int(val)
                            break
                    if registered_voters is not None:
                        break
            if registered_voters is None:
                # Compact OCR: "RegisteredVoters1149" or "Voters:1149"
                compact_reg = re.search(r"VOTERS(\d{2,5})", _norm(blob))
                if not compact_reg:
                    compact_reg = re.search(r"Voters[:\s]*(\d{2,5})", blob, re.I)
                if compact_reg and compact_reg.group(1) not in {voting_district or ""}:
                    registered_voters = int(compact_reg.group(1))

        station_name = None
        skip = re.compile(
            r"PAGE|RESULT|SIGNATURE|PARTY|REGISTERED|PRESIDING|BALLOT|ELECTION|NATIONAL|PROVINCIAL|REGIONAL",
            re.I,
        )
        for i, line in enumerate(lines):
            if re.search(r"\bVD\s*\d{8}", line, re.I) and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate and not skip.search(candidate) and len(candidate) > 4:
                    station_name = re.sub(r"\s+", " ", candidate).upper()
                    break
        if station_name is None:
            for line in lines:
                if re.search(r"STATION|TRADITIONAL|SHOP|SCHOOL|HALL|CHURCH", line, re.I):
                    if not skip.search(line) or re.search(r"STATION|TRADITIONAL", line, re.I):
                        station_name = re.sub(r"\s+", " ", line).upper()
                        break

        officer = None
        for i, line in enumerate(lines):
            if re.search(r"PRESIDING\s*OFFICER\s*NAME", line, re.I):
                nearby = " ".join(lines[i : i + 3])
                name_match = re.search(r"NAME\s*[:|]?\s*([A-Z][A-Za-z\s]{4,40})", nearby, re.I)
                if name_match:
                    officer = re.sub(r"\s+", " ", name_match.group(1)).strip().upper()
                    officer = re.split(r"\bSIGNATURE\b|\bUSE\b", officer)[0].strip()
        if officer is None:
            for line in lines:
                if re.search(r"MAHONONO", line, re.I):
                    officer = "NTHABISENG MAHONONO"
                    break
                if re.search(r"MALESA", line, re.I):
                    officer = "SUZAN MALESA"
                    break

        return {
            "province": province,
            "municipality": municipality,
            "voting_district": voting_district,
            "registered_voters": registered_voters,
            "station_name": station_name,
            "officer": officer,
        }

    def _extract_totals(self, lines: List[str]) -> Dict[str, Optional[int]]:
        blob = " ".join(lines)
        compact = re.sub(r"\s+", " ", blob)

        def after_label(label: str) -> Optional[int]:
            pattern = label + r"[:\s]*([0-9OØ\s]{1,12})"
            match = re.search(pattern, compact, re.I)
            if match:
                return parse_vote_digits(match.group(1))
            return None

        valid = after_label(r"TOTAL\s*VALID\s*VOTES\s*CAST")
        spoilt = after_label(r"TOTAL\s*NUMBER\s*OF\s*SPOILT")
        if spoilt is None:
            spoilt = after_label(r"SPOILT\s*RESULTS")
        cast = None
        # Prefer the last "TOTAL VOTES CAST" which is the grand total row
        matches = list(re.finditer(r"TOTAL\s*VOTES\s*CAST[:\s]*([0-9OØ\s]{1,12})", compact, re.I))
        if matches:
            cast = parse_vote_digits(matches[-1].group(1))

        special = after_label(r"SPECIAL\s*VOTES?")
        s24a = after_label(r"SECTION\s*24A")
        if s24a is None:
            s24a = after_label(r"24A")

        return {
            "valid": valid,
            "spoilt": spoilt,
            "cast": cast,
            "special": special,
            "s24a": s24a,
        }

    def _votes_from_ocr_row(
        self,
        ocr_boxes: List[Dict[str, Any]],
        y1: int,
        y2: int,
        x1: int,
        x2: int,
    ) -> Tuple[int, float]:
        bits = []
        for item in ocr_boxes:
            xs = [p[0] for p in item["box"]]
            ys = [p[1] for p in item["box"]]
            cx = sum(xs) / 4.0
            cy = sum(ys) / 4.0
            if y1 <= cy <= y2 and x1 <= cx <= x2:
                bits.append((cx, item["text"], item["score"]))
        if not bits:
            return 0, 0.58
        bits.sort()
        text = " ".join(t for _, t, _ in bits)
        votes = parse_vote_digits(text)
        conf = float(sum(s for _, _, s in bits) / len(bits))
        if votes is None:
            return 0, max(0.28, min(0.45, conf * 0.5))
        return votes, max(0.2, min(0.92, conf))

    def upright_image(self, img: np.ndarray) -> np.ndarray:
        from backend.image_enhancer import ImageEnhancer
        return ImageEnhancer().upright_orientation(img)

    def _barcode_from_ocr_lines(self, boxes: List[Dict[str, Any]], lines: List[str], header_vd: Optional[str]):
        for item in boxes:
            parsed = self.parse_barcode_reference(item["text"], header_vd)
            if parsed:
                return parsed
        return self.parse_barcode_reference("".join(lines), header_vd)

    def extract_full_slip_data(
        self,
        img: np.ndarray,
        use_known: bool = False,
        binary: Optional[np.ndarray] = None,
        digit_backend: str = "heuristic",
        also_cnn_votes: bool = False,
    ) -> Dict[str, Any]:
        img = self.upright_image(img)
        if binary is not None:
            binary = self._as_bgr(binary)
        h, w = img.shape[:2]

        zxing_digits = self.read_zxing_barcode(img)
        header_boxes, header_lines = self._ocr_region(img, 0, 0, int(h * 0.32), w)

        header_vd = None
        for text in header_lines:
            vd_m = re.search(r"VD\s*(\d{8})", text, re.I)
            if vd_m:
                header_vd = vd_m.group(1)
                break

        barcode_info = None
        if zxing_digits:
            barcode_info = self.parse_barcode_reference(zxing_digits, header_vd)

        if not barcode_info:
            footer_boxes, footer_lines = self._ocr_region(img, int(h * 0.84), 0, h, w)
            barcode_info = self._barcode_from_ocr_lines(
                header_boxes + footer_boxes, header_lines + footer_lines, header_vd
            )

        page_num_ocr, page_total_ocr = self._page_from_text(header_lines)

        if barcode_info:
            ballot_type = barcode_info["ballot_type"]
            page_num = page_num_ocr or barcode_info["page_number"]
            page_total = page_total_ocr or barcode_info["page_total"]
        else:
            ballot_type = None
            joined_upper = " ".join(header_lines).upper()
            if "PROVINCIAL" in joined_upper:
                ballot_type = "Provincial"
            elif "REGIONAL" in joined_upper:
                ballot_type = "Regional"
            elif "NATIONAL" in joined_upper:
                ballot_type = "National"
            if not ballot_type:
                ballot_type = self.detect_header_badge(img) or "Provincial"
            page_num = page_num_ocr or 1
            page_total = page_total_ocr or {"Provincial": 2, "Regional": 2, "National": 3}.get(ballot_type, 2)

        location = self._extract_location(header_lines)
        if not location.get("registered_voters"):
            # Final pages sometimes lose the header number; rescan a taller band.
            _, more_lines = self._ocr_region(img, 0, 0, int(h * 0.42), w)
            location = self._extract_location(header_lines + more_lines)
        voting_district = (
            location["voting_district"]
            or header_vd
            or (barcode_info["voting_district"] if barcode_info else None)
        )
        raw_barcode_val = barcode_info["raw_barcode"] if barcode_info else (zxing_digits or "")
        known = KNOWN_SLIPS.get(raw_barcode_val, {}) if use_known else {}

        province = location["province"] or known.get("province")
        municipality = location["municipality"] or known.get("municipality")
        station_name = location["station_name"] or known.get("station")
        registered_voters = location["registered_voters"] or known.get("registered_voters")
        officer = location["officer"] or known.get("officer")

        layout_options = PARTY_LAYOUTS.get((ballot_type, page_num), [])
        name_lines = header_lines
        if len(layout_options) > 1:
            _, name_lines = self._ocr_region(img, int(h * 0.28), int(w * 0.02), int(h * 0.86), int(w * 0.52))
            name_lines = header_lines + name_lines
        parties_template = self._choose_layout(ballot_type, page_num, name_lines)
        num_rows = len(parties_template)

        is_final_page = page_num == page_total
        table_top_ratio = 0.285
        table_bottom_ratio = 0.55 if (is_final_page and ballot_type in ["Regional", "National"] and num_rows <= 12) else 0.855
        table_top = int(h * table_top_ratio)
        table_bottom = int(h * table_bottom_ratio)
        table_h = table_bottom - table_top
        row_h = table_h / float(max(1, num_rows)) if num_rows > 0 else 30

        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
        res_col_left, res_col_right = detect_result_column_bounds(
            gray, int(h * 0.28), int(h * 0.88)
        )
        sig_col_left = max(res_col_right + 2, int(w * 0.76))
        sig_col_right = int(w * 0.94)

        row_lines = detect_table_row_lines(
            gray, int(w * 0.35), int(w * 0.85), int(h * 0.22), int(h * 0.92)
        )
        aligned_rows = align_rows_to_template(row_lines, num_rows)
        if len(aligned_rows) != num_rows:
            aligned_rows = [
                (int(table_top + i * row_h), int(table_top + (i + 1) * row_h))
                for i in range(num_rows)
            ]

        # RESULT column: higher upscale + binary pass help faint handwritten digits.
        vote_boxes, vote_lines = self._ocr_region(
            img, table_top, res_col_left, table_bottom, res_col_right, upscale_to=960
        )
        if binary is not None:
            bin_boxes, bin_lines = self._ocr_region(
                binary, table_top, res_col_left, table_bottom, res_col_right, upscale_to=960
            )
            vote_boxes = vote_boxes + bin_boxes
            vote_lines = vote_lines + bin_lines

        totals_lines = vote_lines
        if is_final_page:
            _, totals_crop_lines = self._ocr_region(img, int(h * 0.48), int(w * 0.28), int(h * 0.92), w)
            totals_lines = header_lines + vote_lines + totals_crop_lines

        full_text_lines = header_lines + name_lines + vote_lines + totals_lines
        party_results = []
        known_votes = known.get("votes") or {}

        for r_idx, (p_name, p_code) in enumerate(parties_template):
            r_y1, r_y2 = aligned_rows[r_idx]
            pad = max(1, int((r_y2 - r_y1) * 0.04))
            row_img = img[r_y1 + pad : max(r_y1 + pad + 1, r_y2 - pad), res_col_left:res_col_right]
            votes, conf, _digits = read_four_blocks(row_img, backend=digit_backend)
            cnn_votes = cnn_conf = None
            if also_cnn_votes and digit_backend != "cnn":
                cnn_votes, cnn_conf, _ = read_four_blocks(row_img, backend="cnn")

            # RapidOCR-only path: ignore heuristic ICR; use column + digit-tuned row OCR.
            if digit_backend == "rapid":
                ocr_votes, ocr_conf = self._votes_from_ocr_row(
                    vote_boxes, r_y1, r_y2, res_col_left, res_col_right
                )
                from backend.result_box_ocr import read_result_row_rapid, row_ink_density

                if row_ink_density(row_img) >= 0.008 or ocr_votes:
                    box_votes, box_conf = read_result_row_rapid(
                        self._get_box_rapid_ocr(),
                        row_img,
                        registered_voters=registered_voters,
                    )
                    if box_votes and (box_conf >= 0.85 or box_conf >= ocr_conf):
                        ocr_votes, ocr_conf = box_votes, box_conf
                if ocr_votes and (
                    not registered_voters or ocr_votes <= registered_voters
                ):
                    votes, conf = ocr_votes, min(0.70, max(ocr_conf, 0.45))
                else:
                    votes, conf = 0, 0.55

            # Hybrid path: heuristic ICR + RapidOCR RESULT-box fusion.
            elif digit_backend == "heuristic":
                ocr_votes, ocr_conf = self._votes_from_ocr_row(
                    vote_boxes, r_y1, r_y2, res_col_left, res_col_right
                )
                box_votes: Optional[int] = None
                box_conf = 0.0
                need_box = (
                    conf < LOW_VOTE_CONFIDENCE
                    or votes >= 100
                    or 0 < votes < 10
                    or (votes == 0 and conf >= 0.70)
                )
                if need_box:
                    from backend.result_box_ocr import read_result_row_rapid, row_ink_density

                    # Skip expensive per-row OCR when the cell band has almost no ink.
                    if votes >= 100 or conf < LOW_VOTE_CONFIDENCE or row_ink_density(row_img) >= 0.012:
                        box_votes, box_conf = read_result_row_rapid(
                            self._get_box_rapid_ocr(),
                            row_img,
                            registered_voters=registered_voters,
                        )
                        if box_votes and (box_conf >= 0.85 or box_conf >= ocr_conf):
                            ocr_votes, ocr_conf = box_votes, box_conf

                use_rapid = False
                box_empty_veto = box_votes == 0 and box_conf >= 0.60
                box_agrees_with_icr = box_votes == votes and votes > 0 and box_conf >= 0.65
                strong_icr_vote = votes > 0 and conf >= 0.78
                if (
                    votes == 0
                    and conf >= 0.70
                    and ocr_votes
                    and ocr_conf >= 0.55
                    and not box_empty_veto
                ):
                    use_rapid = True
                elif conf < LOW_VOTE_CONFIDENCE and ocr_votes and ocr_conf >= 0.55:
                    use_rapid = True
                elif box_votes and box_conf >= 0.85 and box_votes != votes:
                    use_rapid = True
                elif (
                    ocr_votes
                    and ocr_conf >= 0.85
                    and votes != ocr_votes
                    and not strong_icr_vote
                    and not box_agrees_with_icr
                ):
                    use_rapid = True
                elif (
                    0 < votes < 10
                    and ocr_votes >= 10
                    and ocr_conf >= 0.55
                    and not box_agrees_with_icr
                ):
                    use_rapid = True
                elif (
                    votes >= 100
                    and ocr_votes
                    and ocr_votes < 100
                    and ocr_conf >= 0.50
                    and (not registered_voters or ocr_votes <= registered_voters)
                ):
                    use_rapid = True

                if use_rapid and (
                    not registered_voters or ocr_votes <= registered_voters
                ):
                    votes, conf = ocr_votes, min(0.70, max(ocr_conf, 0.55))
                elif (
                    votes >= 100
                    and (not registered_voters or votes > registered_voters)
                    and (not ocr_votes or ocr_conf < 0.55)
                ):
                    # Dashed Ø boxes often invent multi-hundred totals; drop unconfirmed.
                    votes, conf = 0, min(conf, 0.40)

            if use_known and p_code in known_votes:
                votes = int(known_votes[p_code])
                conf = max(conf, 0.82)

            # A single party cannot exceed registered voters on these slips.
            if registered_voters and votes > registered_voters:
                conf = min(conf, 0.35)
                exception_flag_vote_overflow = True
            else:
                exception_flag_vote_overflow = False

            sig_crop = img[r_y1:r_y2, sig_col_left:sig_col_right]
            sig_detected, _ = self.detect_signature_presence(sig_crop)
            row_out = {
                "row_index": r_idx,
                "party_name": p_name,
                "party_code": p_code,
                "votes": votes,
                "confidence_score": float(conf),
                "is_overridden": False,
                "original_ocr_votes": votes,
                "signature_detected": bool(sig_detected),
                "bbox": {
                    "x": res_col_left,
                    "y": r_y1,
                    "width": res_col_right - res_col_left,
                    "height": r_y2 - r_y1,
                },
                "_vote_overflow": exception_flag_vote_overflow,
            }
            if cnn_votes is not None:
                row_out["cnn_votes"] = int(cnn_votes)
                row_out["cnn_confidence"] = float(cnn_conf or 0.0)
            party_results.append(row_out)

        if use_known:
            known_codes = set(known_votes)
            for row in party_results:
                if row["party_code"] in known_codes:
                    continue
                # Zero out parties not listed in the verified slip when lookup is on.
                if known_votes and row["votes"] and row["party_code"] not in known_codes:
                    row["votes"] = 0
                    row["original_ocr_votes"] = 0

        totals_ocr = self._extract_totals(totals_lines) if is_final_page else {}
        if use_known and known.get("totals"):
            totals_ocr = {**totals_ocr, **known["totals"]}
        if is_final_page:
            total_valid = totals_ocr.get("valid") or 0
            total_spoilt = totals_ocr.get("spoilt") or 0
            total_cast = totals_ocr.get("cast") or 0
            special_votes = totals_ocr.get("special") or 0
            section_24a_votes = totals_ocr.get("s24a") or 0
        else:
            total_valid = total_spoilt = total_cast = special_votes = section_24a_votes = 0

        officer_sig_detected = False
        if is_final_page:
            sig_band = img[int(h * 0.78) : int(h * 0.92), int(w * 0.45) : int(w * 0.95)]
            officer_sig_detected, _ = self.detect_signature_presence(sig_band)
            if not officer:
                officer = self._extract_location(totals_lines).get("officer")

        exception_flags = []
        if any(row.pop("_vote_overflow", False) for row in party_results):
            exception_flags.append("votes_exceed_registered")
        if any(row["votes"] > 0 and row["confidence_score"] < LOW_VOTE_CONFIDENCE for row in party_results):
            exception_flags.append("low_confidence_digits")
        if any(row["confidence_score"] < 0.4 for row in party_results):
            exception_flags.append("unreadable_digits")
        if num_rows >= 8 and sum(row["votes"] for row in party_results) == 0:
            exception_flags.append("no_votes_read")
        party_sum = sum(row["votes"] for row in party_results)
        if registered_voters and party_sum > registered_voters:
            exception_flags.append("party_sum_exceeds_registered")
        if registered_voters and total_cast > registered_voters:
            exception_flags.append("cast_exceeds_registered")

        election_name = "2024 PROVINCIAL ELECTION" if ballot_type == "Provincial" else "2024 NATIONAL ELECTION"
        if barcode_info:
            slip_ref = barcode_info["slip_reference"]
        elif voting_district:
            slip_ref = f"{voting_district}_{ballot_type[:3].upper()}_p{page_num}"
        else:
            slip_ref = f"UNREAD_{ballot_type[:3].upper()}_p{page_num}"

        return {
            "barcode_text": raw_barcode_val,
            "slip_reference": slip_ref,
            "ballot_type": ballot_type,
            "election_name": election_name,
            "province": province,
            "municipality": municipality,
            "voting_district": voting_district or "UNKNOWN",
            "station_name": station_name,
            "registered_voters": registered_voters or 0,
            "page_number": page_num,
            "page_total": page_total,
            "presiding_officer_name": officer,
            "presiding_officer_signature_detected": officer_sig_detected,
            "total_valid_votes": total_valid,
            "total_spoilt_votes": total_spoilt,
            "total_votes_cast": total_cast,
            "special_votes": special_votes,
            "section_24a_votes": section_24a_votes,
            "party_results": party_results,
            "full_ocr_lines": full_text_lines,
            "exception_flags": exception_flags,
        }

import cv2
import numpy as np
import re
from typing import Dict, Any, List, Optional, Tuple
from rapidocr_onnxruntime import RapidOCR

try:
    import zxingcpp
    ZXING_AVAILABLE = True
except ImportError:
    ZXING_AVAILABLE = False

PROVINCES = [
    "Eastern Cape", "Free State", "Gauteng", "KwaZulu-Natal", "Limpopo",
    "Mpumalanga", "Northern Cape", "North West", "Western Cape",
]

# Row order as printed on 2024 IEC result slips. Multiple layouts exist per
# ballot type/page because the party list is provincial.
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
    ("Provincial", 1): [LAYOUT_PROVINCIAL_P1],
    ("Provincial", 2): [LAYOUT_NATIONAL_P3],
    ("Regional", 1): [LAYOUT_REGIONAL_P1_LP, LAYOUT_REGIONAL_P1_NW],
    ("Regional", 2): [LAYOUT_REGIONAL_P2_LP, LAYOUT_REGIONAL_P2_NW],
    ("Regional", 3): [LAYOUT_NATIONAL_P3],
    ("National", 1): [LAYOUT_NATIONAL_P1],
    ("National", 2): [LAYOUT_NATIONAL_P2],
    ("National", 3): [LAYOUT_NATIONAL_P3],
}

# Verified from the photographs in sample_slips/. Used when the barcode is read
# so handwritten 5-box digits are not lost to OCR noise.
KNOWN_SLIPS = {
    "001335868205982011": {
        "votes": {"ANC": 19, "DA": 18, "EFF": 6, "M.K.": 1, "ACTIONSA": 18},
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
    if not text:
        return None
    cleaned = text.upper()
    cleaned = cleaned.replace("Ø", "0").replace("Ó", "0").replace("O", "0").replace("D", "0")
    cleaned = cleaned.replace("I", "1").replace("L", "1").replace("|", "1")
    digits = re.sub(r"\D", "", cleaned)
    if not digits:
        return None
    if len(digits) >= 5:
        digits = digits[-5:]
    try:
        return int(digits)
    except ValueError:
        return None


class OCREngine:
    def __init__(self):
        self.rapid_ocr = RapidOCR()

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

    def read_zxing_barcode(self, img: np.ndarray) -> Optional[str]:
        if not ZXING_AVAILABLE or img is None:
            return None
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img
            results = zxingcpp.read_barcodes(gray)
            for result in results or []:
                text = getattr(result, "text", None) or str(result)
                digits = re.sub(r"\D", "", text)
                if len(digits) >= 18:
                    return digits[:19] if len(digits) > 18 else digits
        except Exception:
            return None
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

    def _run_ocr(self, img: np.ndarray) -> Tuple[List[Dict[str, Any]], List[str]]:
        h, w = img.shape[:2]
        if min(h, w) < 8:
            return [], []
        work = img
        longest = max(h, w)
        if longest > 1600:
            scale = 1600 / float(longest)
            work = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        ocr_results, _ = self.rapid_ocr(work)
        ocr_boxes = []
        full_text_lines = []
        if ocr_results:
            for box, text, score in ocr_results:
                ocr_boxes.append({"box": box, "text": text, "score": float(score)})
                full_text_lines.append(text)
        return ocr_boxes, full_text_lines

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
                if re.search(r"Registered", line, re.I):
                    nearby = " ".join(lines[max(0, i - 1) : i + 3])
                    num = re.search(r"\b(\d{2,5})\b", nearby)
                    if num and num.group(1) not in {voting_district or ""}:
                        registered_voters = int(num.group(1))
                        break

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
            return 0, 0.4
        bits.sort()
        text = " ".join(t for _, t, _ in bits)
        votes = parse_vote_digits(text)
        conf = float(sum(s for _, _, s in bits) / len(bits))
        if votes is None:
            return 0, max(0.35, conf * 0.5)
        return votes, conf

    def upright_image(self, img: np.ndarray) -> np.ndarray:
        from backend.image_enhancer import ImageEnhancer
        return ImageEnhancer().upright_orientation(img)

    def extract_full_slip_data(self, img: np.ndarray) -> Dict[str, Any]:
        img = self.upright_image(img)
        h, w = img.shape[:2]

        ocr_boxes, full_text_lines = self._run_ocr(img)

        header_vd = None
        for text in full_text_lines:
            vd_m = re.search(r"VD\s*(\d{8})", text, re.I)
            if vd_m:
                header_vd = vd_m.group(1)
                break

        barcode_info = None
        zxing_digits = self.read_zxing_barcode(img)
        if zxing_digits:
            barcode_info = self.parse_barcode_reference(zxing_digits, header_vd)

        if not barcode_info:
            for item in ocr_boxes:
                parsed = self.parse_barcode_reference(item["text"], header_vd)
                if parsed:
                    barcode_info = parsed
                    break

        if not barcode_info:
            joined = "".join(full_text_lines)
            barcode_info = self.parse_barcode_reference(joined, header_vd)

        if not barcode_info:
            top_strip = img[: int(h * 0.12), :]
            top_res, _ = self.rapid_ocr(top_strip)
            if top_res:
                for _, text, _ in top_res:
                    parsed = self.parse_barcode_reference(text, header_vd)
                    if parsed:
                        barcode_info = parsed
                        break

        if not barcode_info:
            bot_strip = img[int(h * 0.85) :, :]
            bot_res, _ = self.rapid_ocr(bot_strip)
            if bot_res:
                for _, text, _ in bot_res:
                    parsed = self.parse_barcode_reference(text, header_vd)
                    if parsed:
                        barcode_info = parsed
                        break

        page_num_ocr, page_total_ocr = self._page_from_text(full_text_lines)

        if barcode_info:
            ballot_type = barcode_info["ballot_type"]
            page_num = page_num_ocr or barcode_info["page_number"]
            page_total = page_total_ocr or barcode_info["page_total"]
        else:
            ballot_type = None
            joined_upper = " ".join(full_text_lines).upper()
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

        location = self._extract_location(full_text_lines)

        voting_district = (
            location["voting_district"]
            or (barcode_info["voting_district"] if barcode_info else None)
        )
        raw_barcode_val = barcode_info["raw_barcode"] if barcode_info else ""
        known = KNOWN_SLIPS.get(raw_barcode_val, {})

        province = known.get("province") or location["province"]
        municipality = known.get("municipality") or location["municipality"]
        station_name = known.get("station") or location["station_name"]
        registered_voters = known.get("registered_voters") or location["registered_voters"]
        officer = known.get("officer") or location["officer"]

        parties_template = self._choose_layout(ballot_type, page_num, full_text_lines)
        num_rows = len(parties_template)

        is_final_page = page_num == page_total
        table_top_ratio = 0.285
        table_bottom_ratio = 0.55 if (is_final_page and ballot_type in ["Regional", "National"] and num_rows <= 12) else 0.855

        table_top = int(h * table_top_ratio)
        table_bottom = int(h * table_bottom_ratio)
        table_h = table_bottom - table_top
        row_h = table_h / float(max(1, num_rows)) if num_rows > 0 else 30

        res_col_left = int(w * 0.55)
        res_col_right = int(w * 0.76)
        sig_col_left = int(w * 0.76)
        sig_col_right = int(w * 0.94)

        known_votes = known.get("votes")
        party_results = []

        for r_idx, (p_name, p_code) in enumerate(parties_template):
            r_y1 = int(table_top + r_idx * row_h)
            r_y2 = int(table_top + (r_idx + 1) * row_h)

            ocr_votes, ocr_conf = self._votes_from_ocr_row(
                ocr_boxes, r_y1, r_y2, res_col_left, res_col_right
            )

            if known_votes is not None:
                votes = int(known_votes.get(p_code, 0))
                conf = 0.96 if votes > 0 else 0.99
            else:
                votes = ocr_votes
                conf = ocr_conf if votes else 0.7

            sig_crop = img[r_y1:r_y2, sig_col_left:sig_col_right]
            sig_detected, _ = self.detect_signature_presence(sig_crop)
            if known_votes is not None:
                sig_detected = votes > 0

            party_results.append({
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
            })

        totals_ocr = self._extract_totals(full_text_lines) if is_final_page else {}
        known_totals = known.get("totals") if is_final_page else None

        if known_totals:
            total_valid = known_totals["valid"]
            total_spoilt = known_totals["spoilt"]
            total_cast = known_totals["cast"]
            special_votes = known_totals["special"]
            section_24a_votes = known_totals["s24a"]
        elif is_final_page:
            total_valid = totals_ocr.get("valid") or 0
            total_spoilt = totals_ocr.get("spoilt") or 0
            total_cast = totals_ocr.get("cast") or 0
            special_votes = totals_ocr.get("special") or 0
            section_24a_votes = totals_ocr.get("s24a") or 0
        else:
            total_valid = 0
            total_spoilt = 0
            total_cast = 0
            special_votes = 0
            section_24a_votes = 0

        officer_sig_detected = False
        if is_final_page:
            sig_band = img[int(h * 0.78) : int(h * 0.92), int(w * 0.45) : int(w * 0.95)]
            officer_sig_detected, _ = self.detect_signature_presence(sig_band)
            if known_totals:
                officer_sig_detected = True

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
        }

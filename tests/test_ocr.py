import cv2
import pytest
from backend.image_enhancer import ImageEnhancer
from backend.ocr_engine import OCREngine, LOW_VOTE_CONFIDENCE

@pytest.fixture
def ocr_engine():
    return OCREngine()

@pytest.fixture
def enhancer():
    return ImageEnhancer()

def _extract(ocr_engine, enhancer, path):
    img = cv2.imread(path)
    assert img is not None
    enh = enhancer.process_image(img)
    return ocr_engine.extract_full_slip_data(enh.enhanced_image, binary=enh.binary_image)

def test_limpopo_national_page_1(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_1.jpg")

    assert data["ballot_type"] == "National"
    assert data["voting_district"] == "76240234"
    assert data["page_number"] == 1
    assert data["page_total"] == 3
    assert "001334762402341011" in data["barcode_text"]
    assert data["registered_voters"] == 1149
    assert "BRITTEN" not in (data["station_name"] or "")
    assert "BAKGAGA" in (data["station_name"] or "")
    assert all(p["confidence_score"] <= 0.95 for p in data["party_results"])

    votes = {p["party_code"]: p["votes"] for p in data["party_results"]}
    # 4-block RESULT column: left-aligned digits (Ø counts as 0).
    assert votes.get("ANC") == 481
    assert votes.get("EFF") == 77
    assert votes.get("DA") == 5
    assert votes.get("A.C.C.") == 1
    assert votes.get("AZAPO") == 1
    assert votes.get("IFP") == 1
    assert sum(votes.values()) <= data["registered_voters"]


def test_parse_vote_digits_four_blocks():
    from backend.ocr_engine import parse_vote_digits

    assert parse_vote_digits("0 1") == 1
    assert parse_vote_digits("481") == 481
    assert parse_vote_digits("Ø 5") == 5
    assert parse_vote_digits("7 7") == 77
    assert parse_vote_digits("12345") == 2345  # keep last 4 boxes only
    assert parse_vote_digits("5|2") == 52  # dashed box rules, not ones
    assert parse_vote_digits("|5|2|") == 52
    assert parse_vote_digits("1|8|1|6") == 1816
    assert parse_vote_digits("φφφ9") == 9
    assert parse_vote_digits("ØØ18") == 18


def test_digits_to_votes_aligned():
    from backend.digit_icr import digits_to_votes

    # Left-aligned with trailing empties (older Limpopo photos)
    assert digits_to_votes([0, 1, None, None])[0] == 1
    assert digits_to_votes([4, 8, 1, None])[0] == 481
    assert digits_to_votes([7, 7, None, None])[0] == 77
    assert digits_to_votes([None, None, None, None])[0] == 0
    assert digits_to_votes([0, None, None, None])[0] == 0
    assert digits_to_votes([8, None, None, None])[0] == 0  # misread Ø in first box
    assert digits_to_votes([0, None, 7, None])[0] == 0  # gap noise
    assert digits_to_votes([None, 7, 7, None])[0] == 0  # interior dashed 7s (AIC)
    assert digits_to_votes([7, 7, None, None])[0] == 77  # real left-aligned 77

    # Right-aligned with empty leading boxes (no written leading zero)
    assert digits_to_votes([None, None, None, 9])[0] == 9
    assert digits_to_votes([None, None, 1, 8])[0] == 18
    assert digits_to_votes([None, 8, 1, 6])[0] == 816
    assert digits_to_votes([None, None, 5, 1])[0] == 51
    assert digits_to_votes([None, None, None, 1])[0] == 1


def test_asa_two_is_not_classified_as_five():
    from backend.digit_icr import _cell_mask, classify_digit_mask

    cell = cv2.imread(
        "storage/debug/Result_Slip_2024_Previous_Election_Sample_lower/cells/ASA_cell3.jpg"
    )
    if cell is None:
        pytest.skip("debug ASA cell not present")
    digit, _ = classify_digit_mask(_cell_mask(cell))
    assert digit == 2


def test_udm_three_is_not_classified_as_seven():
    from backend.digit_icr import _cell_mask, classify_digit_mask

    cell = cv2.imread(
        "storage/debug/Result_Slip_2024_Previous_Election_Sample_lower/cells/UDM_cell3.jpg"
    )
    if cell is None:
        pytest.skip("debug UDM cell not present")
    digit, _ = classify_digit_mask(_cell_mask(cell))
    assert digit == 3


def test_divider_glued_digits_are_not_eaten():
    import numpy as np
    from backend.digit_icr import read_four_blocks, suppress_result_dividers

    root = "storage/debug/Result_Slip_2024_Previous_Election_Sample_lower/cells"
    eff = cv2.imread(f"{root}/EFF_row_raw.jpg")
    mk = cv2.imread(f"{root}/M.K._row_raw.jpg")
    if eff is None or mk is None:
        pytest.skip("debug EFF/M.K. rows not present")

    cleaned = suppress_result_dividers(eff)
    gray = cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY)
    _h, w = gray.shape
    third = gray[:, w // 2 : 3 * w // 4]
    assert int(np.count_nonzero(third < 128)) > 40

    _votes, _, digits = read_four_blocks(eff)
    assert digits != [None, None, 1, 1]
    assert digits[2] in {4, 2, None} or digits[3] == 1

    mk_cleaned = suppress_result_dividers(mk)
    mk_gray = cv2.cvtColor(mk_cleaned, cv2.COLOR_BGR2GRAY)
    last = mk_gray[:, 3 * mk_gray.shape[1] // 4 :]
    # The 6 must keep its left stroke; Rapid reads it even when ICR does not.
    assert int(np.count_nonzero(last < 128)) > 40


def test_glued_nine_is_not_read_as_seven():
    from backend.digit_icr import read_four_blocks

    path = "storage/debug/image1/cells/ANC_row_raw.jpg"
    row = cv2.imread(path)
    if row is None:
        pytest.skip("debug image1 ANC row not present")
    votes, _, digits = read_four_blocks(row)
    assert digits[3] == 9
    assert votes == 9


def test_centered_thin_one_is_not_removed_as_divider():
    import numpy as np
    from backend.digit_icr import _cell_mask, classify_digit_mask, suppress_result_dividers

    cell = np.full((80, 50, 3), 255, dtype=np.uint8)
    cv2.line(cell, (25, 18), (25, 64), (0, 0, 0), 4)
    digit, confidence = classify_digit_mask(_cell_mask(cell))
    assert digit == 1
    assert confidence >= 0.8

    # A real 1 in the middle of a box must survive divider suppression.
    row = np.full((40, 200, 3), 255, dtype=np.uint8)
    cv2.line(row, (25, 8), (25, 32), (0, 0, 0), 3)
    cleaned = suppress_result_dividers(row)
    ink = cv2.countNonZero(cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY) < 128)
    assert ink > 20


def test_gapped_dashes_and_blank_cells_are_not_votes():
    import numpy as np
    from backend.digit_icr import (
        cell_looks_blank,
        classify_digit_mask,
        _cell_mask,
        suppress_result_dividers,
    )

    row = np.full((46, 228, 3), 255, dtype=np.uint8)
    for x in (0, 57, 114, 171, 227):
        for y in range(4, 42, 8):
            cv2.line(row, (x, y), (x, min(41, y + 4)), (40, 40, 40), 2)
    cleaned = suppress_result_dividers(row)
    gray = cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY)
    for x in (57, 114, 171):
        assert int(gray[:, max(0, x - 1) : x + 2].mean()) > 230

    blank = np.full((80, 50, 3), 248, dtype=np.uint8)
    cv2.line(blank, (48, 6), (48, 20), (170, 170, 170), 1)
    assert cell_looks_blank(blank) is True
    digit, conf = classify_digit_mask(_cell_mask(blank))
    assert digit is None
    assert conf >= 0.8

    faint_one = np.full((80, 50, 3), 250, dtype=np.uint8)
    cv2.line(faint_one, (25, 16), (25, 66), (155, 155, 155), 3)
    assert cell_looks_blank(faint_one) is False

    edge = np.full((80, 50, 3), 250, dtype=np.uint8)
    cv2.line(edge, (2, 8), (2, 72), (155, 155, 155), 2)
    assert cell_looks_blank(edge) is True


def test_edge_dash_is_not_read_as_one():
    import numpy as np
    from backend.digit_icr import _cell_mask, classify_digit_mask, suppress_result_dividers

    cell = np.full((80, 50, 3), 255, dtype=np.uint8)
    cv2.line(cell, (48, 4), (48, 76), (0, 0, 0), 2)
    digit, _ = classify_digit_mask(_cell_mask(cell))
    assert digit is None

    row = np.full((46, 228, 3), 255, dtype=np.uint8)
    for x in (0, 57, 114, 171, 227):
        cv2.line(row, (x, 2), (x, 44), (0, 0, 0), 2)
    cleaned = suppress_result_dividers(row)
    gray = cv2.cvtColor(cleaned, cv2.COLOR_BGR2GRAY)
    for x in (57, 114, 171):
        assert int(gray[:, max(0, x - 1) : x + 2].mean()) > 240


def test_partial_row_grid_is_extrapolated_not_compressed():
    from backend.digit_icr import align_rows_to_template

    rows = align_rows_to_template(list(range(100, 270, 10)), num_rows=23)
    assert len(rows) == 23
    assert rows[0] == (100, 110)
    assert rows[-1] == (320, 330)


def test_fuse_prefers_strong_rapid_over_blank_icr():
    from backend.result_box_ocr import (
        dash_inflated,
        extra_separator_digit,
        fuse_result_votes,
        looks_like_dash_noise,
    )

    votes, conf, used_rapid = fuse_result_votes(0, 0.90, 9, 0.92, 0.20, registered_voters=165)
    assert votes == 9
    assert used_rapid is True
    assert conf >= 0.70

    votes, _, used_rapid = fuse_result_votes(481, 0.80, 81, 0.91, 0.20, registered_voters=1149)
    assert votes == 481
    assert used_rapid is False

    # Rapid dropped the last 1 of 481.
    votes, _, used_rapid = fuse_result_votes(481, 0.80, 48, 0.92, 0.20, registered_voters=1149)
    assert votes == 481
    assert used_rapid is False

    # ICR dropped the last 1 of 481; Rapid kept it.
    votes, _, used_rapid = fuse_result_votes(48, 0.80, 481, 0.91, 0.20, registered_voters=1149)
    assert votes == 481
    assert used_rapid is True

    votes, _, used_rapid = fuse_result_votes(52, 0.80, 1512, 0.90, 0.22, registered_voters=3080)
    assert votes == 52
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(100, 0.80, 9, 0.92, 0.20, registered_voters=165)
    assert votes == 9
    assert used_rapid is True

    votes, _, used_rapid = fuse_result_votes(27, 0.80, 287, 0.90, 0.22, registered_voters=3080)
    assert votes == 27
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(9, 0.80, 39, 0.90, 0.20, registered_voters=165)
    assert votes == 9
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(77, 0.80, 772, 0.92, 0.22, registered_voters=1149)
    assert votes == 77
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(0, 0.90, 903, 0.91, 0.20, registered_voters=1149)
    assert votes == 0
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(1816, 0.80, 1814, 0.92, 0.20, registered_voters=3080)
    assert votes == 1816
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(0, 0.90, 1816, 0.91, 0.20, registered_voters=3080)
    assert votes == 1816
    assert used_rapid is True

    assert looks_like_dash_noise(1111) is True
    assert looks_like_dash_noise(903) is True
    assert looks_like_dash_noise(18) is False
    assert looks_like_dash_noise(481) is False
    assert dash_inflated(1512, 52) is True
    assert dash_inflated(18, 10) is False
    assert extra_separator_digit(287, 27) is True
    assert extra_separator_digit(39, 9) is True
    assert extra_separator_digit(222, 22) is True
    assert extra_separator_digit(481, 48) is False
    assert dash_inflated(481, 48) is False
    votes, _, used_rapid = fuse_result_votes(2, 0.80, 72, 0.90, 0.18, registered_voters=3080)
    assert votes == 2
    assert used_rapid is False

    assert extra_separator_digit(72, 2) is True
    assert extra_separator_digit(91, 1) is True
    assert extra_separator_digit(13, 1) is False

    votes, _, used_rapid = fuse_result_votes(3, 0.80, 27, 0.66, 0.16, registered_voters=3080)
    assert votes == 27
    assert used_rapid is True

    # ICR read a trailing 8 as Ø (10); Rapid kept 18.
    votes, _, used_rapid = fuse_result_votes(10, 0.80, 18, 0.84, 0.20, registered_voters=165)
    assert votes == 18
    assert used_rapid is True

    # Same pattern at the Rapid conf we see on high-res VF PLUS.
    votes, _, used_rapid = fuse_result_votes(10, 0.80, 18, 0.74, 0.04, registered_voters=165)
    assert votes == 18
    assert used_rapid is True

    # registered_voters OCR missed, so Rapid 218/818 is not rejected as too large.
    votes, _, used_rapid = fuse_result_votes(10, 0.80, 218, 0.79, 0.04, registered_voters=None)
    assert votes == 18
    assert used_rapid is True

    votes, _, used_rapid = fuse_result_votes(10, 0.80, 818, 0.85, 0.04, registered_voters=None)
    assert votes == 18
    assert used_rapid is True

    # Divider-glued 9 remnant: Rapid 4 must not beat ICR 9.
    votes, _, used_rapid = fuse_result_votes(9, 0.80, 4, 0.92, 0.20, registered_voters=165)
    assert votes == 9
    assert used_rapid is False

    votes, _, used_rapid = fuse_result_votes(0, 0.90, 7, 0.92, 0.014, registered_voters=3080)
    assert votes == 7
    assert used_rapid is True

    # Topology ICR reads a 2 as 5 (ASA) and a 3 as 7 (UDM); Rapid is sure.
    votes, _, used_rapid = fuse_result_votes(5, 0.80, 2, 0.92, 0.18, registered_voters=3080)
    assert votes == 2
    assert used_rapid is True

    votes, _, used_rapid = fuse_result_votes(7, 0.80, 3, 0.92, 0.18, registered_voters=3080)
    assert votes == 3
    assert used_rapid is True

    # ICR dropped the leading digit of 41 (4-stem sat on the divider).
    votes, _, used_rapid = fuse_result_votes(11, 0.80, 41, 0.92, 0.18, registered_voters=3080)
    assert votes == 41
    assert used_rapid is True

    # ICR 2-digit near-miss (BOSA 14, RISE 48); Rapid is sure.
    votes, _, used_rapid = fuse_result_votes(14, 0.80, 15, 0.92, 0.18, registered_voters=3080)
    assert votes == 15
    assert used_rapid is True

    votes, _, used_rapid = fuse_result_votes(48, 0.80, 52, 0.92, 0.18, registered_voters=3080)
    assert votes == 52
    assert used_rapid is True

    assert looks_like_dash_noise(2212) is True


def test_result_header_anchor_is_not_mapped_to_first_party():
    from backend.digit_icr import align_rows_to_template

    # 215 is the table-header top; 260 is the first party-row boundary.
    detected = [215, 237, 260, 286, 310, 333, 355, 376, 397]
    rows = align_rows_to_template(detected, num_rows=8, min_y=245)
    assert rows[0] == (260, 286)
    assert rows[1] == (286, 310)


@pytest.mark.parametrize(
    ("path", "expected_left", "expected_right"),
    [
        ("sample_slips/ResultSlip.jpg", (0.53, 0.62), (0.69, 0.77)),
        (
            "sample_slips/Result_Slip_2024_Previous_Election_Sample.jpg",
            (0.57, 0.66),
            (0.75, 0.84),
        ),
    ],
)
def test_result_grid_topology_keeps_all_four_cells(
    enhancer,
    path,
    expected_left,
    expected_right,
):
    from backend.digit_icr import (
        detect_result_column_geometry,
        extract_result_row,
        result_column_bounds_at,
    )

    img = enhancer.load_file_as_cv2(path)
    enhanced = enhancer.process_image(img).enhanced_image
    gray = cv2.cvtColor(enhanced, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    geometry = detect_result_column_geometry(gray, int(h * 0.28), int(h * 0.88))
    left, right = result_column_bounds_at(geometry, h * 0.58)

    assert expected_left[0] <= left / w <= expected_left[1]
    assert expected_right[0] <= right / w <= expected_right[1]

    row = extract_result_row(enhanced, geometry, int(h * 0.40), int(h * 0.44))
    assert row.shape[1] >= int(w * 0.13)


def test_limpopo_provincial_layouts_match_printed_rows(ocr_engine):
    page1 = ocr_engine._choose_layout(
        "Provincial",
        1,
        ["BOLSHEVIKS PARTY OF SOUTH AFRICA BPSA", "SAMEBA", "SADA"],
    )
    page2 = ocr_engine._choose_layout(
        "Provincial",
        2,
        ["UDM VF PLUS ACTIONSA ACDP AMC APC ATM ALJAMA ACP"],
    )
    assert [code for _, code in page1][2] == "BPSA"
    assert [code for _, code in page1][-2:] == ["M.K.", "UAT"]
    assert [code for _, code in page2][:2] == ["UDM", "VF PLUS"]
    assert [code for _, code in page2][-2:] == ["ALJAMA", "ACP"]


def test_limpopo_national_page_2(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_2.jpg")
    assert data["ballot_type"] == "National"
    assert data["page_number"] == 2
    assert data["page_total"] == 3
    assert "001334762402341021" in data["barcode_text"]


def test_limpopo_national_final_page_identity(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_3.jpg")
    assert data["page_number"] == 3
    assert data["page_total"] == 3
    assert "001334762402341031" in (data["barcode_text"] or "")


def test_limpopo_regional_page_1(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_4.jpg")
    assert data["ballot_type"] == "Regional"
    assert data["page_number"] == 1
    assert data["page_total"] == 3


def test_limpopo_provincial_page_1_identity(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_7.jpg")
    assert data["ballot_type"] == "Provincial"
    assert data["voting_district"] == "76240234"
    assert data["page_number"] == 1
    assert "001335762402342011" in (data["barcode_text"] or "")


def test_lookup_does_not_inflate_confidence(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_1.jpg")
    scores = [p["confidence_score"] for p in data["party_results"]]
    assert scores
    assert max(scores) <= 0.95
    assert 0.96 not in scores
    assert 0.99 not in scores
    # Low-confidence or empty-digit rows should still surface for review.
    assert any(s < LOW_VOTE_CONFIDENCE for s in scores) or any(data.get("exception_flags") or [])


def test_page_looks_like_result_slip_requires_evidence():
    from backend.ocr_engine import page_looks_like_result_slip

    assert page_looks_like_result_slip(["random shopping receipt"], layout_score=0) is False
    assert page_looks_like_result_slip(["hello"], barcode_info={"slip_reference": "001335970900502"}) is True
    assert page_looks_like_result_slip(["header"], voting_district="76240234") is True
    assert page_looks_like_result_slip(
        ["IEC RESULT SLIP", "REGISTERED VOTERS 165"],
        layout_score=0,
    ) is True
    assert page_looks_like_result_slip(["AFRICAN NATIONAL CONGRESS"], layout_score=4) is True


def test_blank_image_is_not_treated_as_result_slip(ocr_engine):
    import numpy as np

    blank = np.full((320, 240, 3), 240, dtype=np.uint8)
    data = ocr_engine.extract_full_slip_data(blank)
    assert data["is_vote_related"] is False
    assert data["party_results"] == []
    assert data["voting_district"] == "UNKNOWN"
    assert data["slip_reference"].startswith("UNREAD_")
    assert "not_a_result_slip" in data["exception_flags"]


def test_vote_cells_gold_and_hybrid_export_split():
    import json
    from pathlib import Path
    from backend.digit_finetune.export_result_cells import validate_cell_labels
    from backend.digit_icr import hybrid_result_cells, split_result_cells, scale_result_row

    gold = json.loads(Path("tests/fixtures/sample_gold.json").read_text())
    assert gold["ResultSlip.jpg"]["vote_cells"]["VF PLUS"] == [0, 0, 1, 8]
    assert gold["ResultSlip.jpg"]["vote_cells"]["SUN"] == [0, 0, 0, 1]
    assert validate_cell_labels([0, 0, 1, 8]) == [0, 0, 1, 8]
    assert validate_cell_labels([None, None, None, None]) == [None, None, None, None]
    assert validate_cell_labels([1, 2]) is None

    row = cv2.imread("storage/debug/ResultSlip/cells/VF_PLUS_row_raw.jpg")
    if row is None:
        pytest.skip("debug VF PLUS row not present")
    cells = hybrid_result_cells(row)
    assert len(cells) == 4
    cleaned = split_result_cells(scale_result_row(row))
    assert cleaned[3].shape == cells[3].shape


def test_hybrid_augment_keeps_blank_class_and_shape():
    import numpy as np
    from backend.digit_finetune.hard_augment import BLANK_CLASS, hard_augment_digit

    blank = np.zeros((28, 28), dtype=np.uint8)
    out, lab = hard_augment_digit(blank, BLANK_CLASS, style="hybrid", force_box=True)
    assert lab == BLANK_CLASS
    assert out.shape == (28, 28)
    digit = np.zeros((28, 28), dtype=np.uint8)
    cv2.circle(digit, (14, 14), 8, 255, 2)
    out, lab = hard_augment_digit(digit, 0, style="hybrid")
    assert lab == 0
    assert out.shape == (28, 28)


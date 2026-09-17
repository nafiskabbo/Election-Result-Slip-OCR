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

    # Right-aligned with empty leading boxes (no written leading zero)
    assert digits_to_votes([None, None, None, 9])[0] == 9
    assert digits_to_votes([None, None, 1, 8])[0] == 18
    assert digits_to_votes([None, 8, 1, 6])[0] == 816
    assert digits_to_votes([None, None, 5, 1])[0] == 51
    assert digits_to_votes([None, None, None, 1])[0] == 1


def test_centered_thin_one_is_not_removed_as_divider():
    import numpy as np
    from backend.digit_icr import _cell_mask, classify_digit_mask

    cell = np.full((80, 50, 3), 255, dtype=np.uint8)
    cv2.line(cell, (25, 18), (25, 64), (0, 0, 0), 4)
    digit, confidence = classify_digit_mask(_cell_mask(cell))
    assert digit == 1
    assert confidence >= 0.8


def test_partial_row_grid_is_extrapolated_not_compressed():
    from backend.digit_icr import align_rows_to_template

    rows = align_rows_to_template(list(range(100, 270, 10)), num_rows=23)
    assert len(rows) == 23
    assert rows[0] == (100, 110)
    assert rows[-1] == (320, 330)


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

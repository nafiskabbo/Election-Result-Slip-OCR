from backend.lg2026_forms import (
    BALLOT_DISTRICT_PR,
    BALLOT_LOCAL_PR,
    BALLOT_WARD,
    FAMILY_IEC_2024,
    FAMILY_LG_2026,
    classify_result_form,
    fit_vote_to_digit_count,
    parse_open_votes,
    _choose_vote,
    _reconcile_totals,
    _snap_ward_abbr,
)
from backend.ocr_engine import OCREngine


def test_classify_prefers_2026_titles_over_barcode_collision():
    yellow = classify_result_form(["District Council PR Results Form", "Yellow Ballot Paper"])
    assert yellow["family"] == FAMILY_LG_2026
    assert yellow["ballot_type"] == BALLOT_DISTRICT_PR

    local = classify_result_form(["Local Council PR Results Form", "Green Ballot Paper"])
    assert local["ballot_type"] == BALLOT_LOCAL_PR

    ward = classify_result_form(["Ward Candidate Results Form", "White Ballot Paper"])
    assert ward["ballot_type"] == BALLOT_WARD

    dc40 = classify_result_form(["KZN227 Ward#52207001 VD:43960024 DC40 Ballot"])
    assert dc40["ballot_type"] == BALLOT_DISTRICT_PR


def test_classify_keeps_2024_result_slips():
    national = classify_result_form(["NATIONAL BALLOT", "RESULT SLIP", "AFRICAN NATIONAL CONGRESS"])
    assert national["family"] == FAMILY_IEC_2024

    boxed = classify_result_form(["header only"], has_four_box_grid=True)
    assert boxed["family"] == FAMILY_IEC_2024


def test_lg2026_barcode_does_not_become_regional():
    engine = OCREngine()
    old = engine.parse_barcode_reference("001334762402341011")
    assert old["ballot_type"] == "National"
    assert old["voting_district"] == "76240234"

    regional = engine.parse_barcode_reference("001334762402343011")
    assert regional["ballot_type"] == "Regional"

    local = engine.parse_barcode_reference("011965439600243012", family="lg2026")
    assert local["ballot_type"] == "Local Council PR"
    assert local["voting_district"] == "43960024"
    assert local["page_number"] == 1

    district = engine.parse_barcode_reference("011965439600246012", family="lg2026")
    assert district["ballot_type"] == "District Council PR"

    ward = engine.parse_barcode_reference("011965439600244022", family="lg2026")
    assert ward["ballot_type"] == "Ward"
    assert ward["page_number"] == 2


def test_parse_open_votes_handles_rewrite_and_lookalikes():
    assert parse_open_votes("250") == 250
    assert parse_open_votes("I5") == 15
    assert parse_open_votes("VS731") == 731
    assert parse_open_votes("2513195") == 3195
    assert parse_open_votes("8b") == 98
    assert parse_open_votes("b") == 9
    assert parse_open_votes("bb") == 99
    assert parse_open_votes("6于") == 67


def test_snap_ward_abbr():
    assert _snap_ward_abbr("TRAF") == "TRAFI"
    assert _snap_ward_abbr("TRMAE") == "TRAAE"
    assert _snap_ward_abbr("TRAAN") == "TRAAN"
    assert _snap_ward_abbr("TRAB") == "TRAAB"


def test_choose_vote_completes_missing_leading_digit():
    assert _choose_vote(8, 98) == 98
    assert _choose_vote(0, 100) == 100
    assert _choose_vote(67, 6) == 67
    assert _choose_vote(9, 94) == 9
    assert _choose_vote(None, 99) == 99
    assert _choose_vote(7, 707) == 7
    assert _choose_vote(0, 7001) == 0
    assert _choose_vote(60, 600) == 60
    assert _choose_vote(0, 60) == 60


def test_fit_vote_drops_duplicated_loop_zero():
    assert fit_vote_to_digit_count(600, 2) == 60
    assert fit_vote_to_digit_count(100, 3) == 100
    assert fit_vote_to_digit_count(250, 3) == 250
    assert fit_vote_to_digit_count(98, 2) == 98
    assert fit_vote_to_digit_count(10, 1) == 0
    assert fit_vote_to_digit_count(7, 1) == 7
    assert fit_vote_to_digit_count(160, 3) == 160


def test_reconcile_totals_uses_printed_identity():
    merged = _reconcile_totals({"valid": 1335, "spoilt": 60, "cast": 3195})
    assert merged["cast"] == 1395
    filled = _reconcile_totals({"valid": 405, "spoilt": None, "cast": 505})
    assert filled["spoilt"] == 100
    truncated = _reconcile_totals({"valid": 405, "spoilt": 10, "cast": 505})
    assert truncated["spoilt"] == 100
    # Struck-through valid remnant + written cast/spoilt → valid = cast - spoilt.
    keep = _reconcile_totals({"valid": 120, "spoilt": 100, "cast": 731})
    assert keep["cast"] == 731
    assert keep["valid"] == 631
    unread_spoilt = _reconcile_totals({"valid": 731, "spoilt": 1, "cast": 731})
    assert unread_spoilt["cast"] == 731
    assert unread_spoilt["valid"] == 731

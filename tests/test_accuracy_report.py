from backend.accuracy_check import format_report_markdown, format_report_text, snapshot_extracted


def test_snapshot_extracted_copies_votes_and_identity():
    snap = snapshot_extracted({
        "ballot_type": "Provincial",
        "page_number": 1,
        "page_total": 2,
        "voting_district": "86820598",
        "presiding_officer_name": "THABO",
        "total_valid_votes": 52,
        "exception_flags": ["low_confidence_digits"],
        "party_results": [
            {
                "party_code": "ANC",
                "party_name": "AFRICAN NATIONAL CONGRESS",
                "votes": 9,
                "confidence_score": 0.8,
                "cnn_votes": 8,
                "cnn_confidence": 0.5,
            },
            {"party_code": "DA", "party_name": "DEMOCRATIC ALLIANCE", "votes": 18, "confidence_score": 0.72},
            {"party_code": "GOOD", "party_name": "GOOD", "votes": 0, "confidence_score": 0.9},
        ],
    })
    assert snap["ballot_type"] == "Provincial"
    assert snap["officer"] == "THABO"
    assert snap["total_valid_votes"] == 52
    assert [p["code"] for p in snap["parties"] if p["votes"]] == ["ANC", "DA"]
    assert snap["parties"][0]["cnn_votes"] == 8


def test_format_report_markdown_has_compare_tables():
    result = {
        "images": 1,
        "labeled": 1,
        "unlabeled": 0,
        "labeled_hits": 1,
        "labeled_total": 2,
        "iec_hits": 1,
        "iec_total": 2,
        "heuristic_vote_hits": 1,
        "heuristic_vote_total": 2,
        "cnn_vote_hits": 0,
        "cnn_vote_total": 2,
        "pages": [
            {
                "file": "ResultSlip.jpg",
                "ok": True,
                "seconds": 1.0,
                "unlabeled": False,
                "hits": 1,
                "total": 2,
                "extracted": {
                    "ballot_type": "Provincial",
                    "page_number": 1,
                    "page_total": 2,
                    "voting_district": "86820598",
                    "barcode_text": "001335868205982011",
                    "station_name": "BRITTEN",
                    "registered_voters": 165,
                    "parties": [],
                    "exception_flags": [],
                },
                "checks": [
                    {"field": "votes.ANC", "actual": 9, "expected": 9, "ok": True},
                    {"field": "votes.DA", "actual": 0, "expected": 18, "ok": False},
                ],
                "vote_compare": [
                    {
                        "code": "ANC",
                        "expected": 9,
                        "heuristic": 9,
                        "cnn_votes": 8,
                        "heuristic_ok": True,
                        "cnn_ok": False,
                    },
                    {
                        "code": "DA",
                        "expected": 18,
                        "heuristic": 0,
                        "cnn_votes": 5,
                        "heuristic_ok": False,
                        "cnn_ok": False,
                    },
                ],
            },
        ],
    }
    md = format_report_markdown(result, use_known=False)
    assert "# Sample-slip accuracy report" in md
    assert "| Party | Expected | Heuristic ICR | Digit CNN |" in md
    assert "ANC" in md and "9" in md
    assert "Vote-accuracy winner" in md


def test_format_report_text_shows_got_expected_and_unlabeled_votes():
    result = {
        "images": 2,
        "labeled": 1,
        "unlabeled": 1,
        "labeled_hits": 1,
        "labeled_total": 2,
        "iec_hits": 1,
        "iec_total": 2,
        "pages": [
            {
                "file": "p_1.jpg",
                "ok": True,
                "seconds": 1.2,
                "unlabeled": False,
                "hits": 1,
                "total": 2,
                "extracted": {
                    "ballot_type": "National",
                    "parties": [
                        {"code": "ANC", "name": "AFRICAN NATIONAL CONGRESS", "votes": 400, "confidence": 0.8},
                        {"code": "EFF", "name": "ECONOMIC FREEDOM FIGHTERS", "votes": 12, "confidence": 0.7},
                    ],
                    "exception_flags": [],
                },
                "checks": [
                    {"field": "votes.ANC", "actual": 400, "expected": 481, "ok": False},
                    {"field": "votes.DA", "actual": 5, "expected": 5, "ok": True},
                ],
            },
            {
                "file": "ResultSlip.jpg",
                "ok": True,
                "seconds": 2.0,
                "unlabeled": True,
                "extracted": {
                    "ballot_type": "Provincial",
                    "page_number": 1,
                    "page_total": 2,
                    "voting_district": "86820598",
                    "station_name": "BRITTEN STATION SHOP",
                    "registered_voters": 165,
                    "barcode_text": "001335868205982011",
                    "parties": [
                        {"code": "ANC", "name": "AFRICAN NATIONAL CONGRESS", "votes": 9, "confidence": 0.8},
                        {"code": "DA", "name": "DEMOCRATIC ALLIANCE", "votes": 18, "confidence": 0.7},
                    ],
                    "exception_flags": [],
                },
                "checks": [],
            },
        ],
    }
    text = format_report_text(result, use_known=True)
    assert "Upload API / desk path" in text
    assert "p_1.jpg  votes.ANC: got 400  expected 481" in text
    assert "votes.EFF: got 12  expected 0 (not in gold)  EXTRA" in text
    assert "ResultSlip.jpg" in text
    assert "ANC" in text and "9" in text
    assert "DA" in text and "18" in text
    assert "unlabeled" in text
    assert "KNOWN_SLIPS applied for 001335868205982011" in text


def test_extract_page_defaults_to_desk_lookup():
    import inspect
    from backend.page_pipeline import extract_page_from_file

    assert inspect.signature(extract_page_from_file).parameters["use_known"].default is True


def test_upload_uses_shared_pipeline():
    import inspect
    from backend.routes.upload import _process_saved_file

    source = inspect.getsource(_process_saved_file)
    assert "extract_page_from_file" in source
    assert "use_known=True" in source


def test_digit_cnn_blank_and_synth_nine():
    import cv2
    import numpy as np
    from backend.digit_cnn import classify_cell_cnn, ensure_model

    ensure_model()
    blank = np.full((40, 30, 3), 240, dtype=np.uint8)
    digit, conf = classify_cell_cnn(blank)
    assert digit is None
    assert conf >= 0.5

    canvas = np.full((48, 36, 3), 240, dtype=np.uint8)
    cv2.putText(canvas, "9", (6, 38), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (20, 20, 20), 2)
    digit, conf = classify_cell_cnn(canvas)
    assert digit == 9
    assert conf > 0.5

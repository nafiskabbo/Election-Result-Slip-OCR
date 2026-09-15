import pytest
from backend.database import get_db_connection
from backend.validation_engine import ValidationEngine

pytestmark = pytest.mark.usefixtures("postgres_db")


def test_validation_math_reconciliation():
    validator = ValidationEngine()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO slips (
            id, slip_reference, ballot_type, election_name, voting_district,
            registered_voters, status, total_valid_votes, total_spoilt_votes, total_votes_cast,
            total_expected_pages, total_received_pages, presiding_officer_signature_detected,
            created_at, updated_at
        ) VALUES (
            'slip_test_val', 'REF123', 'Regional', '2024 Election', '12345678',
            100, 'pending_review', 50, 2, 52,
            1, 1, true, '2026-01-01', '2026-01-01'
        )
    """)
    cursor.execute("""
        INSERT INTO slip_pages (
            id, slip_id, page_number, page_total, raw_file_path, enhanced_file_path,
            status, upload_timestamp, file_size, mime_type
        ) VALUES ('page_test', 'slip_test_val', 1, 1, 'raw.jpg', 'enh.jpg', 'valid', '2026-01-01', 100, 'image/jpeg')
    """)
    cursor.execute("""
        INSERT INTO party_results (
            id, slip_id, page_id, row_index, party_name, party_code, votes,
            confidence_score, is_overridden, original_ocr_votes, signature_detected
        ) VALUES ('pr_1', 'slip_test_val', 'page_test', 0, 'Party A', 'PA', 30, 0.95, false, 30, true),
                 ('pr_2', 'slip_test_val', 'page_test', 1, 'Party B', 'PB', 20, 0.95, false, 20, true)
    """)
    conn.commit()
    conn.close()

    res = validator.evaluate_slip("slip_test_val")
    assert res["is_eligible_for_approval"] is True
    assert res["has_critical_error"] is False

    rule_map = {r["rule_code"]: r["status"] for r in res["validation_results"]}
    assert rule_map["SUM_PARTY_VOTES_MATCH"] == "pass"
    assert rule_map["RECONCILIATION_MATCH"] == "pass"
    assert rule_map["TURNOUT_CEILING"] == "pass"


def test_validation_turnout_ceiling_exceeded():
    validator = ValidationEngine()
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO slips (
            id, slip_reference, ballot_type, election_name, voting_district,
            registered_voters, status, total_valid_votes, total_spoilt_votes, total_votes_cast,
            total_expected_pages, total_received_pages, presiding_officer_signature_detected,
            created_at, updated_at
        ) VALUES (
            'slip_turnout_err', 'REF_TURNOUT', 'National', '2024 Election', '99999999',
            100, 'pending_review', 150, 0, 150,
            1, 1, true, '2026-01-01', '2026-01-01'
        )
    """)
    cursor.execute("""
        INSERT INTO slip_pages (
            id, slip_id, page_number, page_total, raw_file_path, enhanced_file_path,
            status, upload_timestamp, file_size, mime_type
        ) VALUES ('page_to', 'slip_turnout_err', 1, 1, 'raw.jpg', 'enh.jpg', 'valid', '2026-01-01', 100, 'image/jpeg')
    """)
    conn.commit()
    conn.close()

    res = validator.evaluate_slip("slip_turnout_err")
    rule_map = {r["rule_code"]: r["status"] for r in res["validation_results"]}
    assert rule_map["TURNOUT_CEILING"] == "fail"
    assert res["is_eligible_for_approval"] is False

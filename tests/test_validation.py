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


def test_validation_votes_within_registered():
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
            'slip_over_reg', 'REF_OVER', 'National', '2024 Election', '76240234',
            100, 'pending_review', 120, 0, 120,
            1, 1, true, '2026-01-01', '2026-01-01'
        )
    """)
    cursor.execute("""
        INSERT INTO slip_pages (
            id, slip_id, page_number, page_total, raw_file_path, enhanced_file_path,
            status, upload_timestamp, file_size, mime_type
        ) VALUES ('page_over', 'slip_over_reg', 1, 1, 'raw.jpg', 'enh.jpg', 'valid', '2026-01-01', 100, 'image/jpeg')
    """)
    cursor.execute("""
        INSERT INTO party_results (
            id, slip_id, page_id, row_index, party_name, party_code, votes,
            confidence_score, is_overridden, original_ocr_votes, signature_detected
        ) VALUES ('pr_over', 'slip_over_reg', 'page_over', 0, 'Party A', 'PA', 120, 0.95, false, 120, true)
    """)
    conn.commit()
    conn.close()

    res = validator.evaluate_slip("slip_over_reg")
    rule_map = {r["rule_code"]: r["status"] for r in res["validation_results"]}
    assert rule_map["TURNOUT_CEILING"] == "fail"
    assert rule_map["VOTES_WITHIN_REGISTERED"] == "fail"
    assert res["is_eligible_for_approval"] is False


def test_validation_party_sum_within_registered_before_final_totals():
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
            'slip_party_ok', 'REF_OK', 'National', '2024 Election', '76240234',
            1149, 'incomplete', 0, 0, 0,
            3, 1, false, '2026-01-01', '2026-01-01'
        )
    """)
    cursor.execute("""
        INSERT INTO slip_pages (
            id, slip_id, page_number, page_total, raw_file_path, enhanced_file_path,
            status, upload_timestamp, file_size, mime_type
        ) VALUES ('page_ok', 'slip_party_ok', 1, 3, 'raw.jpg', 'enh.jpg', 'valid', '2026-01-01', 100, 'image/jpeg')
    """)
    cursor.execute("""
        INSERT INTO party_results (
            id, slip_id, page_id, row_index, party_name, party_code, votes,
            confidence_score, is_overridden, original_ocr_votes, signature_detected
        ) VALUES ('pr_ok1', 'slip_party_ok', 'page_ok', 0, 'ANC', 'ANC', 481, 0.9, false, 481, true),
                 ('pr_ok2', 'slip_party_ok', 'page_ok', 1, 'EFF', 'EFF', 77, 0.9, false, 77, true)
    """)
    conn.commit()
    conn.close()

    res = validator.evaluate_slip("slip_party_ok")
    rule_map = {r["rule_code"]: r["status"] for r in res["validation_results"]}
    assert rule_map["VOTES_WITHIN_REGISTERED"] == "pass"
    assert rule_map["TURNOUT_CEILING"] == "pass"

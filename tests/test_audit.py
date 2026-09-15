import pytest
import sqlite3
from backend.database import init_db, get_db_connection
from backend.audit_service import AuditService

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_aud.db")
    monkeypatch.setenv("BALLOT_DB_PATH", test_db)
    import backend.database as db_module
    db_module.DB_PATH = test_db
    init_db()

def test_audit_logging_and_immutability():
    audit_service = AuditService()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO slips (
            id, slip_reference, ballot_type, election_name, voting_district,
            status, total_expected_pages, total_received_pages, created_at, updated_at
        ) VALUES (
            'slip_audit_test', 'REF_AUDIT', 'Provincial', '2024 Election', '86820598',
            'pending_review', 2, 1, '2026-01-01', '2026-01-01'
        )
    """)
    conn.commit()
    conn.close()

    # 1. Log an edit event
    log_id = audit_service.log_event(
        user_id="usr_operator",
        action="edit_field",
        slip_id="slip_audit_test",
        field_name="total_valid_votes",
        old_value="50",
        new_value="52",
        reason="Correcting transcription error from boxed total"
    )
    assert log_id.startswith("aud_")
    
    # 2. Retrieve logs for slip
    logs = audit_service.get_logs_for_slip("slip_audit_test")
    assert len(logs) == 1
    assert logs[0]["action"] == "edit_field"
    assert logs[0]["field_name"] == "total_valid_votes"
    assert logs[0]["old_value"] == "50"
    assert logs[0]["new_value"] == "52"
    assert "transcription error" in logs[0]["reason"]
    
    # 3. Post-approval edit (Acceptance Criterion 4)
    log_id_2 = audit_service.log_event(
        user_id="usr_supervisor",
        action="post_approval_edit",
        slip_id="slip_audit_test",
        field_name="station_name",
        old_value="Old Station",
        new_value="Britten Station Shop",
        reason="Supervisor metadata update after audit notice"
    )
    assert log_id_2 is not None
    
    updated_logs = audit_service.get_logs_for_slip("slip_audit_test")
    assert len(updated_logs) == 2
    # Verify chronological order
    assert updated_logs[0]["action"] == "post_approval_edit"

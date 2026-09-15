import sqlite3
import json
import os
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

DB_PATH = os.environ.get("BALLOT_DB_PATH", "ballot_ocr.db")

def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'supervisor', 'operator', 'auditor')),
        created_at TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS slips (
        id TEXT PRIMARY KEY,
        slip_reference TEXT NOT NULL,
        ballot_type TEXT NOT NULL,
        election_name TEXT NOT NULL,
        province TEXT,
        municipality TEXT,
        voting_district TEXT NOT NULL,
        station_name TEXT,
        registered_voters INTEGER DEFAULT 0,
        status TEXT NOT NULL CHECK(status IN ('incomplete', 'pending_review', 'approved', 'rejected', 'flagged')),
        presiding_officer_name TEXT,
        presiding_officer_signature_detected INTEGER DEFAULT 0,
        total_valid_votes INTEGER DEFAULT 0,
        total_spoilt_votes INTEGER DEFAULT 0,
        total_votes_cast INTEGER DEFAULT 0,
        special_votes INTEGER DEFAULT 0,
        section_24a_votes INTEGER DEFAULT 0,
        total_expected_pages INTEGER NOT NULL DEFAULT 1,
        total_received_pages INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        approved_at TEXT,
        approved_by TEXT,
        rejection_reason TEXT,
        FOREIGN KEY (approved_by) REFERENCES users(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS slip_pages (
        id TEXT PRIMARY KEY,
        slip_id TEXT NOT NULL,
        page_number INTEGER NOT NULL,
        page_total INTEGER NOT NULL,
        barcode_text TEXT,
        raw_file_path TEXT NOT NULL,
        enhanced_file_path TEXT NOT NULL,
        thumbnail_path TEXT,
        status TEXT NOT NULL,
        upload_timestamp TEXT NOT NULL,
        file_size INTEGER NOT NULL,
        mime_type TEXT NOT NULL,
        exception_flags TEXT,
        FOREIGN KEY (slip_id) REFERENCES slips(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS party_results (
        id TEXT PRIMARY KEY,
        slip_id TEXT NOT NULL,
        page_id TEXT NOT NULL,
        row_index INTEGER NOT NULL,
        party_name TEXT NOT NULL,
        party_code TEXT NOT NULL,
        votes INTEGER NOT NULL DEFAULT 0,
        confidence_score REAL NOT NULL DEFAULT 1.0,
        is_overridden INTEGER NOT NULL DEFAULT 0,
        overridden_by TEXT,
        original_ocr_votes INTEGER NOT NULL DEFAULT 0,
        signature_detected INTEGER NOT NULL DEFAULT 0,
        bbox_json TEXT,
        FOREIGN KEY (slip_id) REFERENCES slips(id) ON DELETE CASCADE,
        FOREIGN KEY (page_id) REFERENCES slip_pages(id) ON DELETE CASCADE
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS audit_logs (
        id TEXT PRIMARY KEY,
        slip_id TEXT,
        page_id TEXT,
        user_id TEXT NOT NULL,
        action TEXT NOT NULL,
        field_name TEXT,
        old_value TEXT,
        new_value TEXT,
        reason TEXT,
        ip_address TEXT,
        timestamp TEXT NOT NULL,
        FOREIGN KEY (slip_id) REFERENCES slips(id) ON DELETE SET NULL,
        FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS validation_rules (
        id TEXT PRIMARY KEY,
        rule_code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT NOT NULL,
        rule_type TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        severity TEXT NOT NULL CHECK(severity IN ('error', 'warning')),
        config_json TEXT NOT NULL
    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS validation_results (
        id TEXT PRIMARY KEY,
        slip_id TEXT NOT NULL,
        rule_code TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pass', 'fail', 'warn')),
        message TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        FOREIGN KEY (slip_id) REFERENCES slips(id) ON DELETE CASCADE,
        FOREIGN KEY (rule_code) REFERENCES validation_rules(rule_code)
    )
    """)

    # Create performance indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_slips_ref ON slips(slip_reference)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_slips_vd_type ON slips(voting_district, ballot_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_slips_status ON slips(status)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_pages_slip ON slip_pages(slip_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_party_results_slip ON party_results(slip_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_slip ON audit_logs(slip_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_logs(timestamp)")

    # Seed Default Users
    now = datetime.now(timezone.utc).isoformat()
    seed_users = [
        ("usr_admin", "admin", "System Administrator", "admin", now),
        ("usr_supervisor", "supervisor", "Election Supervisor (Jane Smith)", "supervisor", now),
        ("usr_operator", "operator", "Data Capture Operator (John Doe)", "operator", now),
        ("usr_auditor", "auditor", "Independent Electoral Auditor", "auditor", now),
    ]
    cursor.executemany("""
    INSERT OR IGNORE INTO users (id, username, full_name, role, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, seed_users)

    # Seed Default Validation Rules
    default_rules = [
        (
            "rule_sum_party_votes",
            "SUM_PARTY_VOTES_MATCH",
            "Party Votes Sum Reconciliation",
            "Validates that the sum of votes for all individual candidates/parties strictly equals the Total Valid Votes Cast.",
            "math",
            1,
            "error",
            json.dumps({"tolerance": 0})
        ),
        (
            "rule_reconciliation",
            "RECONCILIATION_MATCH",
            "Total Votes Cast Reconciliation",
            "Validates that Total Valid Votes Cast + Total Spoilt Ballots strictly equals Total Votes Cast.",
            "math",
            1,
            "error",
            json.dumps({})
        ),
        (
            "rule_turnout_ceiling",
            "TURNOUT_CEILING",
            "Voter Turnout Ceiling Check",
            "Validates that Total Votes Cast does not exceed Registered Voters (flags error if >100%, warning if unusually high >90%).",
            "threshold",
            1,
            "error",
            json.dumps({"warning_threshold_pct": 90.0, "max_threshold_pct": 100.0})
        ),
        (
            "rule_all_pages_present",
            "ALL_PAGES_PRESENT",
            "Complete Multi-Page Set Requirement",
            "Enforces that all pages (Page X of Y) for a logical slip are uploaded, verified, and linked prior to approval.",
            "multi_page",
            1,
            "error",
            json.dumps({})
        ),
        (
            "rule_officer_signature",
            "OFFICER_SIGNATURE_PRESENT",
            "Presiding Officer Signature Verification",
            "Checks for the presence of the presiding officer's handwritten signature on the final page.",
            "compliance",
            1,
            "warning",
            json.dumps({"require_on_final_page": True})
        ),
        (
            "rule_duplicate_vd",
            "DUPLICATE_VD_BALLOT",
            "Duplicate Slip Protection",
            "Ensures no other approved ballot result slip exists with the same Voting District and Ballot Type.",
            "uniqueness",
            1,
            "error",
            json.dumps({})
        ),
        (
            "rule_party_signatures",
            "PARTY_SIGNATURE_CONSISTENCY",
            "Party Agent Signatures on Non-Zero Rows",
            "Recommends that party agent signatures are present on rows where party votes are recorded.",
            "compliance",
            1,
            "warning",
            json.dumps({})
        ),
    ]
    cursor.executemany("""
    INSERT OR IGNORE INTO validation_rules (id, rule_code, name, description, rule_type, is_active, severity, config_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, default_rules)

    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully at", DB_PATH)

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.database import get_db_connection

class AuditService:
    def __init__(self):
        pass

    def log_event(
        self,
        user_id: str,
        action: str,
        slip_id: Optional[str] = None,
        page_id: Optional[str] = None,
        field_name: Optional[str] = None,
        old_value: Optional[Any] = None,
        new_value: Optional[Any] = None,
        reason: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"

        old_val_str = str(old_value) if old_value is not None else None
        new_val_str = str(new_value) if new_value is not None else None

        cursor.execute("""
            INSERT INTO audit_logs (
                id, slip_id, page_id, user_id, action, field_name,
                old_value, new_value, reason, ip_address, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_id, slip_id, page_id, user_id, action, field_name,
            old_val_str, new_val_str, reason, ip_address, now
        ))

        conn.commit()
        conn.close()
        return audit_id

    def get_logs_for_slip(self, slip_id: str) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.username as user_name, u.role as user_role
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.slip_id = ?
            ORDER BY a.timestamp DESC
        """, (slip_id,))
        rows = cursor.fetchall()
        logs = [dict(r) for r in rows]
        conn.close()
        return logs

    def get_all_logs(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT a.*, u.username as user_name, u.role as user_role, s.slip_reference, s.ballot_type
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            LEFT JOIN slips s ON a.slip_id = s.id
            ORDER BY a.timestamp DESC
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        logs = [dict(r) for r in rows]
        conn.close()
        return logs

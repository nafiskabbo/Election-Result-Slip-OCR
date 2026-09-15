import json
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from backend.database import get_db_connection
from backend.models import ValidationRuleResponse, ValidationRuleUpdate
from backend.validation_engine import ValidationEngine
from backend.audit_service import AuditService
from backend.routes.auth import ACTIVE_USER_STATE

router = APIRouter(prefix="/api/rules", tags=["Validation Engine & Rule Builder"])

validation_engine = ValidationEngine()
audit_service = AuditService()

@router.get("", response_model=List[ValidationRuleResponse])
def get_all_rules():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM validation_rules ORDER BY rule_code ASC")
    rows = cursor.fetchall()
    rules = []
    for r in rows:
        d = dict(r)
        d["config_json"] = json.loads(d["config_json"]) if d["config_json"] else {}
        d["is_active"] = bool(d["is_active"])
        rules.append(ValidationRuleResponse(**d))
    conn.close()
    return rules

@router.patch("/{rule_code}")
def update_rule(rule_code: str, update: ValidationRuleUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM validation_rules WHERE rule_code = ?", (rule_code,))
    rule = cursor.fetchone()
    if not rule:
        conn.close()
        raise HTTPException(status_code=404, detail=f"Rule {rule_code} not found.")

    new_active = int(update.is_active) if update.is_active is not None else rule["is_active"]
    new_severity = update.severity if update.severity is not None else rule["severity"]
    new_config = json.dumps(update.config_json) if update.config_json is not None else rule["config_json"]

    cursor.execute("""
        UPDATE validation_rules SET
            is_active = ?,
            severity = ?,
            config_json = ?
        WHERE rule_code = ?
    """, (new_active, new_severity, new_config, rule_code))
    conn.commit()
    conn.close()

    current_user_id = ACTIVE_USER_STATE["id"]
    audit_service.log_event(
        user_id=current_user_id,
        action="update_validation_rule",
        field_name=rule_code,
        old_value=f"active={rule['is_active']}, severity={rule['severity']}",
        new_value=f"active={new_active}, severity={new_severity}",
        reason="Admin updated validation rule configuration"
    )

    return {"message": f"Rule {rule_code} updated successfully"}

@router.post("/evaluate/{slip_id}")
def evaluate_slip(slip_id: str):
    try:
        summary = validation_engine.evaluate_slip(slip_id)
        return summary
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

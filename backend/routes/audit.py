from typing import List
from fastapi import APIRouter, Query
from backend.models import AuditLogItem
from backend.audit_service import AuditService

router = APIRouter(prefix="/api/audit", tags=["Audit Trail & History"])

audit_service = AuditService()

@router.get("", response_model=List[AuditLogItem])
def get_audit_trail(limit: int = Query(100, ge=1, le=500), offset: int = Query(0, ge=0)):
    logs = audit_service.get_all_logs(limit=limit, offset=offset)
    return logs

@router.get("/slip/{slip_id}", response_model=List[AuditLogItem])
def get_slip_audit_trail(slip_id: str):
    logs = audit_service.get_logs_for_slip(slip_id)
    return logs

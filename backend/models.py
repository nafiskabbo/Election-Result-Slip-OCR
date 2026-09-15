from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from enum import Enum

class RoleEnum(str, Enum):
    ADMIN = "admin"
    SUPERVISOR = "supervisor"
    OPERATOR = "operator"
    AUDITOR = "auditor"

class SlipStatusEnum(str, Enum):
    INCOMPLETE = "incomplete"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"

class UserResponse(BaseModel):
    id: str
    username: str
    full_name: str
    role: RoleEnum
    created_at: str

class PartyResultItem(BaseModel):
    id: str
    slip_id: str
    page_id: str
    row_index: int
    party_name: str
    party_code: str
    votes: int
    confidence_score: float
    is_overridden: bool
    overridden_by: Optional[str] = None
    original_ocr_votes: int
    signature_detected: bool
    bbox_json: Optional[str] = None

class PartyResultUpdate(BaseModel):
    party_result_id: str
    votes: int
    reason: Optional[str] = None

class SlipPageResponse(BaseModel):
    id: str
    slip_id: str
    page_number: int
    page_total: int
    barcode_text: Optional[str] = None
    raw_file_path: str
    enhanced_file_path: str
    thumbnail_path: Optional[str] = None
    status: str
    upload_timestamp: str
    file_size: int
    mime_type: str
    exception_flags: Optional[str] = None

class ValidationResultItem(BaseModel):
    rule_code: str
    status: str  # 'pass', 'fail', 'warn'
    message: str
    evaluated_at: str

class SlipSummaryResponse(BaseModel):
    id: str
    slip_reference: str
    ballot_type: str
    election_name: str
    province: Optional[str] = None
    municipality: Optional[str] = None
    voting_district: str
    station_name: Optional[str] = None
    registered_voters: int
    status: SlipStatusEnum
    presiding_officer_name: Optional[str] = None
    presiding_officer_signature_detected: bool
    total_valid_votes: int
    total_spoilt_votes: int
    total_votes_cast: int
    special_votes: int
    section_24a_votes: int
    total_expected_pages: int
    total_received_pages: int
    created_at: str
    updated_at: str
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    rejection_reason: Optional[str] = None
    has_errors: bool = False
    has_warnings: bool = False

class SlipDetailResponse(SlipSummaryResponse):
    pages: List[SlipPageResponse] = []
    party_results: List[PartyResultItem] = []
    validation_results: List[ValidationResultItem] = []

class SlipFieldUpdate(BaseModel):
    field_name: str
    new_value: Any
    reason: Optional[str] = None

class SlipStatusAction(BaseModel):
    status: SlipStatusEnum
    reason: Optional[str] = None

class PageLinkRequest(BaseModel):
    page_id: str
    target_slip_id: str
    reason: str

class PageUnlinkRequest(BaseModel):
    page_id: str
    reason: str

class ValidationRuleResponse(BaseModel):
    id: str
    rule_code: str
    name: str
    description: str
    rule_type: str
    is_active: bool
    severity: str
    config_json: Dict[str, Any]

class ValidationRuleUpdate(BaseModel):
    is_active: Optional[bool] = None
    severity: Optional[str] = None
    config_json: Optional[Dict[str, Any]] = None

class AuditLogItem(BaseModel):
    id: str
    slip_id: Optional[str] = None
    page_id: Optional[str] = None
    user_id: str
    user_name: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    field_name: Optional[str] = None
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    reason: Optional[str] = None
    ip_address: Optional[str] = None
    timestamp: str

class UploadProcessResponse(BaseModel):
    processed_files: int
    created_slips: List[str]
    pages: List[SlipPageResponse]
    elapsed_seconds: float

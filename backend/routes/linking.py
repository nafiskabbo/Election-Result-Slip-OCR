from fastapi import APIRouter, HTTPException
from backend.models import PageLinkRequest, PageUnlinkRequest
from backend.grouping_engine import GroupingEngine
from backend.validation_engine import ValidationEngine
from backend.routes.auth import ACTIVE_USER_STATE

router = APIRouter(prefix="/api/linking", tags=["Multi-Page Linking & Exception Control"])

grouping_engine = GroupingEngine()
validation_engine = ValidationEngine()

@router.post("/link")
def link_page(req: PageLinkRequest):
    if not req.reason or len(req.reason.strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail="Mandatory Multi-Page Rule 3: A valid recorded reason is required to manually link a page."
        )

    current_user_id = ACTIVE_USER_STATE["id"]
    try:
        res = grouping_engine.manual_link_page(
            page_id=req.page_id,
            target_slip_id=req.target_slip_id,
            user_id=current_user_id,
            reason=req.reason
        )
        # Re-evaluate validation on target slip
        val_res = validation_engine.evaluate_slip(req.target_slip_id)
        res["target_validation"] = val_res
        return {"message": "Page linked successfully", "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/unlink")
def unlink_page(req: PageUnlinkRequest):
    if not req.reason or len(req.reason.strip()) < 5:
        raise HTTPException(
            status_code=400,
            detail="Mandatory Multi-Page Rule 3: A valid recorded reason is required to manually unlink a page."
        )

    current_user_id = ACTIVE_USER_STATE["id"]
    try:
        res = grouping_engine.manual_unlink_page(
            page_id=req.page_id,
            user_id=current_user_id,
            reason=req.reason
        )
        return {"message": "Page unlinked successfully into new slip record", "result": res}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

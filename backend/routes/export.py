from typing import Optional
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import Response
from backend.database import get_db_connection
from backend.export_service import ExportService
from backend.models import SlipStatusEnum

router = APIRouter(prefix="/api/export", tags=["Export & Reporting"])

export_service = ExportService()

@router.get("/json")
def export_all_json(status: Optional[str] = Query(None)):
    return export_service.export_slips_summary_json(status_filter=status)

@router.get("/csv")
def export_all_csv(status: Optional[str] = Query(None)):
    csv_content = export_service.export_slips_summary_csv(status_filter=status)
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ballot_slips_summary.csv"}
    )

@router.get("/slips/{slip_id}/csv")
def export_slip_csv(slip_id: str):
    try:
        csv_content = export_service.export_slip_detailed_csv(slip_id)
        return Response(
            content=csv_content,
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=slip_{slip_id}_results.csv"}
        )
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/slips/{slip_id}/json")
def export_slip_json(slip_id: str):
    try:
        data = export_service.export_slip_json(slip_id)
        return data
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/slips/{slip_id}/pdf")
def export_slip_pdf(slip_id: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT status, total_expected_pages, total_received_pages FROM slips WHERE id = ?", (slip_id,))
    slip = cursor.fetchone()
    conn.close()

    if not slip:
        raise HTTPException(status_code=404, detail=f"Slip {slip_id} not found.")

    # Rule 2 Enforcement: Block final export if slip is incomplete
    if slip["status"] == SlipStatusEnum.INCOMPLETE.value or slip["total_received_pages"] < slip["total_expected_pages"]:
        raise HTTPException(
            status_code=400,
            detail=f"EXPORT BLOCKED (Mandatory Multi-Page Rule 2): Cannot generate final certificate for an Incomplete result set ({slip['total_received_pages']}/{slip['total_expected_pages']} pages). Please upload all missing pages."
        )

    try:
        pdf_bytes = export_service.generate_slip_pdf(slip_id)
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f"inline; filename=slip_{slip_id}_certificate.pdf"}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating PDF: {str(e)}")

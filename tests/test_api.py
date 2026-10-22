import pytest
from fastapi.testclient import TestClient
from backend.main import app

pytestmark = pytest.mark.usefixtures("postgres_db")

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

def test_health_and_cors(client):
    res = client.get("/api/health", headers={"Origin": "https://result-desk.vercel.app"})
    assert res.status_code == 200
    assert res.json()["ok"] is True
    assert res.headers.get("access-control-allow-origin") == "*"

def test_upload_and_slips_api(client):
    with open("sample_slips/p_1.jpg", "rb") as f1, open("sample_slips/p_2.jpg", "rb") as f2, open("sample_slips/p_3.jpg", "rb") as f3:
        files = [
            ("files", ("p_1.jpg", f1, "image/jpeg")),
            ("files", ("p_2.jpg", f2, "image/jpeg")),
            ("files", ("p_3.jpg", f3, "image/jpeg")),
        ]
        res = client.post("/api/upload", files=files)
        assert res.status_code == 200
        data = res.json()
        assert data["processed_pages_count"] == 3
        assert len(data["affected_slips"]) == 1
        assert data["started_at"]
        assert data["ended_at"]
        assert data["total_elapsed_seconds"] >= 0
        slip_id = data["affected_slips"][0]

    # Get Slip Detail
    detail_res = client.get(f"/api/slips/{slip_id}")
    assert detail_res.status_code == 200
    slip_data = detail_res.json()
    assert slip_data["ballot_type"] == "National"
    assert slip_data["total_received_pages"] == 3
    assert slip_data["status"] in ("pending_review", "flagged")
    assert len(slip_data["party_results"]) > 0
    assert slip_data["processing_started_at"]
    assert slip_data["processing_ended_at"]

    # Manual Vote Override
    pr_id = slip_data["party_results"][0]["id"]
    patch_res = client.patch(f"/api/slips/{slip_id}/party", json={
        "party_result_id": pr_id,
        "votes": 5,
        "reason": "Test override"
    })
    assert patch_res.status_code == 200

    # Test Exports
    csv_res = client.get(f"/api/export/slips/{slip_id}/csv")
    assert csv_res.status_code == 200
    assert "text/csv" in csv_res.headers["content-type"]

    json_res = client.get(f"/api/export/slips/{slip_id}/json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]

    pdf_res = client.get(f"/api/export/slips/{slip_id}/pdf")
    assert pdf_res.status_code == 200
    assert "application/pdf" in pdf_res.headers["content-type"]

def test_incomplete_slip_approval_blocked_api(client):
    with open("sample_slips/p_1.jpg", "rb") as f1:
        files = [("files", ("p_1.jpg", f1, "image/jpeg"))]
        res = client.post("/api/upload", files=files)
        assert res.status_code == 200
        slip_id = res.json()["affected_slips"][0]

    # Attempt to approve incomplete slip -> Must be rejected with 400!
    approve_res = client.post(f"/api/slips/{slip_id}/approve")
    assert approve_res.status_code == 400
    assert "APPROVAL BLOCKED" in approve_res.json()["detail"]

    # Attempt to export PDF of incomplete slip -> Must also be blocked!
    pdf_res = client.get(f"/api/export/slips/{slip_id}/pdf")
    assert pdf_res.status_code == 400
    assert "EXPORT BLOCKED" in pdf_res.json()["detail"]


def test_upload_lg2026_final_templates_groups_three_slips(client):
    folder = "sample_slips/final_templates"
    names = [
        "WhatsApp Image 2026-10-16 at 13.06.01.jpeg",
        "WhatsApp Image 2026-10-16 at 13.06.01 (1).jpeg",
        "WhatsApp Image 2026-10-16 at 13.06.01 (2).jpeg",
        "WhatsApp Image 2026-10-16 at 13.06.01 (3).jpeg",
        "WhatsApp Image 2026-10-16 at 13.06.01 (4).jpeg",
        "WhatsApp Image 2026-10-16 at 13.06.01 (5).jpeg",
    ]
    handles = [open(f"{folder}/{name}", "rb") for name in names]
    try:
        files = [("files", (name, fh, "image/jpeg")) for name, fh in zip(names, handles)]
        res = client.post("/api/upload", files=files)
    finally:
        for fh in handles:
            fh.close()
    assert res.status_code == 200
    data = res.json()
    assert data["processed_pages_count"] == 6
    assert len(data["affected_slips"]) == 3

    by_type = {}
    for slip_id in data["affected_slips"]:
        slip = client.get(f"/api/slips/{slip_id}").json()
        by_type[slip["ballot_type"]] = slip
        assert slip["total_received_pages"] == 2
        assert slip["status"] in ("pending_review", "flagged")

    ward = by_type["Ward"]
    votes = {row["party_code"]: row["votes"] for row in ward["party_results"]}
    names_by_code = {row["party_code"]: row["party_name"] for row in ward["party_results"]}
    assert votes["TRAHB"] == 22
    assert votes["TRAFI"] == 160
    assert names_by_code["TRAFI"] == "MTOLO AYANDA JUNIOR"
    assert "PROSPECT" not in names_by_code["TRAFI"]
    assert "NDLOVU" not in names_by_code["TRAFI"]
    assert ward["total_valid_votes"] == 631
    assert ward["total_spoilt_votes"] == 100
    assert ward["total_votes_cast"] == 731

    local = by_type["Local Council PR"]
    local_votes = {row["party_code"]: row["votes"] for row in local["party_results"]}
    assert local_votes["AAN"] == 100
    assert local_votes["AFI"] == 60
    assert local_votes["AHB"] == 55

    district = by_type["District Council PR"]
    district_votes = {row["party_code"]: row["votes"] for row in district["party_results"]}
    assert district_votes["AAB"] == 250
    assert district_votes["AAE"] == 420
    assert district["total_valid_votes"] == 1335


def test_replace_and_remove_page_api(client, tmp_path):
    import cv2
    import numpy as np

    blank = tmp_path / "blank.jpg"
    cv2.imwrite(str(blank), np.full((320, 240, 3), 240, dtype=np.uint8))

    with open("sample_slips/p_1.jpg", "rb") as fh:
        res = client.post("/api/upload", files=[("files", ("p_1.jpg", fh, "image/jpeg"))])
    assert res.status_code == 200
    slip_id = res.json()["affected_slips"][0]
    page_id = res.json()["pages"][0]["page_id"]

    with open(blank, "rb") as fh:
        replace_res = client.post(
            f"/api/slips/{slip_id}/pages/{page_id}/replace",
            files=[("file", ("blank.jpg", fh, "image/jpeg"))],
        )
    assert replace_res.status_code == 200
    detail = client.get(f"/api/slips/{slip_id}").json()
    assert detail["is_vote_related"] is False
    assert detail["party_results"] == []

    delete_res = client.delete(f"/api/slips/{slip_id}/pages/{page_id}")
    assert delete_res.status_code == 200
    assert delete_res.json()["slip_deleted"] is True
    assert client.get(f"/api/slips/{slip_id}").status_code == 404

import os
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.database import init_db

@pytest.fixture(autouse=True)
def setup_test_api_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_api.db")
    monkeypatch.setenv("BALLOT_DB_PATH", test_db)
    import backend.database as db_module
    db_module.DB_PATH = test_db
    init_db()

@pytest.fixture
def client():
    return TestClient(app)

def test_upload_and_slips_api(client):
    # Upload Sample 2 and Sample 3 (Complete Regional Slip)
    with open("sample_slips/image2.jpg", "rb") as f2, open("sample_slips/image3.jpg", "rb") as f3:
        files = [
            ("files", ("image2.jpg", f2, "image/jpeg")),
            ("files", ("image3.jpg", f3, "image/jpeg"))
        ]
        res = client.post("/api/upload", files=files)
        assert res.status_code == 200
        data = res.json()
        assert data["processed_pages_count"] == 2
        assert len(data["affected_slips"]) == 1
        slip_id = data["affected_slips"][0]

    # Get Slip Detail
    detail_res = client.get(f"/api/slips/{slip_id}")
    assert detail_res.status_code == 200
    slip_data = detail_res.json()
    assert slip_data["ballot_type"] == "Regional"
    assert slip_data["total_received_pages"] == 2
    assert slip_data["status"] == "pending_review"
    assert len(slip_data["party_results"]) > 0

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
    # Upload only Sample 1 (Provincial Page 1 of 2 - Incomplete!)
    with open("sample_slips/image1.jpg", "rb") as f1:
        files = [("files", ("image1.jpg", f1, "image/jpeg"))]
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

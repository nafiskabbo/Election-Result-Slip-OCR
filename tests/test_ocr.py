import os
import cv2
import pytest
from backend.ocr_engine import OCREngine

@pytest.fixture
def ocr_engine():
    return OCREngine()

def test_sample_1_provincial_ocr(ocr_engine):
    img = cv2.imread("sample_slips/image1.jpg")
    data = ocr_engine.extract_full_slip_data(img)
    
    assert data["ballot_type"] == "Provincial"
    assert data["voting_district"] == "86820598"
    assert data["page_number"] == 1
    assert data["page_total"] == 2
    assert "001335868205982011" in data["barcode_text"]
    
    # Check party results
    votes_by_code = {p["party_code"]: p["votes"] for p in data["party_results"]}
    assert votes_by_code.get("ANC") == 19
    assert votes_by_code.get("DA") == 18
    assert votes_by_code.get("EFF") == 6
    assert votes_by_code.get("M.K.") == 1
    assert votes_by_code.get("ACTIONSA") == 18

def test_sample_2_regional_p1_ocr(ocr_engine):
    img = cv2.imread("sample_slips/image2.jpg")
    data = ocr_engine.extract_full_slip_data(img)
    
    assert data["ballot_type"] == "Regional"
    assert data["voting_district"] == "86820598"
    assert data["page_number"] == 1
    assert data["page_total"] == 2
    assert "001334868205983011" in data["barcode_text"]
    
    votes_by_code = {p["party_code"]: p["votes"] for p in data["party_results"]}
    assert votes_by_code.get("ANC") == 19
    assert votes_by_code.get("DA") == 15
    assert votes_by_code.get("EFF") == 5
    assert votes_by_code.get("ELF-SA") == 1
    assert votes_by_code.get("UAT") == 1

def test_sample_3_regional_p2_ocr(ocr_engine):
    img = cv2.imread("sample_slips/image3.jpg")
    data = ocr_engine.extract_full_slip_data(img)
    
    assert data["ballot_type"] == "Regional"
    assert data["voting_district"] == "86820598"
    assert data["page_number"] == 2
    assert data["page_total"] == 2
    assert "001334868205983021" in data["barcode_text"]
    
    votes_by_code = {p["party_code"]: p["votes"] for p in data["party_results"]}
    assert votes_by_code.get("VF PLUS") == 11
    
    # Totals block
    assert data["total_valid_votes"] == 52
    assert data["total_spoilt_votes"] == 0
    assert data["total_votes_cast"] == 52
    assert data["special_votes"] == 2
    assert data["presiding_officer_signature_detected"] is True

def test_sample_4_national_p3_ocr(ocr_engine):
    img = cv2.imread("sample_slips/image4.jpg")
    data = ocr_engine.extract_full_slip_data(img)
    
    assert data["ballot_type"] == "National"
    assert data["voting_district"] == "86820598"
    assert data["page_number"] == 3
    assert data["page_total"] == 3
    assert "001334868205981031" in data["barcode_text"]
    assert data["total_valid_votes"] == 52
    assert data["total_votes_cast"] == 52


def test_limpopo_national_does_not_use_britten_defaults(ocr_engine):
    img = cv2.imread("sample_slips/i_1.jpg")
    data = ocr_engine.extract_full_slip_data(img)

    assert data["ballot_type"] == "National"
    assert data["voting_district"] == "76240234"
    assert data["page_number"] == 1
    assert data["page_total"] == 3
    assert "001334762402341011" in data["barcode_text"]
    assert data["registered_voters"] == 1149
    assert "BRITTEN" not in (data["station_name"] or "")
    assert "BAKGAGA" in (data["station_name"] or "")
    votes_by_code = {p["party_code"]: p["votes"] for p in data["party_results"]}
    assert votes_by_code.get("ANC") == 481
    assert votes_by_code.get("EFF") == 77


def test_limpopo_national_final_totals(ocr_engine):
    img = cv2.imread("sample_slips/i_3.jpg")
    data = ocr_engine.extract_full_slip_data(img)
    assert data["page_number"] == 3
    assert data["page_total"] == 3
    assert data["total_valid_votes"] == 574
    assert data["total_spoilt_votes"] == 4
    assert data["total_votes_cast"] == 578
    assert data["special_votes"] == 25


def test_limpopo_regional_reads_three_page_set(ocr_engine):
    img = cv2.imread("sample_slips/i_4.jpg")
    data = ocr_engine.extract_full_slip_data(img)
    assert data["ballot_type"] == "Regional"
    assert data["page_number"] == 1
    assert data["page_total"] == 3
    votes_by_code = {p["party_code"]: p["votes"] for p in data["party_results"]}
    assert votes_by_code.get("ANC") == 462
    assert votes_by_code.get("EFF") == 97

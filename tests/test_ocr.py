import cv2
import pytest
from backend.image_enhancer import ImageEnhancer
from backend.ocr_engine import OCREngine, LOW_VOTE_CONFIDENCE

@pytest.fixture
def ocr_engine():
    return OCREngine()

@pytest.fixture
def enhancer():
    return ImageEnhancer()

def _extract(ocr_engine, enhancer, path):
    img = cv2.imread(path)
    assert img is not None
    enh = enhancer.process_image(img)
    return ocr_engine.extract_full_slip_data(enh.enhanced_image, binary=enh.binary_image)

def test_limpopo_national_page_1(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_1.jpg")

    assert data["ballot_type"] == "National"
    assert data["voting_district"] == "76240234"
    assert data["page_number"] == 1
    assert data["page_total"] == 3
    assert "001334762402341011" in data["barcode_text"]
    assert data["registered_voters"] == 1149
    assert "BRITTEN" not in (data["station_name"] or "")
    assert "BAKGAGA" in (data["station_name"] or "")
    assert all(p["confidence_score"] <= 0.92 for p in data["party_results"])


def test_limpopo_national_page_2(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_2.jpg")
    assert data["ballot_type"] == "National"
    assert data["page_number"] == 2
    assert data["page_total"] == 3
    assert "001334762402341021" in data["barcode_text"]


def test_limpopo_national_final_page_identity(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_3.jpg")
    assert data["page_number"] == 3
    assert data["page_total"] == 3
    assert "001334762402341031" in (data["barcode_text"] or "")


def test_limpopo_regional_page_1(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_4.jpg")
    assert data["ballot_type"] == "Regional"
    assert data["page_number"] == 1
    assert data["page_total"] == 3


def test_limpopo_provincial_page_1_identity(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_7.jpg")
    assert data["ballot_type"] == "Provincial"
    assert data["voting_district"] == "76240234"
    assert data["page_number"] == 1
    assert "001335762402342011" in (data["barcode_text"] or "")


def test_lookup_does_not_inflate_confidence(ocr_engine, enhancer):
    data = _extract(ocr_engine, enhancer, "sample_slips/p_1.jpg")
    scores = [p["confidence_score"] for p in data["party_results"]]
    assert scores
    assert max(scores) <= 0.92
    assert 0.96 not in scores
    assert 0.99 not in scores
    assert any(s < LOW_VOTE_CONFIDENCE for s in scores) or any(data.get("exception_flags") or [])

import os
import cv2
import pytest
from backend.database import init_db, get_db_connection
from backend.ocr_engine import OCREngine
from backend.grouping_engine import GroupingEngine
from backend.validation_engine import ValidationEngine

@pytest.fixture(autouse=True)
def setup_test_db(tmp_path, monkeypatch):
    test_db = str(tmp_path / "test_ballot.db")
    monkeypatch.setenv("BALLOT_DB_PATH", test_db)
    import backend.database as db_module
    db_module.DB_PATH = test_db
    init_db()

@pytest.fixture
def engines():
    return OCREngine(), GroupingEngine(), ValidationEngine()

def test_rule_1_and_rule_4_grouping_and_consolidation(engines):
    ocr, grouping, validator = engines
    
    # Process Sample 2 (Regional Page 1 of 2)
    img2 = cv2.imread("sample_slips/image2.jpg")
    data2 = ocr.extract_full_slip_data(img2)
    slip_id_2, page_id_2, sum_2 = grouping.process_extracted_page(
        extracted_data=data2,
        raw_file_path="sample_slips/image2.jpg",
        enhanced_file_path="storage/enhanced/test_enh_2.jpg",
        thumb_path="storage/thumbnails/test_thumb_2.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    
    # At this point, only Page 1 is uploaded -> Rule 2: Result set must be Incomplete!
    assert sum_2["is_complete"] is False
    assert sum_2["status"] == "incomplete"
    assert sum_2["missing_pages"] == [2]
    
    # Process Sample 3 (Regional Page 2 of 2)
    img3 = cv2.imread("sample_slips/image3.jpg")
    data3 = ocr.extract_full_slip_data(img3)
    slip_id_3, page_id_3, sum_3 = grouping.process_extracted_page(
        extracted_data=data3,
        raw_file_path="sample_slips/image3.jpg",
        enhanced_file_path="storage/enhanced/test_enh_3.jpg",
        thumb_path="storage/thumbnails/test_thumb_3.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    
    # Rule 1 Verification: Sample 2 and 3 must group into the EXACT same slip ID!
    assert slip_id_2 == slip_id_3, "Rule 1 Failed: Pages 1 and 2 must form ONE logical slip record!"
    
    # Rule 2 Verification: With both pages present, set is now Complete!
    assert sum_3["is_complete"] is True
    assert sum_3["status"] == "pending_review"
    assert len(sum_3["missing_pages"]) == 0
    
    # Rule 4 Verification: Consolidation without double-counting
    # Sum of Page 1 (19+15+5+1+1 = 41) + Page 2 (11) = 52!
    assert sum_3["sum_party_votes"] == 52, f"Rule 4 Failed: Expected 52 votes, got {sum_3['sum_party_votes']}"

def test_rule_2_incomplete_set_blocking(engines):
    ocr, grouping, validator = engines
    
    # Sample 4 (National Page 3 of 3)
    img4 = cv2.imread("sample_slips/image4.jpg")
    data4 = ocr.extract_full_slip_data(img4)
    slip_id, _, summary = grouping.process_extracted_page(
        extracted_data=data4,
        raw_file_path="sample_slips/image4.jpg",
        enhanced_file_path="storage/enhanced/test_enh_4.jpg",
        thumb_path="storage/thumbnails/test_thumb_4.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    
    # Rule 2 Verification: Pages 1 and 2 are missing
    assert summary["is_complete"] is False
    assert summary["status"] == "incomplete"
    assert summary["missing_pages"] == [1, 2]
    
    # Validation evaluation must flag failure for incomplete page set
    val_res = validator.evaluate_slip(slip_id)
    assert val_res["is_eligible_for_approval"] is False
    
    rule_results = {r["rule_code"]: r["status"] for r in val_res["validation_results"]}
    assert rule_results.get("ALL_PAGES_PRESENT") == "fail"

def test_rule_3_manual_link_and_unlink(engines):
    ocr, grouping, validator = engines
    
    # Upload Sample 1 (Provincial p1)
    img1 = cv2.imread("sample_slips/image1.jpg")
    data1 = ocr.extract_full_slip_data(img1)
    slip_id_1, page_id_1, _ = grouping.process_extracted_page(
        extracted_data=data1,
        raw_file_path="sample_slips/image1.jpg",
        enhanced_file_path="storage/enhanced/test_enh_1.jpg",
        thumb_path="storage/thumbnails/test_thumb_1.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    
    # Upload Sample 2 (Regional p1)
    img2 = cv2.imread("sample_slips/image2.jpg")
    data2 = ocr.extract_full_slip_data(img2)
    slip_id_2, page_id_2, _ = grouping.process_extracted_page(
        extracted_data=data2,
        raw_file_path="sample_slips/image2.jpg",
        enhanced_file_path="storage/enhanced/test_enh_2.jpg",
        thumb_path="storage/thumbnails/test_thumb_2.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    
    # Test manual unlink
    unlink_res = grouping.manual_unlink_page(
        page_id=page_id_1,
        user_id="usr_supervisor",
        reason="Splitting into standalone audit inspection slip"
    )
    assert unlink_res is not None
    
    # Test manual link
    link_res = grouping.manual_link_page(
        page_id=page_id_1,
        target_slip_id=slip_id_2,
        user_id="usr_supervisor",
        reason="Supervisor manual attachment of misfiled page"
    )
    assert link_res is not None

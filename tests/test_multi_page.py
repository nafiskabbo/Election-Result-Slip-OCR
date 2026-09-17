import cv2
import pytest
from backend.ocr_engine import OCREngine
from backend.grouping_engine import GroupingEngine
from backend.validation_engine import ValidationEngine

pytestmark = pytest.mark.usefixtures("postgres_db")

@pytest.fixture
def engines():
    return OCREngine(), GroupingEngine(), ValidationEngine()

def test_rule_1_and_rule_4_grouping_and_consolidation(engines):
    ocr, grouping, validator = engines

    img1 = cv2.imread("sample_slips/p_1.jpg")
    data1 = ocr.extract_full_slip_data(img1)
    slip_id_1, _, sum_1 = grouping.process_extracted_page(
        extracted_data=data1,
        raw_file_path="sample_slips/p_1.jpg",
        enhanced_file_path="storage/enhanced/test_enh_1.jpg",
        thumb_path="storage/thumbnails/test_thumb_1.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    assert sum_1["is_complete"] is False
    assert sum_1["status"] == "incomplete"
    assert sum_1["missing_pages"] == [2, 3]

    img2 = cv2.imread("sample_slips/p_2.jpg")
    data2 = ocr.extract_full_slip_data(img2)
    slip_id_2, _, sum_2 = grouping.process_extracted_page(
        extracted_data=data2,
        raw_file_path="sample_slips/p_2.jpg",
        enhanced_file_path="storage/enhanced/test_enh_2.jpg",
        thumb_path="storage/thumbnails/test_thumb_2.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    assert slip_id_1 == slip_id_2
    assert sum_2["is_complete"] is False
    assert 3 in sum_2["missing_pages"]

    img3 = cv2.imread("sample_slips/p_3.jpg")
    data3 = ocr.extract_full_slip_data(img3)
    slip_id_3, _, sum_3 = grouping.process_extracted_page(
        extracted_data=data3,
        raw_file_path="sample_slips/p_3.jpg",
        enhanced_file_path="storage/enhanced/test_enh_3.jpg",
        thumb_path="storage/thumbnails/test_thumb_3.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )
    assert slip_id_1 == slip_id_3
    assert sum_3["is_complete"] is True
    assert sum_3["status"] in ("pending_review", "flagged")
    assert len(sum_3["missing_pages"]) == 0

def test_rule_2_incomplete_set_blocking(engines):
    ocr, grouping, validator = engines

    img3 = cv2.imread("sample_slips/p_3.jpg")
    data3 = ocr.extract_full_slip_data(img3)
    slip_id, _, summary = grouping.process_extracted_page(
        extracted_data=data3,
        raw_file_path="sample_slips/p_3.jpg",
        enhanced_file_path="storage/enhanced/test_enh_3.jpg",
        thumb_path="storage/thumbnails/test_thumb_3.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )

    assert summary["is_complete"] is False
    assert summary["status"] == "incomplete"
    assert summary["missing_pages"] == [1, 2]

    val_res = validator.evaluate_slip(slip_id)
    assert val_res["is_eligible_for_approval"] is False

    rule_results = {r["rule_code"]: r["status"] for r in val_res["validation_results"]}
    assert rule_results.get("ALL_PAGES_PRESENT") == "fail"

def test_rule_3_manual_link_and_unlink(engines):
    ocr, grouping, validator = engines

    img1 = cv2.imread("sample_slips/p_1.jpg")
    data1 = ocr.extract_full_slip_data(img1)
    slip_id_1, page_id_1, _ = grouping.process_extracted_page(
        extracted_data=data1,
        raw_file_path="sample_slips/p_1.jpg",
        enhanced_file_path="storage/enhanced/test_enh_1.jpg",
        thumb_path="storage/thumbnails/test_thumb_1.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )

    img4 = cv2.imread("sample_slips/p_4.jpg")
    data4 = ocr.extract_full_slip_data(img4)
    slip_id_4, page_id_4, _ = grouping.process_extracted_page(
        extracted_data=data4,
        raw_file_path="sample_slips/p_4.jpg",
        enhanced_file_path="storage/enhanced/test_enh_4.jpg",
        thumb_path="storage/thumbnails/test_thumb_4.jpg",
        file_size=1000,
        mime_type="image/jpeg"
    )

    unlink_res = grouping.manual_unlink_page(
        page_id=page_id_1,
        user_id="usr_supervisor",
        reason="Splitting into standalone audit inspection slip"
    )
    assert unlink_res is not None

    link_res = grouping.manual_link_page(
        page_id=page_id_1,
        target_slip_id=slip_id_4,
        user_id="usr_supervisor",
        reason="Supervisor manual attachment of misfiled page"
    )
    assert link_res is not None


def _sample_extracted(**overrides):
    data = {
        "slip_reference": "001335970900502",
        "voting_district": "97090050",
        "ballot_type": "Provincial",
        "page_number": 1,
        "page_total": 2,
        "barcode_text": "001335970900502011",
        "election_name": "2024 PROVINCIAL ELECTION",
        "province": "Gauteng",
        "municipality": None,
        "station_name": "Test Station",
        "registered_voters": 100,
        "presiding_officer_name": None,
        "presiding_officer_signature_detected": False,
        "total_valid_votes": 0,
        "total_spoilt_votes": 0,
        "total_votes_cast": 0,
        "special_votes": 0,
        "section_24a_votes": 0,
        "party_results": [{
            "row_index": 0,
            "party_name": "AFRICAN NATIONAL CONGRESS",
            "party_code": "ANC",
            "votes": 9,
            "confidence_score": 0.9,
            "original_ocr_votes": 9,
            "signature_detected": False,
            "bbox": {},
        }],
        "exception_flags": [],
        "is_vote_related": True,
    }
    data.update(overrides)
    return data


def test_duplicate_page_creates_numbered_copy(engines):
    from backend.database import get_db_connection

    _, grouping, _ = engines
    first_id, _, _ = grouping.process_extracted_page(
        extracted_data=_sample_extracted(),
        raw_file_path="sample_slips/p_1.jpg",
        enhanced_file_path="storage/enhanced/dup_1.jpg",
        thumb_path="storage/thumbnails/dup_1.jpg",
        file_size=1000,
        mime_type="image/jpeg",
    )
    second_id, _, _ = grouping.process_extracted_page(
        extracted_data=_sample_extracted(),
        raw_file_path="sample_slips/p_1.jpg",
        enhanced_file_path="storage/enhanced/dup_2.jpg",
        thumb_path="storage/thumbnails/dup_2.jpg",
        file_size=1000,
        mime_type="image/jpeg",
    )
    assert first_id != second_id

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT slip_reference FROM slips WHERE id = ?", (first_id,))
    first_ref = cursor.fetchone()["slip_reference"]
    cursor.execute("SELECT slip_reference FROM slips WHERE id = ?", (second_id,))
    second_ref = cursor.fetchone()["slip_reference"]
    conn.close()
    assert first_ref == "001335970900502"
    assert second_ref == "001335970900502 (2)"

    page2_id, _, summary = grouping.process_extracted_page(
        extracted_data=_sample_extracted(page_number=2, barcode_text="001335970900502021"),
        raw_file_path="sample_slips/p_2.jpg",
        enhanced_file_path="storage/enhanced/dup_p2.jpg",
        thumb_path="storage/thumbnails/dup_p2.jpg",
        file_size=1000,
        mime_type="image/jpeg",
    )
    assert page2_id == second_id
    assert 2 in summary["received_pages"]


def test_non_vote_pages_stay_separate(engines):
    from backend.database import get_db_connection

    _, grouping, _ = engines
    unread = dict(
        _sample_extracted(
            is_vote_related=False,
            slip_reference="UNREAD_AAAA",
            voting_district="UNKNOWN",
            ballot_type="Unknown",
            party_results=[],
            page_total=1,
            exception_flags=["not_a_result_slip"],
        )
    )
    first_id, _, _ = grouping.process_extracted_page(
        extracted_data=dict(unread),
        raw_file_path="a.jpg",
        enhanced_file_path="storage/enhanced/a.jpg",
        thumb_path="storage/thumbnails/a.jpg",
        file_size=10,
        mime_type="image/jpeg",
    )
    second_id, _, _ = grouping.process_extracted_page(
        extracted_data=dict(unread),
        raw_file_path="b.jpg",
        enhanced_file_path="storage/enhanced/b.jpg",
        thumb_path="storage/thumbnails/b.jpg",
        file_size=10,
        mime_type="image/jpeg",
    )
    assert first_id != second_id
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT is_vote_related FROM slips WHERE id = ?", (first_id,))
    assert cursor.fetchone()["is_vote_related"] is False
    conn.close()

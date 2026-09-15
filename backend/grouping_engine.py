import sqlite3
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from backend.database import get_db_connection
from backend.models import SlipStatusEnum

class GroupingEngine:
    def __init__(self):
        pass

    def process_extracted_page(
        self,
        extracted_data: Dict[str, Any],
        raw_file_path: str,
        enhanced_file_path: str,
        thumb_path: str,
        file_size: int,
        mime_type: str,
        user_id: str = "usr_operator"
    ) -> Tuple[str, str, Dict[str, Any]]:
        """
        Processes a newly uploaded and enhanced page:
        Applies Rule 1 (Identify & Group), Rule 2 (Complete Set requirement),
        Rule 3 (Exception Control), and Rule 4 (Consolidation).
        Returns: (slip_id, page_id, processing_summary)
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        slip_ref = extracted_data["slip_reference"]
        vd = extracted_data["voting_district"]
        ballot_type = extracted_data["ballot_type"]
        page_num = extracted_data["page_number"]
        page_total = extracted_data["page_total"]
        barcode_text = extracted_data["barcode_text"]

        # Rule 1: Find if an existing slip record exists for this logical slip
        cursor.execute("""
            SELECT * FROM slips 
            WHERE slip_reference = ? OR (voting_district = ? AND ballot_type = ?)
        """, (slip_ref, vd, ballot_type))
        existing_slip = cursor.fetchone()

        exception_flags = []
        page_id = f"page_{uuid.uuid4().hex[:12]}"

        if existing_slip:
            slip_id = existing_slip["id"]
            # Check for duplicate page (Rule 3)
            cursor.execute("""
                SELECT id FROM slip_pages 
                WHERE slip_id = ? AND page_number = ?
            """, (slip_id, page_num))
            dup_page = cursor.fetchone()
            if dup_page:
                exception_flags.append(f"DUPLICATE_PAGE: Page {page_num} already exists for this slip.")

            # Check for conflicting metadata (Rule 3)
            if existing_slip["voting_district"] != vd:
                exception_flags.append(f"MISMATCHED_VD: Existing VD {existing_slip['voting_district']} != incoming VD {vd}.")
            if existing_slip["ballot_type"] != ballot_type:
                exception_flags.append(f"MISMATCHED_BALLOT_TYPE: Existing {existing_slip['ballot_type']} != incoming {ballot_type}.")

        else:
            slip_id = f"slip_{uuid.uuid4().hex[:12]}"
            # Create new slip record
            cursor.execute("""
                INSERT INTO slips (
                    id, slip_reference, ballot_type, election_name, province, municipality,
                    voting_district, station_name, registered_voters, status,
                    presiding_officer_name, presiding_officer_signature_detected,
                    total_valid_votes, total_spoilt_votes, total_votes_cast,
                    special_votes, section_24a_votes, total_expected_pages, total_received_pages,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                slip_id, slip_ref, ballot_type, extracted_data["election_name"],
                extracted_data["province"], extracted_data["municipality"],
                vd, extracted_data["station_name"], extracted_data["registered_voters"],
                SlipStatusEnum.INCOMPLETE.value,
                extracted_data.get("presiding_officer_name"),
                1 if extracted_data.get("presiding_officer_signature_detected") else 0,
                extracted_data.get("total_valid_votes", 0),
                extracted_data.get("total_spoilt_votes", 0),
                extracted_data.get("total_votes_cast", 0),
                extracted_data.get("special_votes", 0),
                extracted_data.get("section_24a_votes", 0),
                page_total, 0, now, now
            ))

        # Insert the page record
        flag_str = json.dumps(exception_flags) if exception_flags else None
        cursor.execute("""
            INSERT INTO slip_pages (
                id, slip_id, page_number, page_total, barcode_text,
                raw_file_path, enhanced_file_path, thumbnail_path,
                status, upload_timestamp, file_size, mime_type, exception_flags
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            page_id, slip_id, page_num, page_total, barcode_text,
            raw_file_path, enhanced_file_path, thumb_path,
            "exception" if exception_flags else "valid",
            now, file_size, mime_type, flag_str
        ))

        # Insert party results for this page
        for pr in extracted_data["party_results"]:
            pr_id = f"pr_{uuid.uuid4().hex[:12]}"
            cursor.execute("""
                INSERT INTO party_results (
                    id, slip_id, page_id, row_index, party_name, party_code,
                    votes, confidence_score, is_overridden, overridden_by,
                    original_ocr_votes, signature_detected, bbox_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pr_id, slip_id, page_id, pr["row_index"], pr["party_name"], pr["party_code"],
                pr["votes"], pr["confidence_score"], 0, None,
                pr["original_ocr_votes"], 1 if pr["signature_detected"] else 0,
                json.dumps(pr.get("bbox", {}))
            ))

        # Audit log for upload & extraction
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO audit_logs (
                id, slip_id, page_id, user_id, action, field_name,
                old_value, new_value, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_id, slip_id, page_id, user_id, "upload_and_extract",
            "page_upload", None, f"Page {page_num} of {page_total} (Barcode: {barcode_text})",
            f"Automated extraction. Exception flags: {exception_flags}", now
        ))

        conn.commit()

        # Consolidate and update completeness (Rules 2 & 4)
        summary = self.consolidate_slip(slip_id, conn)

        conn.close()
        return slip_id, page_id, summary

    def consolidate_slip(self, slip_id: str, conn: Optional[sqlite3.Connection] = None) -> Dict[str, Any]:
        """
        Rule 2: Require Complete Set (keep Incomplete, block approval if pages missing)
        Rule 4: Consolidate once, aggregate rows and totals without double counting.
        """
        should_close = False
        if conn is None:
            conn = get_db_connection()
            should_close = True

        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        # Get all pages for this slip
        cursor.execute("""
            SELECT * FROM slip_pages WHERE slip_id = ? ORDER BY page_number ASC
        """, (slip_id,))
        pages = cursor.fetchall()

        cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
        slip = cursor.fetchone()
        if not slip:
            if should_close: conn.close()
            return {}

        expected_total = slip["total_expected_pages"]
        received_page_nums = sorted(list(set([p["page_number"] for p in pages])))
        received_count = len(received_page_nums)

        # Check completeness (Rule 2)
        is_complete = True
        missing_pages = []
        for p in range(1, expected_total + 1):
            if p not in received_page_nums:
                is_complete = False
                missing_pages.append(p)

        # Calculate party aggregates without double counting (Rule 4)
        # If multiple copies of the same page exist, take the latest uploaded page's rows
        cursor.execute("""
            SELECT pr.party_code, pr.party_name, pr.votes, pr.confidence_score, pr.signature_detected,
                   p.page_number
            FROM party_results pr
            JOIN slip_pages p ON pr.page_id = p.id
            WHERE pr.slip_id = ?
            ORDER BY p.page_number ASC, pr.row_index ASC
        """, (slip_id,))
        rows = cursor.fetchall()

        # Aggregate party votes across distinct pages
        consolidated_parties = {}
        for r in rows:
            code = r["party_code"]
            # Deduplicate by party code (each party should only appear once in a ballot)
            if code not in consolidated_parties:
                consolidated_parties[code] = {
                    "party_name": r["party_name"],
                    "votes": r["votes"],
                    "confidence": r["confidence_score"],
                    "signature": bool(r["signature_detected"])
                }
            else:
                consolidated_parties[code]["votes"] += r["votes"]

        sum_party_votes = sum(p["votes"] for p in consolidated_parties.values())

        # Pull totals from final page if present
        cursor.execute("""
            SELECT p.id FROM slip_pages p 
            WHERE p.slip_id = ? AND p.page_number = ?
        """, (slip_id, expected_total))
        final_page = cursor.fetchone()

        # Determine status
        has_exceptions = False
        for p in pages:
            if p["exception_flags"]:
                has_exceptions = True
                break

        if not is_complete:
            new_status = SlipStatusEnum.INCOMPLETE.value
        elif has_exceptions:
            new_status = SlipStatusEnum.FLAGGED.value
        else:
            # If was already approved, retain approved; otherwise pending_review
            if slip["status"] == SlipStatusEnum.APPROVED.value:
                new_status = SlipStatusEnum.APPROVED.value
            else:
                new_status = SlipStatusEnum.PENDING_REVIEW.value

        # Update slip totals and status
        cursor.execute("""
            UPDATE slips SET
                total_received_pages = ?,
                status = ?,
                updated_at = ?
            WHERE id = ?
        """, (received_count, new_status, now, slip_id))

        conn.commit()

        summary = {
            "slip_id": slip_id,
            "is_complete": is_complete,
            "expected_pages": expected_total,
            "received_pages": received_page_nums,
            "missing_pages": missing_pages,
            "status": new_status,
            "total_party_count": len(consolidated_parties),
            "sum_party_votes": sum_party_votes
        }

        if should_close:
            conn.close()

        return summary

    def manual_link_page(
        self,
        page_id: str,
        target_slip_id: str,
        user_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Rule 3: Manual linking requires an authorized user, a recorded reason, and an immutable audit entry.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("SELECT * FROM slip_pages WHERE id = ?", (page_id,))
        page = cursor.fetchone()
        if not page:
            conn.close()
            raise ValueError(f"Page {page_id} not found.")

        old_slip_id = page["slip_id"]

        # Update page slip_id
        cursor.execute("UPDATE slip_pages SET slip_id = ? WHERE id = ?", (target_slip_id, page_id))
        cursor.execute("UPDATE party_results SET slip_id = ? WHERE page_id = ?", (target_slip_id, page_id))

        # Log audit entry
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO audit_logs (
                id, slip_id, page_id, user_id, action, field_name,
                old_value, new_value, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_id, target_slip_id, page_id, user_id, "manual_link_page",
            "slip_id", old_slip_id, target_slip_id, reason, now
        ))

        conn.commit()

        # Re-consolidate both old and target slips
        summary_old = self.consolidate_slip(old_slip_id, conn)
        summary_new = self.consolidate_slip(target_slip_id, conn)

        conn.close()
        return {
            "old_slip_summary": summary_old,
            "target_slip_summary": summary_new
        }

    def manual_unlink_page(
        self,
        page_id: str,
        user_id: str,
        reason: str
    ) -> Dict[str, Any]:
        """
        Rule 3: Manual unlinking page into a new standalone slip record with audit tracking.
        """
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("SELECT * FROM slip_pages WHERE id = ?", (page_id,))
        page = cursor.fetchone()
        if not page:
            conn.close()
            raise ValueError(f"Page {page_id} not found.")

        old_slip_id = page["slip_id"]
        cursor.execute("SELECT * FROM slips WHERE id = ?", (old_slip_id,))
        old_slip = cursor.fetchone()

        new_slip_id = f"slip_{uuid.uuid4().hex[:12]}"
        new_slip_ref = f"{old_slip['slip_reference']}_unlinked_{uuid.uuid4().hex[:4]}"

        # Create new standalone slip
        cursor.execute("""
            INSERT INTO slips (
                id, slip_reference, ballot_type, election_name, province, municipality,
                voting_district, station_name, registered_voters, status,
                presiding_officer_name, total_valid_votes, total_spoilt_votes, total_votes_cast,
                special_votes, section_24a_votes, total_expected_pages, total_received_pages,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            new_slip_id, new_slip_ref, old_slip["ballot_type"], old_slip["election_name"],
            old_slip["province"], old_slip["municipality"], old_slip["voting_district"],
            old_slip["station_name"], old_slip["registered_voters"],
            SlipStatusEnum.INCOMPLETE.value, old_slip["presiding_officer_name"],
            0, 0, 0, 0, 0, page["page_total"], 1, now, now
        ))

        # Reassign page and party results
        cursor.execute("UPDATE slip_pages SET slip_id = ? WHERE id = ?", (new_slip_id, page_id))
        cursor.execute("UPDATE party_results SET slip_id = ? WHERE page_id = ?", (new_slip_id, page_id))

        # Audit log
        audit_id = f"aud_{uuid.uuid4().hex[:12]}"
        cursor.execute("""
            INSERT INTO audit_logs (
                id, slip_id, page_id, user_id, action, field_name,
                old_value, new_value, reason, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            audit_id, new_slip_id, page_id, user_id, "manual_unlink_page",
            "slip_id", old_slip_id, new_slip_id, reason, now
        ))

        conn.commit()

        summary_old = self.consolidate_slip(old_slip_id, conn)
        summary_new = self.consolidate_slip(new_slip_id, conn)

        conn.close()
        return {
            "old_slip_summary": summary_old,
            "new_slip_summary": summary_new
        }

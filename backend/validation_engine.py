import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from backend.database import get_db_connection, parse_config_json

class ValidationEngine:
    def __init__(self):
        pass

    def evaluate_slip(self, slip_id: str) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()
        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
        slip = cursor.fetchone()
        if not slip:
            conn.close()
            raise ValueError(f"Slip {slip_id} not found.")

        # Fetch active rules
        cursor.execute("SELECT * FROM validation_rules WHERE is_active")
        active_rules = cursor.fetchall()

        # Fetch pages
        cursor.execute("SELECT * FROM slip_pages WHERE slip_id = ? ORDER BY page_number ASC", (slip_id,))
        pages = cursor.fetchall()

        # Fetch party results
        cursor.execute("""
            SELECT party_code, party_name, votes, signature_detected 
            FROM party_results 
            WHERE slip_id = ?
        """, (slip_id,))
        party_rows = cursor.fetchall()

        # Delete previous validation results for this slip
        cursor.execute("DELETE FROM validation_results WHERE slip_id = ?", (slip_id,))

        eval_results = []
        has_critical_error = False
        has_warning = False

        # Pre-compute metrics
        sum_party_votes = sum(r["votes"] for r in party_rows)
        total_valid = slip["total_valid_votes"]
        total_spoilt = slip["total_spoilt_votes"]
        total_cast = slip["total_votes_cast"]
        reg_voters = max(1, slip["registered_voters"])
        expected_pages = slip["total_expected_pages"]
        received_page_nums = sorted(list(set([p["page_number"] for p in pages])))

        for rule in active_rules:
            code = rule["rule_code"]
            name = rule["name"]
            severity = rule["severity"]
            config = parse_config_json(rule["config_json"])

            status = "pass"
            message = f"{name}: Validation passed."

            # 1. Sum Party Votes Check
            if code == "SUM_PARTY_VOTES_MATCH":
                # Only strictly check if final totals are present (or if slip has expected pages)
                if expected_pages in received_page_nums and total_valid > 0:
                    diff = abs(sum_party_votes - total_valid)
                    tol = config.get("tolerance", 0)
                    if diff > tol:
                        status = "fail" if severity == "error" else "warn"
                        message = f"Party votes sum ({sum_party_votes}) does not equal Total Valid Votes Cast ({total_valid}). Difference = {diff}."
                    else:
                        message = f"Party votes sum ({sum_party_votes}) matches Total Valid Votes Cast ({total_valid})."
                else:
                    if len(received_page_nums) < expected_pages:
                        status = "warn"
                        message = f"Cannot verify party sum totals until final page {expected_pages} with summary block is uploaded."
                    else:
                        message = "Party votes sum verified."

            # 2. Total Votes Reconciliation
            elif code == "RECONCILIATION_MATCH":
                if expected_pages in received_page_nums and (total_valid > 0 or total_cast > 0):
                    if (total_valid + total_spoilt) != total_cast:
                        status = "fail" if severity == "error" else "warn"
                        message = f"Reconciliation error: Total Valid ({total_valid}) + Spoilt ({total_spoilt}) = {total_valid + total_spoilt}, which does not match Total Votes Cast ({total_cast})."
                    else:
                        message = f"Reconciliation verified: Valid ({total_valid}) + Spoilt ({total_spoilt}) == Total Cast ({total_cast})."
                else:
                    message = "Reconciliation check pending final page totals."

            # 3. Voter Turnout Ceiling — votes cast and party totals vs registered
            elif code == "TURNOUT_CEILING":
                max_pct = config.get("max_threshold_pct", 100.0)
                warn_pct = config.get("warning_threshold_pct", 90.0)
                ceiling = reg_voters

                if sum_party_votes > ceiling:
                    status = "fail"
                    message = (
                        f"Party vote sum ({sum_party_votes}) exceeds registered voters "
                        f"({reg_voters})."
                    )
                elif total_cast > 0:
                    turnout_pct = (total_cast / float(reg_voters)) * 100.0
                    if turnout_pct > max_pct or total_cast > ceiling:
                        status = "fail"
                        message = (
                            f"Voter turnout ({turnout_pct:.1f}%) exceeds 100% of registered "
                            f"voters ({total_cast} / {reg_voters})."
                        )
                    elif turnout_pct > warn_pct:
                        status = "warn"
                        message = (
                            f"High voter turnout alert: {turnout_pct:.1f}% "
                            f"({total_cast} of {reg_voters} voters)."
                        )
                    else:
                        message = (
                            f"Voter turnout ({turnout_pct:.1f}%) is within expected threshold "
                            f"({total_cast} / {reg_voters})."
                        )
                elif sum_party_votes > 0:
                    turnout_pct = (sum_party_votes / float(reg_voters)) * 100.0
                    if turnout_pct > warn_pct:
                        status = "warn"
                        message = (
                            f"Party votes so far are {turnout_pct:.1f}% of registered voters "
                            f"({sum_party_votes} / {reg_voters}); awaiting final page totals."
                        )
                    else:
                        message = (
                            f"Party votes ({sum_party_votes}) are within registered voters "
                            f"({reg_voters})."
                        )
                else:
                    message = f"Registered voters: {reg_voters}."

            # 3b. Explicit votes-vs-registered ceiling (party sum and cast)
            elif code == "VOTES_WITHIN_REGISTERED":
                over_party = sum_party_votes > reg_voters
                over_cast = total_cast > reg_voters if total_cast > 0 else False
                if over_party or over_cast:
                    status = "fail" if severity == "error" else "warn"
                    parts = []
                    if over_party:
                        parts.append(f"party sum {sum_party_votes}")
                    if over_cast:
                        parts.append(f"votes cast {total_cast}")
                    message = (
                        f"{' and '.join(parts)} exceed registered voters ({reg_voters})."
                    )
                else:
                    message = (
                        f"Votes within registered voters: parties={sum_party_votes}, "
                        f"cast={total_cast}, registered={reg_voters}."
                    )

            # 4. Complete Multi-Page Set Requirement
            elif code == "ALL_PAGES_PRESENT":
                missing = [p for p in range(1, expected_pages + 1) if p not in received_page_nums]
                if missing:
                    status = "fail"
                    message = f"Mandatory Multi-Page Rule 2: Result set is incomplete. Received page(s) {received_page_nums}, missing page(s) {missing} of {expected_pages}. Approval blocked."
                else:
                    message = f"All {expected_pages} expected pages are present and verified."

            # 5. Presiding Officer Signature
            elif code == "OFFICER_SIGNATURE_PRESENT":
                if expected_pages in received_page_nums:
                    if not slip["presiding_officer_signature_detected"]:
                        status = "warn"
                        message = "Presiding officer signature not verified on the final summary slip page."
                    else:
                        message = f"Presiding officer signature verified for {slip['presiding_officer_name'] or 'officer'}."
                else:
                    message = "Final page required for signature verification."

            # 6. Duplicate Slip Protection
            elif code == "DUPLICATE_VD_BALLOT":
                cursor.execute("""
                    SELECT id, slip_reference FROM slips
                    WHERE voting_district = ? AND ballot_type = ? AND status = 'approved' AND id != ?
                """, (slip["voting_district"], slip["ballot_type"], slip_id))
                dup_approved = cursor.fetchone()
                if dup_approved:
                    status = "fail"
                    message = f"Duplicate approved result detected for VD {slip['voting_district']} and ballot type {slip['ballot_type']} (Slip ID: {dup_approved['id']})."
                else:
                    message = "No duplicate approved result exists for this VD and ballot type."

            # 7. Party Signatures on Non-Zero Rows
            elif code == "PARTY_SIGNATURE_CONSISTENCY":
                unsigned_rows = [r["party_code"] for r in party_rows if r["votes"] > 0 and not r["signature_detected"]]
                if unsigned_rows:
                    status = "warn"
                    message = f"Party agent signature missing on non-zero rows: {', '.join(unsigned_rows[:5])}."
                else:
                    message = "Party agent signatures verified on all non-zero vote rows."

            if status == "fail":
                has_critical_error = True
            elif status == "warn":
                has_warning = True

            res_id = f"vr_{uuid.uuid4().hex[:12]}"
            cursor.execute("""
                INSERT INTO validation_results (
                    id, slip_id, rule_code, status, message, evaluated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (res_id, slip_id, code, status, message, now))

            eval_results.append({
                "rule_code": code,
                "name": name,
                "status": status,
                "severity": severity,
                "message": message,
                "evaluated_at": now
            })

        conn.commit()
        conn.close()

        is_eligible_for_approval = (not has_critical_error) and (slip["status"] != "incomplete")

        return {
            "slip_id": slip_id,
            "is_eligible_for_approval": is_eligible_for_approval,
            "has_critical_error": has_critical_error,
            "has_warning": has_warning,
            "validation_results": eval_results
        }

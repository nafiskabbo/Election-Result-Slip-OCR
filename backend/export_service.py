import csv
import io
import json
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from backend.database import get_db_connection

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

class ExportService:
    def __init__(self):
        pass

    def export_slips_summary_csv(self, status_filter: Optional[str] = None) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()

        query = "SELECT * FROM slips"
        params = []
        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter)
        query += " ORDER BY created_at DESC"

        cursor.execute(query, params)
        slips = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "Slip ID", "Reference", "Ballot Type", "Election", "Province", "Municipality",
            "Voting District", "Station Name", "Registered Voters", "Status",
            "Valid Votes", "Spoilt Votes", "Total Votes Cast", "Special Votes",
            "Pages Expected", "Pages Received", "Approved By", "Approved At",
            "Processing Started At", "Processing Ended At", "Uploaded At"
        ])

        for s in slips:
            writer.writerow([
                s["id"], s["slip_reference"], s["ballot_type"], s["election_name"],
                s["province"] or "", s["municipality"] or "", s["voting_district"],
                s["station_name"] or "", s["registered_voters"], s["status"],
                s["total_valid_votes"], s["total_spoilt_votes"], s["total_votes_cast"],
                s["special_votes"], s["total_expected_pages"], s["total_received_pages"],
                s["approved_by"] or "", s["approved_at"] or "",
                s.get("processing_started_at") or "", s.get("processing_ended_at") or "",
                s["created_at"]
            ])

        conn.close()
        return output.getvalue()

    def export_slip_detailed_csv(self, slip_id: str) -> str:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
        slip = cursor.fetchone()
        if not slip:
            conn.close()
            raise ValueError(f"Slip {slip_id} not found.")

        cursor.execute("""
            SELECT pr.*, sp.page_number 
            FROM party_results pr
            JOIN slip_pages sp ON pr.page_id = sp.id
            WHERE pr.slip_id = ?
            ORDER BY sp.page_number ASC, pr.row_index ASC
        """, (slip_id,))
        party_rows = cursor.fetchall()

        output = io.StringIO()
        writer = csv.writer(output)

        writer.writerow(["# ELECTION RESULT SLIP DETAILED EXPORT"])
        writer.writerow(["Slip ID", slip["id"]])
        writer.writerow(["Slip Reference", slip["slip_reference"]])
        writer.writerow(["Ballot Type", slip["ballot_type"]])
        writer.writerow(["Voting District", slip["voting_district"]])
        writer.writerow(["Station Name", slip["station_name"]])
        writer.writerow(["Total Valid Votes", slip["total_valid_votes"]])
        writer.writerow(["Total Votes Cast", slip["total_votes_cast"]])
        writer.writerow([])

        writer.writerow([
            "Page", "Row Index", "Party Name", "Party Code", "Votes",
            "Confidence Score", "Manual Override", "Agent Signature Detected"
        ])

        for r in party_rows:
            writer.writerow([
                r["page_number"], r["row_index"] + 1, r["party_name"], r["party_code"],
                r["votes"], f"{r['confidence_score']:.2f}",
                "YES" if r["is_overridden"] else "NO",
                "YES" if r["signature_detected"] else "NO"
            ])

        conn.close()
        return output.getvalue()

    def export_slips_summary_json(self, status_filter: Optional[str] = None) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()
        if status_filter:
            cursor.execute("SELECT * FROM slips WHERE status = ? ORDER BY created_at DESC", (status_filter,))
        else:
            cursor.execute("SELECT * FROM slips ORDER BY created_at DESC")
        slips = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return {
            "count": len(slips),
            "slips": slips,
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }

    def export_slip_json(self, slip_id: str) -> Dict[str, Any]:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM slips WHERE id = ?", (slip_id,))
        slip = cursor.fetchone()
        if not slip:
            conn.close()
            raise ValueError(f"Slip {slip_id} not found.")

        cursor.execute("SELECT * FROM slip_pages WHERE slip_id = ? ORDER BY page_number ASC", (slip_id,))
        pages = [dict(p) for p in cursor.fetchall()]

        cursor.execute("""
            SELECT pr.*, sp.page_number
            FROM party_results pr
            JOIN slip_pages sp ON pr.page_id = sp.id
            WHERE pr.slip_id = ?
            ORDER BY sp.page_number ASC, pr.row_index ASC
        """, (slip_id,))
        party_results = [dict(pr) for pr in cursor.fetchall()]

        cursor.execute("SELECT * FROM validation_results WHERE slip_id = ?", (slip_id,))
        val_results = [dict(vr) for vr in cursor.fetchall()]

        cursor.execute("""
            SELECT a.*, u.username as user_name, u.role as user_role
            FROM audit_logs a
            LEFT JOIN users u ON a.user_id = u.id
            WHERE a.slip_id = ?
            ORDER BY a.timestamp ASC
        """, (slip_id,))
        audit_logs = [dict(al) for al in cursor.fetchall()]

        conn.close()

        data = {
            "slip": dict(slip),
            "pages": pages,
            "party_results": party_results,
            "validation_results": val_results,
            "audit_trail": audit_logs,
            "exported_at": datetime.now(timezone.utc).isoformat()
        }
        return data

    def generate_slip_pdf(self, slip_id: str) -> bytes:
        data = self.export_slip_json(slip_id)
        slip = data["slip"]
        parties = data["party_results"]

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "CertTitle",
            parent=styles["Heading1"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#0F172A"),
            alignment=1
        )
        subtitle_style = ParagraphStyle(
            "CertSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#475569"),
            alignment=1
        )
        meta_label_style = ParagraphStyle(
            "MetaLabel",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#64748B"),
            fontName="Helvetica-Bold"
        )
        meta_val_style = ParagraphStyle(
            "MetaVal",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#0F172A")
        )

        story = []

        # Header Title
        story.append(Paragraph("<b>OFFICIAL ELECTION RESULT SLIP CERTIFICATE</b>", title_style))
        story.append(Paragraph(f"{slip['election_name'].upper()} — {slip['ballot_type'].upper()} BALLOT", subtitle_style))
        story.append(Spacer(1, 10))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#0F172A"), spaceAfter=10))

        # Metadata Table
        meta_data = [
            [
                Paragraph("<b>Voting District (VD):</b>", meta_label_style),
                Paragraph(str(slip["voting_district"]), meta_val_style),
                Paragraph("<b>Ballot Slip Reference:</b>", meta_label_style),
                Paragraph(str(slip["slip_reference"]), meta_val_style)
            ],
            [
                Paragraph("<b>Station Name:</b>", meta_label_style),
                Paragraph(str(slip["station_name"] or "N/A"), meta_val_style),
                Paragraph("<b>Status:</b>", meta_label_style),
                Paragraph(f"<b>{slip['status'].upper()}</b>", meta_val_style)
            ],
            [
                Paragraph("<b>Municipality:</b>", meta_label_style),
                Paragraph(str(slip["municipality"] or "N/A"), meta_val_style),
                Paragraph("<b>Province:</b>", meta_label_style),
                Paragraph(str(slip["province"] or "N/A"), meta_val_style)
            ],
            [
                Paragraph("<b>Registered Voters:</b>", meta_label_style),
                Paragraph(str(slip["registered_voters"]), meta_val_style),
                Paragraph("<b>Multi-Page Set:</b>", meta_label_style),
                Paragraph(f"{slip['total_received_pages']} of {slip['total_expected_pages']} Pages Received", meta_val_style)
            ]
        ]
        meta_table = Table(meta_data, colWidths=[110, 160, 120, 150])
        meta_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(meta_table)
        story.append(Spacer(1, 12))

        # Party Results Table
        table_header = ["#", "Party / Candidate Name", "Code", "Votes", "Confidence", "Agent Signature"]
        table_rows = [table_header]

        for idx, p in enumerate(parties):
            sig_text = "Verified" if p["signature_detected"] else "None"
            table_rows.append([
                str(idx + 1),
                p["party_name"][:35],
                p["party_code"],
                str(p["votes"]),
                f"{p['confidence_score'] * 100:.0f}%",
                sig_text
            ])

        col_widths = [25, 260, 70, 55, 65, 65]
        party_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        party_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E293B")),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 8),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'),
            ('ALIGN', (3, 0), (4, -1), 'RIGHT'),
            ('ALIGN', (5, 0), (5, -1), 'CENTER'),
            ('FONTSIZE', (0, 1), (-1, -1), 7.5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")])
        ]))
        story.append(party_table)
        story.append(Spacer(1, 10))

        # Totals Summary Block
        totals_data = [
            ["TOTAL VALID VOTES CAST", str(slip["total_valid_votes"])],
            ["TOTAL SPOILT RESULTS", str(slip["total_spoilt_votes"])],
            ["TOTAL VOTES CAST", str(slip["total_votes_cast"])],
            ["SPECIAL VOTES", str(slip["special_votes"])],
            ["PRESIDING OFFICER", slip["presiding_officer_name"] or "N/A"]
        ]
        totals_table = Table(totals_data, colWidths=[380, 160])
        totals_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor("#0F172A")),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 8.5),
            ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(totals_table)

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

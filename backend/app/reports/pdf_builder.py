"""PDF report builder using ReportLab."""
from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.reports.base import BaseReportBuilder


class PDFReportBuilder(BaseReportBuilder):
    """Builds a formatted PDF report for project progress and delay risks."""

    def build(self, data: dict[str, Any]) -> bytes:
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()
        title_style = ParagraphStyle(
            "DocTitle",
            parent=styles["Title"],
            fontSize=18,
            leading=22,
            textColor=colors.HexColor("#1E293B"),
            alignment=0,
        )
        heading_style = ParagraphStyle(
            "SectionHeading",
            parent=styles["Heading2"],
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#0F172A"),
            spaceBefore=10,
            spaceAfter=6,
        )
        body_style = ParagraphStyle(
            "Body",
            parent=styles["Normal"],
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#334155"),
        )
        body_bold = ParagraphStyle(
            "BodyBold",
            parent=body_style,
            fontName="Helvetica-Bold",
        )

        elements: list[Any] = []

        # Header Title
        report_title = data.get("title", "Project Progress & Delay Risk Report")
        elements.append(Paragraph(report_title, title_style))
        elements.append(Spacer(1, 8))

        # Project Metadata Box
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        meta_data = [
            [
                Paragraph("<b>Project:</b>", body_style),
                Paragraph(self.project_name, body_style),
                Paragraph("<b>Generated:</b>", body_style),
                Paragraph(generated_at, body_style),
            ],
            [
                Paragraph("<b>Discipline Filter:</b>", body_style),
                Paragraph(str(self.parameters.get("discipline") or "All"), body_style),
                Paragraph("<b>Status Filter:</b>", body_style),
                Paragraph(str(self.parameters.get("status") or "All"), body_style),
            ],
        ]
        meta_table = Table(meta_data, colWidths=[100, 170, 80, 190])
        meta_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F1F5F9")),
                    ("PADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements.append(meta_table)
        elements.append(Spacer(1, 14))

        # Executive Summary Section
        elements.append(Paragraph("Executive Summary", heading_style))
        summary = data.get("summary", {})
        summary_rows = [
            [
                Paragraph("<b>Total Activities</b>", body_bold),
                Paragraph(str(summary.get("total_activities", 0)), body_style),
                Paragraph("<b>Completed</b>", body_bold),
                Paragraph(str(summary.get("completed_activities", 0)), body_style),
            ],
            [
                Paragraph("<b>In Progress</b>", body_bold),
                Paragraph(str(summary.get("in_progress_activities", 0)), body_style),
                Paragraph("<b>Delayed Activities</b>", body_bold),
                Paragraph(str(summary.get("delayed_activities", 0)), body_style),
            ],
            [
                Paragraph("<b>Overall Progress</b>", body_bold),
                Paragraph(f"{summary.get('progress_pct', 0.0):.1f}%", body_style),
                Paragraph("<b>High Risk Count</b>", body_bold),
                Paragraph(str(summary.get("high_risk_count", 0)), body_style),
            ],
        ]
        summary_table = Table(summary_rows, colWidths=[130, 140, 130, 140])
        summary_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FFFFFF")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("PADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        elements.append(summary_table)
        elements.append(Spacer(1, 14))

        # Key Activities Breakdown
        elements.append(Paragraph("Activity Status Breakdown", heading_style))
        activities = data.get("activities", [])
        act_rows: list[list[Any]] = [
            [
                Paragraph("<b>WBS / Code</b>", body_bold),
                Paragraph("<b>Activity Name</b>", body_bold),
                Paragraph("<b>Status</b>", body_bold),
                Paragraph("<b>Progress</b>", body_bold),
                Paragraph("<b>Risk Band</b>", body_bold),
            ]
        ]
        if not activities:
            act_rows.append(
                [
                    Paragraph("N/A", body_style),
                    Paragraph("No activities found matching parameters", body_style),
                    Paragraph("-", body_style),
                    Paragraph("-", body_style),
                    Paragraph("-", body_style),
                ]
            )
        else:
            for act in activities[:25]:  # Top 25 activities in PDF summary
                act_rows.append(
                    [
                        Paragraph(str(act.get("code") or act.get("wbs_path") or "-"), body_style),
                        Paragraph(str(act.get("name") or "Unnamed"), body_style),
                        Paragraph(str(act.get("status") or "NOT_STARTED"), body_style),
                        Paragraph(f"{act.get('progress_pct', 0.0):.0f}%", body_style),
                        Paragraph(str(act.get("risk_band") or "LOW"), body_style),
                    ]
                )

        act_table = Table(act_rows, colWidths=[90, 200, 85, 80, 85])
        act_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1F5F9")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E2E8F0")),
                    ("PADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(act_table)

        doc.build(elements)
        buffer.seek(0)
        return buffer.getvalue()

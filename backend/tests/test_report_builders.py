"""Unit tests for PDF and Excel report builders."""
from __future__ import annotations

import io
import openpyxl

from app.reports.excel_builder import ExcelReportBuilder
from app.reports.pdf_builder import PDFReportBuilder


def test_pdf_report_builder_generates_valid_pdf_bytes() -> None:
    sample_data = {
        "title": "Test Progress Report",
        "summary": {
            "total_activities": 10,
            "completed_activities": 4,
            "in_progress_activities": 3,
            "delayed_activities": 1,
            "high_risk_count": 2,
            "progress_pct": 45.0,
        },
        "activities": [
            {
                "code": "ACT-101",
                "name": "Excavation",
                "discipline": "CIVIL",
                "wbs_path": "1.1",
                "status": "COMPLETED",
                "progress_pct": 100.0,
                "risk_band": "LOW",
            },
            {
                "code": "ACT-102",
                "name": "Piping",
                "discipline": "PIPING",
                "wbs_path": "1.2",
                "status": "IN_PROGRESS",
                "progress_pct": 50.0,
                "risk_band": "HIGH",
            },
        ],
    }

    builder = PDFReportBuilder("Sample Project", {"discipline": "CIVIL"})
    pdf_bytes = builder.build(sample_data)

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 0
    assert pdf_bytes.startswith(b"%PDF-")


def test_excel_report_builder_generates_valid_workbook() -> None:
    sample_data = {
        "summary": {
            "total_activities": 5,
            "completed_activities": 2,
            "in_progress_activities": 2,
            "delayed_activities": 1,
            "high_risk_count": 1,
            "progress_pct": 40.0,
        },
        "activities": [
            {
                "code": "A1",
                "name": "Foundation",
                "discipline": "CIVIL",
                "wbs_path": "1",
                "status": "COMPLETED",
                "progress_pct": 100.0,
                "risk_band": "LOW",
            }
        ],
        "risks": [
            {
                "code": "A2",
                "name": "Structure",
                "risk_score": 0.85,
                "risk_band": "HIGH",
                "forecast_delay_days": 12,
                "top_factors": "Weather delay",
            }
        ],
    }

    builder = ExcelReportBuilder("Sample Project", {"status": "IN_PROGRESS"})
    xlsx_bytes = builder.build(sample_data)

    assert isinstance(xlsx_bytes, bytes)
    assert len(xlsx_bytes) > 0

    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes))
    sheet_names = wb.sheetnames
    assert "Executive Summary" in sheet_names
    assert "Activity Details" in sheet_names
    assert "Delay Risk Analysis" in sheet_names

    ws_summary = wb["Executive Summary"]
    assert "Sample Project" in ws_summary["A1"].value

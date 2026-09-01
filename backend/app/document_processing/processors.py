"""Swappable parsers that return plain extracted document data."""
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import pandas as pd
from app.core.exceptions import UnprocessableFileError

@dataclass(frozen=True)
class ProcessorResult:
    raw_text: str
    metadata: dict[str, Any] = field(default_factory=dict)
class DocumentProcessor(ABC):
    name = "document"
    @abstractmethod
    def process(self, path: Path) -> ProcessorResult: ...
class OCRProcessor(ABC):
    name = "ocr"
    @abstractmethod
    def extract_text(self, source_path: Path) -> str: ...
class NoopOCRProcessor(OCRProcessor):
    name = "noop-ocr"
    def extract_text(self, source_path: Path) -> str: return ""
class PDFProcessor(DocumentProcessor):
    name = "pdf"
    def __init__(self, ocr: OCRProcessor | None = None) -> None: self.ocr = ocr or NoopOCRProcessor()
    def process(self, path: Path) -> ProcessorResult:
        try:
            import fitz
            document = fitz.open(path)
            try: text, pages = "\n".join(page.get_text("text") for page in document), document.page_count
            finally: document.close()
        except Exception as exc: raise UnprocessableFileError(f"Unable to read PDF: {exc}") from exc
        try:
            import pdfplumber
            with pdfplumber.open(path) as pdf: tables = sum(len(page.extract_tables()) for page in pdf.pages)
        except Exception: tables = 0
        if not text.strip(): text = self.ocr.extract_text(path)
        return ProcessorResult(text, {"page_count": pages, "table_count": tables, "ocr_used": bool(text.strip()), "ocr_provider": self.ocr.name})
class ExcelProcessor(DocumentProcessor):
    name = "excel"
    def process(self, path: Path) -> ProcessorResult:
        try: sheets = pd.read_excel(path, sheet_name=None)
        except Exception as exc: raise UnprocessableFileError(f"Unable to read spreadsheet: {exc}") from exc
        frames = [f"[Sheet: {name}]\n{frame.dropna(how='all').to_csv(index=False)}" for name, frame in sheets.items()]
        return ProcessorResult("\n".join(frames), {"sheets": list(sheets), "rows": sum(len(frame.dropna(how='all')) for frame in sheets.values())})
class CSVProcessor(DocumentProcessor):
    name = "csv"
    def process(self, path: Path) -> ProcessorResult:
        try: frame = pd.read_csv(path)
        except Exception as exc: raise UnprocessableFileError(f"Unable to read CSV: {exc}") from exc
        return ProcessorResult(frame.to_csv(index=False), {"rows": len(frame), "columns": list(frame.columns)})
class TextProcessor(DocumentProcessor):
    name = "text"
    def process(self, path: Path) -> ProcessorResult: return ProcessorResult(path.read_bytes().decode("utf-8", errors="replace"))
class ImageProcessor(DocumentProcessor):
    name = "image"
    def __init__(self, ocr: OCRProcessor | None = None) -> None: self.ocr = ocr or NoopOCRProcessor()
    def process(self, path: Path) -> ProcessorResult:
        text = self.ocr.extract_text(path); return ProcessorResult(text, {"ocr_used": bool(text.strip()), "ocr_provider": self.ocr.name})
def processor_for(path: Path, *, ocr: OCRProcessor | None = None) -> DocumentProcessor:
    suffix = path.suffix.lower()
    if suffix == ".pdf": return PDFProcessor(ocr)
    if suffix in {".xlsx", ".xls"}: return ExcelProcessor()
    if suffix == ".csv": return CSVProcessor()
    if suffix in {".txt", ".xml", ".xer"}: return TextProcessor()
    if suffix in {".png", ".jpg", ".jpeg"}: return ImageProcessor(ocr)
    raise UnprocessableFileError(f"No processor is configured for '{suffix}'.")

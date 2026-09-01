"""Document processor abstractions and concrete local parsers."""
from app.document_processing.processors import DocumentProcessor, ExcelProcessor, OCRProcessor, PDFProcessor, processor_for
__all__ = ["DocumentProcessor", "ExcelProcessor", "OCRProcessor", "PDFProcessor", "processor_for"]

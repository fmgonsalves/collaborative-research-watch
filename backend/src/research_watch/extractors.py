from __future__ import annotations

from pathlib import Path

from docx import Document
from pypdf import PdfReader

from .models import ExtractedSourceText, ExtractionResult, SourceRecord

SIMPLE_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
PDF_PAGE_LIMIT = 50


def extraction_success(source_id: str, content_text: str, extractor: str = "simple-text") -> ExtractionResult:
    return ExtractionResult(
        source_id=source_id,
        extracted=ExtractedSourceText(source_id=source_id, content_text=content_text),
        extractor=extractor,
    )


def extraction_failure(
    source_id: str,
    error_summary: str,
    diagnostics: str | None = None,
    extractor: str = "simple-text",
) -> ExtractionResult:
    return ExtractionResult(source_id=source_id, error_summary=error_summary, diagnostics=diagnostics, extractor=extractor)


def extract_document_text(source: SourceRecord, path: Path) -> ExtractionResult:
    if source.type != "document":
        return extraction_failure(source.source_id, "Only local document sources can be extracted.")
    extension = path.suffix.lower()
    if extension == ".docx":
        return extract_docx_file(source, path)
    if extension == ".pdf":
        return extract_pdf_file(source, path)
    return extract_simple_text_file(source, path)


def extract_simple_text_file(source: SourceRecord, path: Path) -> ExtractionResult:
    if source.type != "document":
        return extraction_failure(source.source_id, "Only local document sources can be extracted.")
    extension = path.suffix.lower()
    if extension not in SIMPLE_TEXT_EXTENSIONS:
        return extraction_failure(source.source_id, f"Unsupported extraction format: {extension or '(none)'}.")
    try:
        return extraction_success(source.source_id, path.read_text(encoding="utf-8"))
    except UnicodeDecodeError as error:
        return extraction_failure(source.source_id, "Could not decode source text as UTF-8.", repr(error))
    except OSError as error:
        return extraction_failure(source.source_id, "Could not read source file.", repr(error))


def extract_pdf_file(source: SourceRecord, path: Path) -> ExtractionResult:
    if source.type != "document":
        return extraction_failure(source.source_id, "Only local document sources can be extracted.", extractor="pypdf")
    try:
        reader = PdfReader(path)
        page_texts = [
            text.strip()
            for page in reader.pages[:PDF_PAGE_LIMIT]
            if (text := page.extract_text()) and text.strip()
        ]
    except Exception as error:
        return extraction_failure(source.source_id, "Could not extract text from PDF.", repr(error), extractor="pypdf")
    content_text = "\n\n".join(page_texts)
    if not content_text:
        return extraction_failure(source.source_id, "No readable text found in PDF.", extractor="pypdf")
    return extraction_success(source.source_id, content_text, extractor="pypdf")


def extract_docx_file(source: SourceRecord, path: Path) -> ExtractionResult:
    if source.type != "document":
        return extraction_failure(source.source_id, "Only local document sources can be extracted.", extractor="python-docx")
    try:
        document = Document(str(path))
        paragraph_texts = [paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()]
    except Exception as error:
        return extraction_failure(source.source_id, "Could not extract text from DOCX.", repr(error), extractor="python-docx")
    content_text = "\n\n".join(paragraph_texts)
    if not content_text:
        return extraction_failure(source.source_id, "No readable text found in DOCX.", extractor="python-docx")
    return extraction_success(source.source_id, content_text, extractor="python-docx")

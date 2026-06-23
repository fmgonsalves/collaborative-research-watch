from __future__ import annotations

from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from docx import Document
from pypdf import PdfReader

from .models import ExtractedSourceText, ExtractionResult, SourceRecord

SIMPLE_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}
PDF_PAGE_LIMIT = 50
LINK_FETCH_TIMEOUT_SECONDS = 10.0
HTML_EXTRACTOR = "html"


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


def fetch_link_text(source: SourceRecord, client: httpx.Client | None = None) -> ExtractionResult:
    if source.type != "link" or not source.original_url:
        return extraction_failure(source.source_id, "Only web link sources can be fetched.", extractor=HTML_EXTRACTOR)
    if not source.original_url.startswith(("http://", "https://")):
        return extraction_failure(source.source_id, "Only HTTP and HTTPS links can be fetched.", extractor=HTML_EXTRACTOR)

    owns_client = client is None
    active_client = client or httpx.Client(timeout=LINK_FETCH_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        response = active_client.get(
            source.original_url,
            headers={"User-Agent": "CollaborativeResearchWatch/0.1"},
        )
    except httpx.RequestError as error:
        return extraction_failure(source.source_id, "Could not fetch link content.", repr(error), extractor=HTML_EXTRACTOR)
    finally:
        if owns_client:
            active_client.close()

    if response.status_code < 200 or response.status_code >= 300:
        return extraction_failure(
            source.source_id,
            "Link is blocked or inaccessible.",
            f"HTTP status {response.status_code}",
            extractor=HTML_EXTRACTOR,
        )
    content_type = response.headers.get("content-type", "").lower()
    if "html" not in content_type:
        return extraction_failure(
            source.source_id,
            "Link did not return readable HTML.",
            f"Content-Type: {content_type or '(missing)'}",
            extractor=HTML_EXTRACTOR,
        )

    try:
        content_text = extract_visible_html_text(response.text)
    except Exception as error:
        return extraction_failure(source.source_id, "Link did not return readable HTML.", repr(error), extractor=HTML_EXTRACTOR)
    if not content_text:
        return extraction_failure(source.source_id, "Link did not return readable HTML.", extractor=HTML_EXTRACTOR)
    return extraction_success(source.source_id, content_text, extractor=HTML_EXTRACTOR)


def extract_visible_html_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "noscript", "template", "meta", "link", "header", "nav", "footer", "aside"]):
        tag.decompose()
    root = soup.body or soup
    lines = [" ".join(text.split()) for text in root.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


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

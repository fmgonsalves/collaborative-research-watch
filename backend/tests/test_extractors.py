from __future__ import annotations

from pathlib import Path

from docx import Document

from research_watch.ai_input import build_ai_safe_source_input
from research_watch.extractors import extract_document_text, extract_simple_text_file
from research_watch.models import SourceRecord


def source_record(**overrides: object) -> SourceRecord:
    values: dict[str, object] = {
        "source_id": "src_abc123",
        "type": "document",
        "title": "Example Source",
        "lifecycle_status": "available",
        "date_added": "2026-06-15T12:00:00+00:00",
        "last_seen_at": "2026-06-15T12:00:00+00:00",
        "updated_at": "2026-06-15T12:00:00+00:00",
    }
    values.update(overrides)
    return SourceRecord.model_validate(values)


def assert_extracted_text(path: Path, expected: str) -> None:
    source = source_record(relative_path=f"sources/{path.name}")

    result = extract_document_text(source, path)

    assert result.error_summary is None
    assert result.diagnostics is None
    assert result.extracted is not None
    assert result.extracted.source_id == source.source_id
    assert result.extracted.content_text == expected


def pdf_bytes(page_texts: list[str]) -> bytes:
    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{' '.join(f'{index} 0 R' for index in range(3, 3 + len(page_texts)))}] /Count {len(page_texts)} >>".encode(),
    ]
    content_object_start = 3 + len(page_texts)
    for index, _ in enumerate(page_texts):
        content_object_id = content_object_start + index
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 {content_object_start + len(page_texts)} 0 R >> >> /Contents {content_object_id} 0 R >>".encode()
        )
    for text in page_texts:
        escaped_text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = f"BT /F1 24 Tf 72 720 Td ({escaped_text}) Tj ET\n".encode()
        objects.append(b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream")
    objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for object_id, body in enumerate(objects, start=1):
        offsets.append(len(output))
        output.extend(f"{object_id} 0 obj\n".encode())
        output.extend(body)
        output.extend(b"\nendobj\n")
    xref_offset = len(output)
    output.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    output.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode())
    return bytes(output)


def write_pdf(path: Path, page_texts: list[str]) -> None:
    path.write_bytes(pdf_bytes(page_texts))


def write_docx(path: Path, paragraph_texts: list[str]) -> None:
    document = Document()
    for text in paragraph_texts:
        document.add_paragraph(text)
    document.save(path)


def test_txt_extraction_returns_raw_decoded_text(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    text = "First line\n\nSecond line with punctuation: * untouched.\n"
    path.write_text(text, encoding="utf-8")

    assert_extracted_text(path, text)


def test_md_extraction_returns_raw_decoded_markdown(tmp_path: Path) -> None:
    path = tmp_path / "paper.md"
    text = "---\ntitle: Internal Metadata\n---\n# Heading\n\n- Item **one**\n"
    path.write_text(text, encoding="utf-8")

    assert_extracted_text(path, text)


def test_csv_extraction_returns_raw_decoded_csv(tmp_path: Path) -> None:
    path = tmp_path / "data.csv"
    text = "name,value\nalpha,1\nbeta,2\n"
    path.write_text(text, encoding="utf-8")

    assert_extracted_text(path, text)


def test_extracted_text_can_feed_ai_safe_input(tmp_path: Path) -> None:
    path = tmp_path / "paper.md"
    path.write_text("# Paper\nSource text.\n", encoding="utf-8")
    source = source_record(relative_path="sources/private-folder/paper.md")

    result = extract_simple_text_file(source, path)

    assert result.extracted is not None
    payload = build_ai_safe_source_input(source, result.extracted)
    assert payload.content_text == "# Paper\nSource text.\n"
    assert payload.filename == "paper.md"
    assert "private-folder" not in payload.model_dump_json()


def test_pdf_extraction_returns_text_from_fixture_pdf(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    write_pdf(path, ["First PDF page", "Second PDF page"])
    source = source_record(relative_path="sources/paper.pdf")

    result = extract_document_text(source, path)

    assert result.error_summary is None
    assert result.diagnostics is None
    assert result.extractor == "pypdf"
    assert result.extracted is not None
    assert result.extracted.content_text == "First PDF page\n\nSecond PDF page"


def test_pdf_extraction_reads_only_first_fifty_pages(tmp_path: Path) -> None:
    path = tmp_path / "long.pdf"
    write_pdf(path, [f"PDF page {number}" for number in range(1, 56)])
    source = source_record(relative_path="sources/long.pdf")

    result = extract_document_text(source, path)

    assert result.extracted is not None
    assert "PDF page 1" in result.extracted.content_text
    assert "PDF page 50" in result.extracted.content_text
    assert "PDF page 51" not in result.extracted.content_text
    assert "PDF page 55" not in result.extracted.content_text


def test_empty_pdf_returns_safe_extraction_failure(tmp_path: Path) -> None:
    path = tmp_path / "empty.pdf"
    write_pdf(path, [""])
    source = source_record(relative_path="sources/empty.pdf")

    result = extract_document_text(source, path)

    assert result.extracted is None
    assert result.error_summary == "No readable text found in PDF."
    assert result.diagnostics is None
    assert result.extractor == "pypdf"


def test_malformed_pdf_returns_safe_failure_with_internal_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"%PDF-this-is-not-valid")
    source = source_record(relative_path="sources/broken.pdf")

    result = extract_document_text(source, path)

    assert result.extracted is None
    assert result.error_summary == "Could not extract text from PDF."
    assert result.diagnostics is not None
    assert result.extractor == "pypdf"


def test_unsupported_extension_returns_safe_extraction_failure(tmp_path: Path) -> None:
    path = tmp_path / "paper.rtf"
    path.write_text("{\\rtf1 not supported}", encoding="utf-8")
    source = source_record(relative_path="sources/paper.rtf")

    result = extract_document_text(source, path)

    assert result.extracted is None
    assert result.error_summary == "Unsupported extraction format: .rtf."
    assert result.diagnostics is None


def test_bad_encoding_returns_safe_failure_with_internal_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xff\xfe\xfa")
    source = source_record(relative_path="sources/notes.txt")

    result = extract_document_text(source, path)

    assert result.extracted is None
    assert result.error_summary == "Could not decode source text as UTF-8."
    assert result.diagnostics is not None
    assert "UnicodeDecodeError" in result.diagnostics


def test_failure_diagnostics_do_not_enter_extracted_text_or_ai_safe_input(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xff")
    source = source_record(relative_path="sources/notes.txt")

    failure = extract_simple_text_file(source, path)
    fallback_path = tmp_path / "fallback.txt"
    fallback_path.write_text("Allowed replacement text.", encoding="utf-8")
    fallback = extract_simple_text_file(source, fallback_path)

    assert failure.extracted is None
    assert failure.diagnostics is not None
    assert fallback.extracted is not None
    payload_json = build_ai_safe_source_input(source, fallback.extracted).model_dump_json()
    assert failure.diagnostics not in payload_json
    assert failure.error_summary not in payload_json


def test_pdf_diagnostics_do_not_enter_extracted_text_or_ai_safe_input(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.pdf"
    broken_path.write_bytes(b"%PDF-broken")
    source = source_record(relative_path="sources/broken.pdf")

    failure = extract_document_text(source, broken_path)
    fallback_path = tmp_path / "fallback.pdf"
    write_pdf(fallback_path, ["Allowed PDF text"])
    fallback = extract_document_text(source, fallback_path)

    assert failure.extracted is None
    assert failure.diagnostics is not None
    assert fallback.extracted is not None
    payload_json = build_ai_safe_source_input(source, fallback.extracted).model_dump_json()
    assert failure.diagnostics not in payload_json
    assert failure.error_summary not in payload_json


def test_docx_extraction_returns_paragraph_text(tmp_path: Path) -> None:
    path = tmp_path / "brief.docx"
    write_docx(path, ["First DOCX paragraph", "", "Second DOCX paragraph"])
    source = source_record(relative_path="sources/brief.docx")

    result = extract_document_text(source, path)

    assert result.error_summary is None
    assert result.diagnostics is None
    assert result.extractor == "python-docx"
    assert result.extracted is not None
    assert result.extracted.content_text == "First DOCX paragraph\n\nSecond DOCX paragraph"


def test_empty_docx_returns_safe_extraction_failure(tmp_path: Path) -> None:
    path = tmp_path / "empty.docx"
    write_docx(path, ["", "   "])
    source = source_record(relative_path="sources/empty.docx")

    result = extract_document_text(source, path)

    assert result.extracted is None
    assert result.error_summary == "No readable text found in DOCX."
    assert result.diagnostics is None
    assert result.extractor == "python-docx"


def test_malformed_docx_returns_safe_failure_with_internal_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "broken.docx"
    path.write_bytes(b"not-a-real-docx")
    source = source_record(relative_path="sources/broken.docx")

    result = extract_document_text(source, path)

    assert result.extracted is None
    assert result.error_summary == "Could not extract text from DOCX."
    assert result.diagnostics is not None
    assert result.extractor == "python-docx"


def test_docx_diagnostics_do_not_enter_extracted_text_or_ai_safe_input(tmp_path: Path) -> None:
    broken_path = tmp_path / "broken.docx"
    broken_path.write_bytes(b"not-a-real-docx")
    source = source_record(relative_path="sources/broken.docx")

    failure = extract_document_text(source, broken_path)
    fallback_path = tmp_path / "fallback.docx"
    write_docx(fallback_path, ["Allowed DOCX text"])
    fallback = extract_document_text(source, fallback_path)

    assert failure.extracted is None
    assert failure.diagnostics is not None
    assert fallback.extracted is not None
    payload_json = build_ai_safe_source_input(source, fallback.extracted).model_dump_json()
    assert failure.diagnostics not in payload_json
    assert failure.error_summary not in payload_json

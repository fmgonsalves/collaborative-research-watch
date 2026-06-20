from __future__ import annotations

from pathlib import Path

from research_watch.ai_input import build_ai_safe_source_input
from research_watch.extractors import extract_simple_text_file
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

    result = extract_simple_text_file(source, path)

    assert result.error_summary is None
    assert result.diagnostics is None
    assert result.extracted is not None
    assert result.extracted.source_id == source.source_id
    assert result.extracted.content_text == expected


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


def test_unsupported_extension_returns_safe_extraction_failure(tmp_path: Path) -> None:
    path = tmp_path / "paper.pdf"
    path.write_bytes(b"%PDF-not-yet-supported")
    source = source_record(relative_path="sources/paper.pdf")

    result = extract_simple_text_file(source, path)

    assert result.extracted is None
    assert result.error_summary == "Unsupported extraction format: .pdf."
    assert result.diagnostics is None


def test_bad_encoding_returns_safe_failure_with_internal_diagnostics(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_bytes(b"\xff\xfe\xfa")
    source = source_record(relative_path="sources/notes.txt")

    result = extract_simple_text_file(source, path)

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

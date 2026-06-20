from __future__ import annotations

import pytest

from research_watch.ai_input import build_ai_safe_source_input
from research_watch.models import ExtractedSourceText, SourceRecord


def source_record(**overrides: object) -> SourceRecord:
    values: dict[str, object] = {
        "source_id": "src_abc123",
        "type": "document",
        "title": "Example Paper",
        "lifecycle_status": "available",
        "date_added": "2026-06-15T12:00:00+00:00",
        "last_seen_at": "2026-06-15T12:00:00+00:00",
        "updated_at": "2026-06-15T12:00:00+00:00",
    }
    values.update(overrides)
    return SourceRecord.model_validate(values)


def test_document_ai_safe_input_includes_allowed_public_fields() -> None:
    source = source_record(relative_path="sources/team-folder/paper.md")
    extracted = ExtractedSourceText(source_id="src_abc123", content_text="Normalized extracted text.")

    payload = build_ai_safe_source_input(source, extracted)

    assert payload.model_dump() == {
        "source_id": "src_abc123",
        "source_type": "document",
        "title": "Example Paper",
        "content_text": "Normalized extracted text.",
        "original_url": None,
        "filename": "paper.md",
    }


def test_link_ai_safe_input_includes_original_url() -> None:
    source = source_record(
        type="link",
        title="Example Link",
        original_url="https://example.com/research",
    )
    extracted = ExtractedSourceText(source_id="src_abc123", content_text="Fetched page text.")

    payload = build_ai_safe_source_input(source, extracted)

    assert payload.model_dump() == {
        "source_id": "src_abc123",
        "source_type": "link",
        "title": "Example Link",
        "content_text": "Fetched page text.",
        "original_url": "https://example.com/research",
        "filename": None,
    }


def test_ai_safe_input_serializes_only_approved_public_keys() -> None:
    source = source_record(
        relative_path="sources/team-confidential/project-alpha/paper.md",
        original_url="https://should-not-appear.example",
        content_size=123456,
        content_mtime=987654321.0,
    )
    extracted = ExtractedSourceText(source_id="src_abc123", content_text="Allowed source text.")

    payload = build_ai_safe_source_input(source, extracted)

    assert set(payload.model_dump()) == {
        "source_id",
        "source_type",
        "title",
        "content_text",
        "original_url",
        "filename",
    }


def test_ai_safe_input_excludes_forbidden_values_from_serialized_payload() -> None:
    source = source_record(
        relative_path="sources/team-confidential/project-alpha/paper.md",
        original_url="https://should-not-appear.example",
        content_size=123456,
        content_mtime=987654321.0,
    )
    extracted = ExtractedSourceText(source_id="src_abc123", content_text="Allowed source text.")
    forbidden_values = [
        "Human comment: read this first",
        "human-created-priority-tag",
        "Ada Lovelace",
        "ada@example.com",
        "selected-user@example.com",
        "https://should-not-appear.example",
        "/Users/fred/shared/private-workspace/sources/team-confidential/project-alpha/paper.md",
        "sources/team-confidential/project-alpha",
        "team-confidential",
        "project-alpha",
        "123456",
        "987654321",
        "PDF parser traceback",
        "Raw parser error",
        "cache-key-123",
        "run-internal-456",
    ]

    payload_json = build_ai_safe_source_input(source, extracted).model_dump_json()

    for value in forbidden_values:
        assert value not in payload_json
    assert "paper.md" in payload_json


def test_ai_safe_input_rejects_mismatched_extracted_source_text() -> None:
    source = source_record(source_id="src_expected")
    extracted = ExtractedSourceText(source_id="src_other", content_text="Extracted text.")

    with pytest.raises(ValueError, match="does not match"):
        build_ai_safe_source_input(source, extracted)

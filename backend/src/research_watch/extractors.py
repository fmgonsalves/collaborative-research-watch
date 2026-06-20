from __future__ import annotations

from pathlib import Path

from .models import ExtractedSourceText, ExtractionResult, SourceRecord

SIMPLE_TEXT_EXTENSIONS = {".txt", ".md", ".csv"}


def extraction_success(source_id: str, content_text: str) -> ExtractionResult:
    return ExtractionResult(
        source_id=source_id,
        extracted=ExtractedSourceText(source_id=source_id, content_text=content_text),
    )


def extraction_failure(source_id: str, error_summary: str, diagnostics: str | None = None) -> ExtractionResult:
    return ExtractionResult(source_id=source_id, error_summary=error_summary, diagnostics=diagnostics)


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

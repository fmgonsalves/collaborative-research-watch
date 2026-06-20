from __future__ import annotations

from pathlib import Path

from .models import AISafeSourceInput, ExtractedSourceText, SourceRecord


def build_ai_safe_source_input(source: SourceRecord, extracted: ExtractedSourceText) -> AISafeSourceInput:
    if source.source_id != extracted.source_id:
        raise ValueError("Extracted source text does not match the source record.")
    return AISafeSourceInput(
        source_id=source.source_id,
        source_type=source.type,
        title=source.title,
        content_text=extracted.content_text,
        original_url=source.original_url if source.type == "link" else None,
        filename=Path(source.relative_path).name if source.type == "document" and source.relative_path else None,
    )

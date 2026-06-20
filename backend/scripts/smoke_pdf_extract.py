from __future__ import annotations

import argparse
import sys
from pathlib import Path

from research_watch.extractors import extract_document_text
from research_watch.models import SourceRecord


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test PDF extraction for a local PDF file.")
    parser.add_argument("pdf", type=Path, help="Path to the PDF to extract.")
    parser.add_argument("--preview-chars", type=int, default=3000, help="Number of extracted characters to preview.")
    return parser.parse_args()


def smoke_source_record(path: Path) -> SourceRecord:
    timestamp = "2026-06-20T00:00:00+00:00"
    return SourceRecord(
        source_id="src_pdf_smoke",
        type="document",
        title=path.stem,
        lifecycle_status="available",
        date_added=timestamp,
        last_seen_at=timestamp,
        updated_at=timestamp,
        relative_path=f"sources/{path.name}",
    )


def main() -> int:
    args = parse_args()
    pdf_path = args.pdf.expanduser()
    if not pdf_path.exists():
        print(f"PDF not found: {pdf_path}", file=sys.stderr)
        return 2
    if not pdf_path.is_file():
        print(f"Path is not a file: {pdf_path}", file=sys.stderr)
        return 2

    result = extract_document_text(smoke_source_record(pdf_path), pdf_path)
    print(f"extractor: {result.extractor}")
    print(f"error_summary: {result.error_summary}")
    print(f"diagnostics: {result.diagnostics}")

    if result.extracted is None:
        return 1

    text = result.extracted.content_text
    preview_chars = max(args.preview_chars, 0)
    print(f"chars: {len(text)}")
    print("\n--- preview ---\n")
    print(text[:preview_chars])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

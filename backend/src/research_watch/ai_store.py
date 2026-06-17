from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from .markdown_store import read_markdown_record, write_markdown_record
from .models import AIRecord, ValidationIssue


def ai_records_dir(root: Path) -> Path:
    return root / "records" / "ai"


def ai_record_path(root: Path, source_id: str) -> Path:
    return ai_records_dir(root) / f"{source_id}.md"


def ai_record_frontmatter(record: AIRecord) -> dict[str, object]:
    return record.model_dump(exclude={"summary"}, exclude_none=True)


def validate_ai_record(path: Path) -> tuple[AIRecord | None, ValidationIssue | None]:
    frontmatter, body = read_markdown_record(path)
    try:
        return AIRecord.model_validate({**frontmatter, "summary": body.strip()}), None
    except ValidationError as error:
        return None, ValidationIssue(code="invalid_ai_record", message=str(error), path=str(path))


def read_ai_record(root: Path, source_id: str) -> tuple[AIRecord | None, list[ValidationIssue]]:
    path = ai_record_path(root, source_id)
    if not path.exists():
        return None, []
    record, issue = validate_ai_record(path)
    return record, [issue] if issue else []


def read_ai_records(root: Path) -> tuple[list[AIRecord], list[ValidationIssue]]:
    records: list[AIRecord] = []
    issues: list[ValidationIssue] = []
    for path in sorted(ai_records_dir(root).glob("src_*.md")):
        record, issue = validate_ai_record(path)
        if record is not None:
            records.append(record)
        if issue is not None:
            issues.append(issue)
    return records, issues


def write_ai_record(root: Path, record: AIRecord) -> None:
    write_markdown_record(ai_record_path(root, record.source_id), ai_record_frontmatter(record), record.summary)

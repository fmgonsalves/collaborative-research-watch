from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from research_watch.ai_store import ai_record_path, read_ai_record, read_ai_records, write_ai_record
from research_watch.csv_store import append_link, read_links, read_users, write_users
from research_watch.logging_config import configure_logging
from research_watch.markdown_store import read_markdown_record, write_markdown_record
from research_watch.models import AI_RECORD_STATUSES, AIRecord, UserRecord
from research_watch.sync import ResearchRepository
from research_watch.workspace import WorkspaceManager


def test_workspace_initialization_and_user_bootstrap(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    state = manager.select(str(tmp_path))

    assert state.initialized is True
    assert (tmp_path / "sources").is_dir()
    assert (tmp_path / "records" / "sources").is_dir()
    assert (tmp_path / "links.csv").read_text(encoding="utf-8") == "url,title\n"

    user = manager.bootstrap_user(type("Request", (), {"name": "Ada", "email": "ADA@example.com"})())
    assert user.email == "ada@example.com"
    users, issues = read_users(tmp_path / "users.csv")
    assert issues == []
    assert users == [UserRecord(name="Ada", email="ada@example.com")]


def test_csv_validation_reports_bad_headers_and_duplicates(tmp_path: Path) -> None:
    (tmp_path / "users.csv").write_text("email,name\nada@example.com,Ada\n", encoding="utf-8")
    users, issues = read_users(tmp_path / "users.csv")
    assert users == []
    assert issues[0].code == "invalid_users_header"

    write_users(
        tmp_path / "users.csv",
        [
            UserRecord(name="Ada", email="ada@example.com"),
            UserRecord(name="Duplicate", email="ada@example.com"),
        ],
    )
    users, issues = read_users(tmp_path / "users.csv")
    assert len(users) == 1
    assert issues[0].code == "duplicate_user_email"

    (tmp_path / "links.csv").write_text("title,url\nExample,https://example.com\n", encoding="utf-8")
    links, issues = read_links(tmp_path / "links.csv")
    assert links == []
    assert issues[0].code == "invalid_links_header"


def test_markdown_frontmatter_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "record.md"
    write_markdown_record(path, {"source_id": "src_123", "title": "Example"}, "# Body")

    frontmatter, body = read_markdown_record(path)

    assert frontmatter["source_id"] == "src_123"
    assert frontmatter["title"] == "Example"
    assert body == "# Body\n"


def test_ai_record_round_trip_writes_frontmatter_and_summary_body(tmp_path: Path) -> None:
    record = AIRecord(
        source_id="src_abc123",
        status="generated",
        generated_at="2026-06-15T12:00:00+00:00",
        source_title="Example Paper",
        source_type="document",
        ai_generated_tags=["economics", "methods"],
        summary="This is an AI-generated summary.",
        extractor="manual-fixture",
        model="test-model",
    )

    write_ai_record(tmp_path, record)
    read_record, issues = read_ai_record(tmp_path, "src_abc123")
    frontmatter, body = read_markdown_record(ai_record_path(tmp_path, "src_abc123"))

    assert issues == []
    assert read_record == record
    assert body == "This is an AI-generated summary.\n"
    assert frontmatter["source_id"] == "src_abc123"
    assert frontmatter["status"] == "generated"
    assert frontmatter["ai_generated_tags"] == ["economics", "methods"]
    assert "summary" not in frontmatter
    assert ai_record_path(tmp_path, "src_abc123") == tmp_path / "records" / "ai" / "src_abc123.md"


def test_ai_failure_record_round_trip_allows_empty_body_and_safe_error(tmp_path: Path) -> None:
    record = AIRecord(
        source_id="src_abc123",
        status="extraction_failed",
        generated_at="2026-06-15T12:00:00+00:00",
        source_title="Example Paper",
        source_type="document",
        ai_generated_tags=[],
        error_summary="Could not extract readable text.",
        extractor="pypdf",
    )

    write_ai_record(tmp_path, record)
    read_record, issues = read_ai_record(tmp_path, "src_abc123")
    frontmatter, body = read_markdown_record(ai_record_path(tmp_path, "src_abc123"))

    assert issues == []
    assert read_record == record
    assert body == ""
    assert frontmatter["error_summary"] == "Could not extract readable text."
    assert frontmatter["extractor"] == "pypdf"
    assert "model" not in frontmatter


def test_ai_record_accepts_documented_status_values() -> None:
    for status in sorted(AI_RECORD_STATUSES):
        AIRecord(
            source_id="src_abc123",
            status=status,
            generated_at="2026-06-15T12:00:00+00:00",
            source_title="Example",
            source_type="link",
        )

    with pytest.raises(ValidationError):
        AIRecord(
            source_id="src_abc123",
            status="pending",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title="Example",
            source_type="link",
        )


def test_invalid_ai_record_is_reported_and_skipped(tmp_path: Path) -> None:
    write_markdown_record(
        ai_record_path(tmp_path, "src_abc123"),
        {
            "source_id": "src_abc123",
            "status": "not_valid",
            "generated_at": "2026-06-15T12:00:00+00:00",
            "source_title": "Example",
            "source_type": "document",
        },
        "Summary",
    )

    records, issues = read_ai_records(tmp_path)
    read_record, read_issues = read_ai_record(tmp_path, "src_abc123")

    assert records == []
    assert [issue.code for issue in issues] == ["invalid_ai_record"]
    assert issues[0].path == str(ai_record_path(tmp_path, "src_abc123"))
    assert read_record is None
    assert [issue.code for issue in read_issues] == ["invalid_ai_record"]


def test_missing_ai_record_returns_none_without_issues(tmp_path: Path) -> None:
    record, issues = read_ai_record(tmp_path, "src_missing")

    assert record is None
    assert issues == []


def test_source_detail_skips_invalid_ai_record_and_logs_warning(tmp_path: Path, capsys) -> None:
    configure_logging()
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    (tmp_path / "sources" / "paper.md").write_text("content", encoding="utf-8")
    repo = ResearchRepository(tmp_path)
    repo.sync()
    source = repo.read_source_records()[0][0]
    capsys.readouterr()
    write_markdown_record(
        ai_record_path(tmp_path, source.source_id),
        {
            "source_id": source.source_id,
            "status": "not_valid",
            "generated_at": "2026-06-15T12:00:00+00:00",
            "source_title": source.title,
            "source_type": source.type,
        },
        "Summary",
    )

    detail = repo.detail(source.source_id)

    captured = capsys.readouterr().err
    assert detail is not None
    assert detail.ai is None
    assert "invalid_ai_record" in captured
    assert source.source_id in captured
    assert str(ai_record_path(tmp_path, source.source_id)) in captured


def test_sync_emits_start_and_finish_logs(tmp_path: Path, capsys) -> None:
    configure_logging()
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    (tmp_path / "sources" / "paper.md").write_text("content", encoding="utf-8")
    repo = ResearchRepository(tmp_path)

    repo.sync()

    captured = capsys.readouterr().err
    assert "Sync started" in captured
    assert "Sync finished" in captured


def test_document_unchanged_when_size_and_mtime_stable(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    document = tmp_path / "sources" / "paper.md"
    document.write_text("stable content", encoding="utf-8")
    repo = ResearchRepository(tmp_path)

    first = repo.sync()
    assert first.created == 1

    second = repo.sync()
    assert second.changed == 0
    record = repo.read_source_records()[0][0]
    assert record.lifecycle_status == "available"


def test_legacy_record_without_size_mtime_establishes_baseline_without_changed(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    document = tmp_path / "sources" / "paper.md"
    document.write_text("legacy content", encoding="utf-8")
    records_dir = tmp_path / "records" / "sources"
    records_dir.mkdir(parents=True, exist_ok=True)
    write_markdown_record(
        records_dir / "src_legacy123.md",
        {
            "source_id": "src_legacy123",
            "type": "document",
            "title": "Paper",
            "relative_path": "sources/paper.md",
            "content_hash": "abc123",
            "lifecycle_status": "available",
            "date_added": "2026-01-01T00:00:00+00:00",
            "last_seen_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:00+00:00",
        },
        "# Paper",
    )
    repo = ResearchRepository(tmp_path)

    report = repo.sync()
    record = next(item for item in repo.read_source_records()[0] if item.source_id == "src_legacy123")

    assert report.changed == 0
    assert record.content_size == document.stat().st_size
    assert record.content_mtime == document.stat().st_mtime
    assert record.lifecycle_status == "available"


def test_resync_stable_ids_changed_and_removed_documents(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    document = tmp_path / "sources" / "paper.md"
    document.write_text("first version", encoding="utf-8")
    repo = ResearchRepository(tmp_path)

    first = repo.sync()
    first_record = repo.read_source_records()[0][0]
    assert first.created == 1
    assert first_record.lifecycle_status == "available"

    document.write_text("second version", encoding="utf-8")
    second = repo.sync()
    second_record = repo.read_source_records()[0][0]
    assert second_record.source_id == first_record.source_id
    assert second_record.lifecycle_status == "changed"
    assert second.changed == 1

    document.unlink()
    third = repo.sync()
    assert third.removed == 1
    assert third.removed_sources[0].source_id == first_record.source_id
    assert not (tmp_path / "records" / "sources" / f"{first_record.source_id}.md").exists()
    assert repo.read_source_records()[0] == []


def test_removed_link_deletes_record_and_cascade_collaboration(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    write_users(tmp_path / "users.csv", [UserRecord(name="Ada", email="ada@example.com")])
    links_path = tmp_path / "links.csv"
    append_link(links_path, "https://example.com/research", "Example Research")
    repo = ResearchRepository(tmp_path)
    repo.sync()
    source = repo.read_source_records()[0][0]
    repo.write_comment(source.source_id, "ada@example.com", "Worth discussing.")
    repo.write_tag(source.source_id, "ada@example.com", "methods")

    links_path.write_text("url,title\n", encoding="utf-8")
    report = repo.sync()

    assert report.removed == 1
    assert report.removed_comments == 1
    assert report.removed_tags == 1
    assert not list((tmp_path / "records" / "sources").glob("src_*.md"))
    assert not list((tmp_path / "records" / "comments").glob("comment_*.md"))
    assert not list((tmp_path / "records" / "human-tags").glob("tag_*.md"))


def test_sync_report_lists_removed_source_details(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    append_link(tmp_path / "links.csv", "https://example.com/research", "Example Research")
    repo = ResearchRepository(tmp_path)
    repo.sync()
    (tmp_path / "links.csv").write_text("url,title\n", encoding="utf-8")

    report = repo.sync()

    assert report.removed == 1
    assert report.removed_sources[0].title == "Example Research"
    assert report.removed_sources[0].original_url == "https://example.com/research"


def test_links_human_comments_and_tags_stay_separate(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    write_users(tmp_path / "users.csv", [UserRecord(name="Ada", email="ada@example.com")])
    append_link(tmp_path / "links.csv", "https://example.com/research", "Example Research")
    repo = ResearchRepository(tmp_path)
    repo.sync()
    source = repo.read_source_records()[0][0]

    repo.write_comment(source.source_id, "ada@example.com", "Worth discussing.")
    repo.write_tag(source.source_id, "ada@example.com", "methods")

    links_text = (tmp_path / "links.csv").read_text(encoding="utf-8")
    source_text = (tmp_path / "records" / "sources" / f"{source.source_id}.md").read_text(encoding="utf-8")
    assert "Worth discussing" not in links_text
    assert "methods" not in links_text
    assert "Worth discussing" not in source_text
    assert "methods" not in source_text
    assert list((tmp_path / "records" / "comments").glob("comment_*.md"))
    assert list((tmp_path / "records" / "human-tags").glob("tag_*.md"))


def test_unsupported_document_is_reported_without_record(tmp_path: Path) -> None:
    manager = WorkspaceManager()
    manager.select(str(tmp_path))
    (tmp_path / "sources" / "archive.zip").write_text("zip-ish", encoding="utf-8")
    (tmp_path / "sources" / "photo.jpg").write_text("jpg-ish", encoding="utf-8")

    report = ResearchRepository(tmp_path).sync()

    assert report.invalid == 2
    assert [issue.code for issue in report.issues] == ["unsupported_document_type", "unsupported_document_type"]
    assert [issue.path for issue in report.issues] == ["sources/archive.zip", "sources/photo.jpg"]
    assert not list((tmp_path / "records" / "sources").glob("src_*.md"))

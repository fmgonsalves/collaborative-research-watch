from __future__ import annotations

from pathlib import Path

from research_watch.csv_store import append_link, read_links, read_users, write_users
from research_watch.markdown_store import read_markdown_record, write_markdown_record
from research_watch.models import UserRecord
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


def test_resync_stable_ids_changed_and_missing_documents(tmp_path: Path) -> None:
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
    third_record = repo.read_source_records()[0][0]
    assert third_record.source_id == first_record.source_id
    assert third_record.lifecycle_status == "missing"
    assert third.missing == 1


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

    report = ResearchRepository(tmp_path).sync()

    assert report.invalid == 1
    assert report.issues[0].code == "unsupported_document_type"
    assert not list((tmp_path / "records" / "sources").glob("src_*.md"))

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from research_watch.ai_generation import AIGenerationError, AIGenerationOutput
from research_watch.ai_store import ai_record_path, read_ai_record, write_ai_record
from research_watch.api import app, workspace
from research_watch.markdown_store import read_markdown_record, write_markdown_record
from research_watch.models import AIRecord, AISafeSourceInput, ExtractedSourceText, ExtractionResult


def client_for(tmp_path: Path) -> TestClient:
    workspace.current_path = None
    client = TestClient(app)
    response = client.post("/api/workspace/select", json={"path": str(tmp_path)})
    assert response.status_code == 200
    return client


def unselected_client() -> TestClient:
    workspace.current_path = None
    return TestClient(app)


def docx_bytes(paragraph_texts: list[str]) -> bytes:
    from io import BytesIO

    document = Document()
    for text in paragraph_texts:
        document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def test_bootstrap_upload_link_sync_and_detail_flow(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    user_response = client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    assert user_response.status_code == 200
    assert user_response.json()["email"] == "ada@example.com"

    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper\nUseful notes.", "text/markdown")},
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["saved"] == ["sources/paper.md"]

    link_response = client.post("/api/links", json={"url": "https://example.com/research", "title": "Example"})
    assert link_response.status_code == 200

    sources_response = client.get("/api/sources", params={"sort": "title"})
    assert sources_response.status_code == 200
    sources = sources_response.json()
    assert len(sources) == 2
    paper = next(source for source in sources if source["type"] == "document")
    assert paper["content_updated_at"] is not None
    assert paper["ai_generated_at"] is None

    comment_response = client.post(
        f"/api/sources/{paper['source_id']}/comments",
        json={"user_email": "ada@example.com", "body": "Read first."},
    )
    assert comment_response.status_code == 200

    tag_response = client.post(
        f"/api/sources/{paper['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "priority"},
    )
    assert tag_response.status_code == 200

    detail_response = client.get(f"/api/sources/{paper['source_id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["comment_count"] == 1
    assert detail["human_tags"] == ["priority"]
    assert detail["open_path"].replace("\\", "/").endswith("sources/paper.md")

    upload_sync = upload_response.json()["sync"]
    assert "removed" in upload_sync
    assert "renamed" in upload_sync
    assert upload_sync["removed"] == 0
    assert upload_sync["renamed"] == 0

    filtered_response = client.get("/api/sources", params={"search": "Read first", "tag": "priority"})
    assert filtered_response.status_code == 200
    assert len(filtered_response.json()) == 1

    index_text = (tmp_path / "index.md").read_text(encoding="utf-8")
    assert "Paper" in index_text
    assert "Human-created tags: priority" in index_text


def test_list_tags_returns_unique_labels_with_counts(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    client.post("/api/links", json={"url": "https://example.com/research", "title": "Example"})
    sources = client.get("/api/sources", params={"sort": "title"}).json()
    paper = next(source for source in sources if source["type"] == "document")
    link = next(source for source in sources if source["type"] == "link")

    empty_response = client.get("/api/tags")
    assert empty_response.status_code == 200
    assert empty_response.json() == []

    client.post(
        f"/api/sources/{paper['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "priority"},
    )
    client.post(
        f"/api/sources/{link['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "priority"},
    )
    client.post(
        f"/api/sources/{link['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "review"},
    )

    tags_response = client.get("/api/tags")
    assert tags_response.status_code == 200
    assert tags_response.json() == [
        {"tag": "priority", "count": 2},
        {"tag": "review", "count": 1},
    ]

    filtered_response = client.get("/api/tags", params={"q": "PRI"})
    assert filtered_response.status_code == 200
    assert filtered_response.json() == [{"tag": "priority", "count": 2}]


def test_source_detail_includes_ai_record_without_merging_human_tags(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]
    client.post(
        f"/api/sources/{source['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "priority"},
    )
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=source["source_id"],
            status="generated",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title=source["title"],
            source_type="document",
            ai_generated_tags=["methods", "summary"],
            summary="AI summary for the paper.",
            extractor="test-extractor",
            model="test-model",
        ),
    )

    detail_response = client.get(f"/api/sources/{source['source_id']}")
    summary_response = client.get("/api/sources")

    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["human_tags"] == ["priority"]
    assert [record["tag"] for record in detail["tag_records"]] == ["priority"]
    assert detail["ai"] == {
        "status": "generated",
        "generated_at": "2026-06-15T12:00:00+00:00",
        "ai_generated_tags": ["methods", "summary"],
        "summary": "AI summary for the paper.",
        "error_summary": None,
    }
    assert "extractor" not in detail["ai"]
    assert "model" not in detail["ai"]
    summary = summary_response.json()[0]
    assert summary["ai_status"] == "generated"
    assert summary["ai_generated_at"] == "2026-06-15T12:00:00+00:00"
    assert summary["ai_generated_tags"] == ["methods", "summary"]
    assert summary["ai_summary"] == "AI summary for the paper."
    assert "ai" not in summary


def test_source_summary_exposes_content_and_ai_generation_times_for_staleness(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=source["source_id"],
            status="generated",
            generated_at="2026-01-01T00:00:00+00:00",
            source_title=source["title"],
            source_type="document",
            ai_generated_tags=["methods"],
            summary="Older AI summary.",
        ),
    )

    (tmp_path / "sources" / "paper.md").write_text("# Paper\nUpdated content", encoding="utf-8")
    sync_response = client.post("/api/sync", json={})
    summary_response = client.get("/api/sources")
    detail_response = client.get(f"/api/sources/{source['source_id']}")

    assert sync_response.status_code == 200
    assert sync_response.json()["changed"] == 1
    summary = summary_response.json()[0]
    detail = detail_response.json()
    assert summary["content_updated_at"] is not None
    assert summary["ai_generated_at"] == "2026-01-01T00:00:00+00:00"
    assert detail["content_updated_at"] == summary["content_updated_at"]
    assert detail["ai_generated_at"] == "2026-01-01T00:00:00+00:00"


def test_sync_response_reports_hash_detected_rename(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]

    (tmp_path / "sources" / "paper.md").rename(tmp_path / "sources" / "renamed-paper.md")
    sync_response = client.post("/api/sync", json={})
    sources = client.get("/api/sources").json()

    assert sync_response.status_code == 200
    sync = sync_response.json()
    assert sync["renamed"] == 1
    assert sync["created"] == 0
    assert sync["removed"] == 0
    assert sync["renamed_sources"][0]["source_id"] == source["source_id"]
    assert sources[0]["source_id"] == source["source_id"]
    assert sources[0]["relative_path"] == "sources/renamed-paper.md"


def test_source_browse_search_and_filters_over_ai_fields_keep_human_tags_separate(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    client.post(
        "/api/sources/upload",
        files={"files": ("dataset.md", b"# Dataset", "text/markdown")},
    )
    sources = client.get("/api/sources", params={"sort": "title"}).json()
    dataset = next(source for source in sources if source["title"] == "Dataset")
    paper = next(source for source in sources if source["title"] == "Paper")
    client.post(
        f"/api/sources/{dataset['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "human-only"},
    )
    client.post(
        f"/api/sources/{paper['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "priority"},
    )
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=paper["source_id"],
            status="generated",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title=paper["title"],
            source_type="document",
            ai_generated_tags=["climate", "methods"],
            summary="Ocean evidence synthesis for coastal planning.",
            extractor="test-extractor",
            model="test-model",
        ),
    )
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=dataset["source_id"],
            status="generation_failed",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title=dataset["title"],
            source_type="document",
            error_summary="AI provider request failed.",
            extractor="test-extractor",
        ),
    )

    ai_summary_search = client.get("/api/sources", params={"search": "coastal planning"}).json()
    ai_tag_search = client.get("/api/sources", params={"search": "climate"}).json()
    human_filter = client.get("/api/sources", params={"tag": "climate"}).json()
    ai_filter = client.get("/api/sources", params={"ai_tag": "climate"}).json()
    human_only_filter = client.get("/api/sources", params={"tag": "human-only"}).json()
    ai_status_filter = client.get("/api/sources", params={"ai_status": "generation_failed"}).json()

    assert [source["source_id"] for source in ai_summary_search] == [paper["source_id"]]
    assert [source["source_id"] for source in ai_tag_search] == [paper["source_id"]]
    assert human_filter == []
    assert [source["source_id"] for source in ai_filter] == [paper["source_id"]]
    assert [source["source_id"] for source in human_only_filter] == [dataset["source_id"]]
    assert [source["source_id"] for source in ai_status_filter] == [dataset["source_id"]]
    assert ai_filter[0]["human_tags"] == ["priority"]
    assert ai_filter[0]["ai_generated_tags"] == ["climate", "methods"]
    assert ai_filter[0]["ai_status"] == "generated"


def test_ai_tag_suggestions_count_only_ai_generated_tags(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    client.post(
        "/api/sources/upload",
        files={"files": ("dataset.md", b"# Dataset", "text/markdown")},
    )
    sources = client.get("/api/sources", params={"sort": "title"}).json()
    dataset = next(source for source in sources if source["title"] == "Dataset")
    paper = next(source for source in sources if source["title"] == "Paper")
    client.post(
        f"/api/sources/{dataset['source_id']}/tags",
        json={"user_email": "ada@example.com", "tag": "climate"},
    )
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=paper["source_id"],
            status="generated",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title=paper["title"],
            source_type="document",
            ai_generated_tags=["climate", "methods"],
            summary="AI summary.",
            extractor="test-extractor",
            model="test-model",
        ),
    )
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=dataset["source_id"],
            status="generated",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title=dataset["title"],
            source_type="document",
            ai_generated_tags=["methods"],
            summary="AI summary.",
            extractor="test-extractor",
            model="test-model",
        ),
    )

    ai_tags_response = client.get("/api/ai-tags")
    human_tags_response = client.get("/api/tags")

    assert ai_tags_response.status_code == 200
    assert ai_tags_response.json() == [
        {"tag": "climate", "count": 1},
        {"tag": "methods", "count": 2},
    ]
    assert human_tags_response.json() == [{"tag": "climate", "count": 1}]


def test_malformed_ai_record_does_not_crash_source_browse(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]
    write_markdown_record(
        ai_record_path(tmp_path, source["source_id"]),
        {
            "source_id": source["source_id"],
            "status": "not-valid",
            "generated_at": "2026-06-15T12:00:00+00:00",
            "source_title": source["title"],
            "source_type": "document",
        },
        "Summary",
    )

    with caplog.at_level(logging.WARNING, logger="research_watch.sync"):
        response = client.get("/api/sources")

    assert response.status_code == 200
    assert response.json()[0]["ai_status"] is None
    assert response.json()[0]["ai_generated_tags"] == []
    assert response.json()[0]["ai_summary"] == ""
    assert "invalid_ai_record" in caplog.text


def test_source_detail_includes_ai_failure_status_and_safe_error(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]
    write_ai_record(
        tmp_path,
        AIRecord(
            source_id=source["source_id"],
            status="extraction_failed",
            generated_at="2026-06-15T12:00:00+00:00",
            source_title=source["title"],
            source_type="document",
            error_summary="Could not extract readable text.",
            extractor="test-extractor",
        ),
    )

    detail_response = client.get(f"/api/sources/{source['source_id']}")

    assert detail_response.status_code == 200
    assert detail_response.json()["ai"] == {
        "status": "extraction_failed",
        "generated_at": "2026-06-15T12:00:00+00:00",
        "ai_generated_tags": [],
        "summary": "",
        "error_summary": "Could not extract readable text.",
    }


def test_source_detail_returns_null_ai_when_record_is_missing(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]

    detail_response = client.get(f"/api/sources/{source['source_id']}")

    assert detail_response.status_code == 200
    assert detail_response.json()["ai"] is None


def test_workspace_required_api_returns_controlled_errors_without_selection() -> None:
    client = unselected_client()

    responses = [
        client.get("/api/users"),
        client.post("/api/sync", json={}),
        client.get("/api/sources"),
        client.get("/api/tags"),
        client.post("/api/links", json={"url": "https://example.com/research", "title": "Example"}),
    ]

    assert [response.status_code for response in responses] == [400, 400, 400, 400, 400]
    assert all("Workspace has not been selected." in response.text for response in responses)


def test_unknown_source_comment_and_tag_requests_do_not_create_orphans(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada", "email": "ada@example.com"})

    detail_response = client.get("/api/sources/src_missing")
    assert detail_response.status_code == 404

    comment_response = client.post(
        "/api/sources/src_missing/comments",
        json={"user_email": "ada@example.com", "body": "This should not be orphaned."},
    )
    assert comment_response.status_code == 404

    tag_response = client.post(
        "/api/sources/src_missing/tags",
        json={"user_email": "ada@example.com", "tag": "orphan"},
    )
    assert tag_response.status_code == 404

    assert not list((tmp_path / "records" / "comments").glob("comment_*.md"))
    assert not list((tmp_path / "records" / "human-tags").glob("tag_*.md"))


def test_unknown_comment_and_tag_updates_return_404(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    comment_response = client.put(
        "/api/comments/comment_missing",
        json={"user_email": "ada@example.com", "body": "Updated."},
    )
    assert comment_response.status_code == 404

    tag_response = client.put(
        "/api/tags/tag_missing",
        json={"user_email": "ada@example.com", "tag": "updated"},
    )
    assert tag_response.status_code == 404


def test_invalid_users_csv_is_reported_by_api(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    (tmp_path / "users.csv").write_text("email,name\nada@example.com,Ada\n", encoding="utf-8")

    users_response = client.get("/api/users")
    assert users_response.status_code == 400
    assert users_response.json()["detail"][0]["code"] == "invalid_users_header"

    status_response = client.get("/api/workspace/status")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["has_users"] is False
    assert status["issues"][0]["code"] == "invalid_users_header"


def test_upload_rejects_unsupported_files_without_source_records(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    response = client.post(
        "/api/sources/upload",
        files=[
            ("files", ("paper.md", b"# Paper", "text/markdown")),
            ("files", ("payload.exe", b"not a supported document", "application/octet-stream")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    assert body["saved"] == ["sources/paper.md"]
    assert body["rejected"] == ["payload.exe"]
    assert (tmp_path / "sources" / "paper.md").exists()
    assert not (tmp_path / "sources" / "payload.exe").exists()
    assert body["sync"]["sources_total"] == 1


def test_invalid_request_payloads_return_validation_errors(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    invalid_link_response = client.post("/api/links", json={"url": "not a url", "title": "Bad"})
    assert invalid_link_response.status_code == 422

    empty_user_response = client.post("/api/users/bootstrap", json={"name": " ", "email": " "})
    assert empty_user_response.status_code == 400


def test_enrich_unknown_source_returns_404(tmp_path: Path) -> None:
    client = client_for(tmp_path)

    response = client.post("/api/sources/src_missing/ai/enrich")

    assert response.status_code == 404
    assert response.json()["detail"] == "Source not found."


def test_enrich_link_source_writes_generated_ai_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_fetch(source: object) -> ExtractionResult:
        return ExtractionResult(
            source_id=source.source_id,
            extracted=ExtractedSourceText(source_id=source.source_id, content_text="Fetched public link text."),
            extractor="html",
        )

    def fake_generator(source_input: AISafeSourceInput) -> AIGenerationOutput:
        assert source_input.source_type == "link"
        assert source_input.original_url == "https://example.com/research"
        assert source_input.filename is None
        assert source_input.content_text == "Fetched public link text."
        return AIGenerationOutput(
            summary="Mocked link summary.",
            ai_generated_tags=["link", "research", "public"],
            model="test-model",
        )

    monkeypatch.setattr("research_watch.sync.fetch_link_text", fake_fetch)
    monkeypatch.setattr("research_watch.sync.generate_with_openai", fake_generator)
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada Confidential", "email": "ada.secret@example.com"})
    link_response = client.post("/api/links", json={"url": "https://example.com/research", "title": "Example"})
    assert link_response.status_code == 200
    source = client.get("/api/sources").json()[0]
    client.post(
        f"/api/sources/{source['source_id']}/comments",
        json={"user_email": "ada.secret@example.com", "body": "Do not send this link note."},
    )
    client.post(
        f"/api/sources/{source['source_id']}/tags",
        json={"user_email": "ada.secret@example.com", "tag": "human-link-secret"},
    )

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert issues == []
    assert ai_record is not None
    assert ai_record.status == "generated"
    assert ai_record.source_type == "link"
    assert ai_record.summary == "Mocked link summary."
    assert ai_record.ai_generated_tags == ["link", "research", "public"]
    assert ai_record.extractor == "html"
    assert ai_record.model == "test-model"
    serialized = ai_record.model_dump_json()
    assert "Do not send this link note" not in serialized
    assert "human-link-secret" not in serialized
    assert "Ada Confidential" not in serialized
    assert "ada.secret@example.com" not in serialized


def test_enrich_link_fetch_failure_writes_safe_failure_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing_fetch(source: object) -> ExtractionResult:
        return ExtractionResult(
            source_id=source.source_id,
            error_summary="Link is blocked or inaccessible.",
            diagnostics="HTTP status 403",
            extractor="html",
        )

    monkeypatch.setattr("research_watch.sync.fetch_link_text", failing_fetch)
    client = client_for(tmp_path)
    link_response = client.post("/api/links", json={"url": "https://example.com/research", "title": "Example"})
    assert link_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "fetch_failed"
    assert response.json()["error_summary"] == "Link is blocked or inaccessible."
    assert issues == []
    assert ai_record is not None
    assert ai_record.status == "fetch_failed"
    assert ai_record.source_type == "link"
    assert ai_record.summary == ""
    assert ai_record.error_summary == "Link is blocked or inaccessible."
    assert ai_record.extractor == "html"
    assert "HTTP status 403" not in ai_record.model_dump_json()


def test_enrich_document_source_writes_generated_ai_record_and_detail_loads_it(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generator(_source_input: AISafeSourceInput) -> AIGenerationOutput:
        return AIGenerationOutput(
            summary="Mocked real model summary.",
            ai_generated_tags=["methods", "research", "document"],
            model="test-model",
        )

    monkeypatch.setattr("research_watch.sync.generate_with_openai", fake_generator)
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper\nSource text.", "text/markdown")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    detail_response = client.get(f"/api/sources/{source['source_id']}")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert issues == []
    assert ai_record is not None
    assert ai_record.status == "generated"
    assert ai_record.ai_generated_tags == ["methods", "research", "document"]
    assert ai_record.summary == "Mocked real model summary."
    assert ai_record.extractor == "simple-text"
    assert ai_record.model == "test-model"
    assert detail_response.json()["ai"] == response.json()


def test_enrich_docx_document_source_writes_generated_ai_record(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generator(source_input: AISafeSourceInput) -> AIGenerationOutput:
        assert source_input.filename == "brief.docx"
        assert source_input.content_text == "First DOCX paragraph\n\nSecond DOCX paragraph"
        return AIGenerationOutput(
            summary="Mocked DOCX summary.",
            ai_generated_tags=["docx", "research", "document"],
            model="test-model",
        )

    monkeypatch.setattr("research_watch.sync.generate_with_openai", fake_generator)
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={
            "files": (
                "brief.docx",
                docx_bytes(["First DOCX paragraph", "", "Second DOCX paragraph"]),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert issues == []
    assert ai_record is not None
    assert ai_record.status == "generated"
    assert ai_record.summary == "Mocked DOCX summary."
    assert ai_record.ai_generated_tags == ["docx", "research", "document"]
    assert ai_record.extractor == "python-docx"
    assert ai_record.model == "test-model"


def test_enrich_document_extraction_failure_writes_safe_failure_record(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("notes.txt", b"\xff", "text/plain")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "extraction_failed"
    assert response.json()["error_summary"] == "Could not decode source text as UTF-8."
    assert issues == []
    assert ai_record is not None
    assert ai_record.summary == ""
    assert ai_record.error_summary == "Could not decode source text as UTF-8."
    assert "UnicodeDecodeError" not in ai_record.model_dump_json()


def test_enrich_document_with_unsafe_or_missing_path_fails_without_exposing_local_path(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]
    record_path = tmp_path / "records" / "sources" / f"{source['source_id']}.md"
    frontmatter, body = read_markdown_record(record_path)
    frontmatter["relative_path"] = "../outside.md"
    write_markdown_record(record_path, frontmatter, body)

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "extraction_failed"
    assert response.json()["error_summary"] == "Source file is not available for extraction."
    assert issues == []
    assert ai_record is not None
    serialized = ai_record.model_dump_json()
    assert str(tmp_path) not in serialized
    assert "outside.md" not in serialized


def test_enrich_document_does_not_include_human_collaboration_data(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_generator(_source_input: AISafeSourceInput) -> AIGenerationOutput:
        return AIGenerationOutput(
            summary="Mocked real model summary.",
            ai_generated_tags=["methods", "research", "document"],
            model="test-model",
        )

    monkeypatch.setattr("research_watch.sync.generate_with_openai", fake_generator)
    client = client_for(tmp_path)
    client.post("/api/users/bootstrap", json={"name": "Ada Confidential", "email": "ada.secret@example.com"})
    client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper\nOnly source content.", "text/markdown")},
    )
    source = client.get("/api/sources").json()[0]
    client.post(
        f"/api/sources/{source['source_id']}/comments",
        json={"user_email": "ada.secret@example.com", "body": "Do not send this human note."},
    )
    client.post(
        f"/api/sources/{source['source_id']}/tags",
        json={"user_email": "ada.secret@example.com", "tag": "human-secret-tag"},
    )

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, _ = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert ai_record is not None
    serialized = ai_record.model_dump_json()
    assert "Do not send this human note" not in serialized
    assert "human-secret-tag" not in serialized
    assert "Ada Confidential" not in serialized
    assert "ada.secret@example.com" not in serialized


def test_enrich_document_missing_ai_config_returns_safe_error_without_writing_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("RESEARCH_WATCH_OPENAI_MODEL", raising=False)
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper\nSource text.", "text/markdown")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")

    assert response.status_code == 503
    assert response.json()["detail"] == "AI generation is not configured. Missing: OPENAI_API_KEY, RESEARCH_WATCH_OPENAI_MODEL."
    assert not ai_record_path(tmp_path, source["source_id"]).exists()


def test_enrich_document_provider_failure_writes_generation_failed_when_no_prior_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failing_generator(_source_input: AISafeSourceInput) -> AIGenerationOutput:
        raise AIGenerationError("AI provider request failed.")

    monkeypatch.setattr("research_watch.sync.generate_with_openai", failing_generator)
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper\nSource text.", "text/markdown")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    with caplog.at_level(logging.WARNING, logger="research_watch.sync"):
        response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 200
    assert response.json()["status"] == "generation_failed"
    assert response.json()["error_summary"] == "AI provider request failed."
    assert issues == []
    assert ai_record is not None
    assert ai_record.status == "generation_failed"
    assert ai_record.summary == ""
    assert ai_record.error_summary == "AI provider request failed."
    assert "writing_status=generation_failed" in caplog.text
    assert source["source_id"] in caplog.text


def test_enrich_document_provider_failure_preserves_existing_generated_record(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    def failing_generator(_source_input: AISafeSourceInput) -> AIGenerationOutput:
        raise AIGenerationError("AI provider request failed.")

    monkeypatch.setattr("research_watch.sync.generate_with_openai", failing_generator)
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper\nSource text.", "text/markdown")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]
    existing = AIRecord(
        source_id=source["source_id"],
        status="generated",
        generated_at="2026-06-15T12:00:00+00:00",
        source_title=source["title"],
        source_type="document",
        ai_generated_tags=["existing", "record", "preserved"],
        summary="Existing paid-for summary.",
        extractor="simple-text",
        model="previous-model",
    )
    write_ai_record(tmp_path, existing)

    with caplog.at_level(logging.WARNING, logger="research_watch.sync"):
        response = client.post(f"/api/sources/{source['source_id']}/ai/enrich")
    ai_record, issues = read_ai_record(tmp_path, source["source_id"])

    assert response.status_code == 502
    assert response.json()["detail"] == "AI provider request failed."
    assert issues == []
    assert ai_record == existing
    assert "existing_record=preserved" in caplog.text
    assert source["source_id"] in caplog.text


def test_manual_sync_does_not_create_ai_records(tmp_path: Path) -> None:
    client = client_for(tmp_path)
    upload_response = client.post(
        "/api/sources/upload",
        files={"files": ("paper.md", b"# Paper", "text/markdown")},
    )
    assert upload_response.status_code == 200
    source = client.get("/api/sources").json()[0]

    sync_response = client.post("/api/sync")

    assert sync_response.status_code == 200
    assert not ai_record_path(tmp_path, source["source_id"]).exists()

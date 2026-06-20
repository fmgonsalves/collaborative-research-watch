from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_watch.ai_store import write_ai_record
from research_watch.api import app, workspace
from research_watch.models import AIRecord


def client_for(tmp_path: Path) -> TestClient:
    workspace.current_path = None
    client = TestClient(app)
    response = client.post("/api/workspace/select", json={"path": str(tmp_path)})
    assert response.status_code == 200
    return client


def unselected_client() -> TestClient:
    workspace.current_path = None
    return TestClient(app)


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
    assert upload_sync["removed"] == 0

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
    assert "ai" not in summary_response.json()[0]


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

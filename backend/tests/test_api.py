from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from research_watch.api import app, workspace


def client_for(tmp_path: Path) -> TestClient:
    workspace.current_path = None
    client = TestClient(app)
    response = client.post("/api/workspace/select", json={"path": str(tmp_path)})
    assert response.status_code == 200
    return client


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

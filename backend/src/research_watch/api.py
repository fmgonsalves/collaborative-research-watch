from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .csv_store import append_link, read_users
from .logging_config import configure_logging
from .models import (
    BootstrapUserRequest,
    CommentCreateRequest,
    CommentRecord,
    CommentUpdateRequest,
    HumanTagRecord,
    LinkCreateRequest,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    SourceDetail,
    SourceAIEnrichment,
    SourceSummary,
    SyncReport,
    TagCreateRequest,
    TagSuggestion,
    TagUpdateRequest,
    UserRecord,
    WorkspaceSelectRequest,
    WorkspaceState,
)
from .sync import ResearchRepository
from .workspace import WorkspaceManager

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title="Collaborative Research Watch")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
workspace = WorkspaceManager()


def repo() -> ResearchRepository:
    try:
        return ResearchRepository(workspace.require())
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def require_workspace_path() -> Path:
    try:
        return workspace.require()
    except RuntimeError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


def require_source(repository: ResearchRepository, source_id: str) -> SourceDetail:
    detail = repository.detail(source_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    return detail


@app.post("/api/workspace/select", response_model=WorkspaceState)
def select_workspace(request: WorkspaceSelectRequest) -> WorkspaceState:
    return workspace.select(request.path)


@app.get("/api/workspace/status", response_model=WorkspaceState)
def workspace_status() -> WorkspaceState:
    return workspace.status()


@app.post("/api/users/bootstrap", response_model=UserRecord)
def bootstrap_user(request: BootstrapUserRequest) -> UserRecord:
    try:
        return workspace.bootstrap_user(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/users", response_model=list[UserRecord])
def list_users() -> list[UserRecord]:
    users, issues = read_users(require_workspace_path() / "users.csv")
    if issues:
        raise HTTPException(status_code=400, detail=[issue.model_dump() for issue in issues])
    return users


@app.post("/api/sync", response_model=SyncReport)
def sync_workspace() -> SyncReport:
    logger.info("POST /api/sync received")
    report = repo().sync()
    logger.info(
        "POST /api/sync completed total=%d created=%d changed=%d removed=%d",
        report.sources_total,
        report.created,
        report.changed,
        report.removed,
    )
    return report


@app.get("/api/sources", response_model=list[SourceSummary])
def list_sources(search: str = "", type: str = "", status: str = "", tag: str = "", sort: str = "title") -> list[SourceSummary]:
    return repo().summaries(search=search, type_filter=type, status=status, tag=tag, sort=sort)


@app.get("/api/sources/{source_id}", response_model=SourceDetail)
def source_detail(source_id: str) -> SourceDetail:
    return require_source(repo(), source_id)


@app.post("/api/sources/{source_id}/ai/enrich", response_model=SourceAIEnrichment)
def enrich_source(source_id: str) -> SourceAIEnrichment:
    repository = repo()
    source = repository.source_record(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found.")
    if source.type == "link":
        raise HTTPException(status_code=409, detail="Link enrichment is not available until link fetching is implemented.")
    return repository.enrich_document_source(source)


@app.post("/api/sources/upload")
async def upload_sources(files: list[UploadFile] = File(...)) -> dict[str, object]:
    root = workspace.require()
    destination = root / "sources"
    destination.mkdir(parents=True, exist_ok=True)
    saved: list[str] = []
    rejected: list[str] = []
    for upload in files:
        filename = Path(upload.filename or "").name
        if not filename or Path(filename).suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
            rejected.append(filename or "(unnamed)")
            continue
        target = destination / filename
        with target.open("wb") as handle:
            shutil.copyfileobj(upload.file, handle)
        saved.append(f"sources/{filename}")
        logger.info("Uploaded %s (%d bytes)", filename, target.stat().st_size)
    logger.info("Starting sync after upload of %d file(s)", len(saved))
    report = repo().sync()
    return {"saved": saved, "rejected": rejected, "sync": report.model_dump()}


@app.post("/api/links")
def create_link(request: LinkCreateRequest) -> dict[str, object]:
    root = require_workspace_path()
    append_link(root / "links.csv", str(request.url), request.title or "")
    logger.info("Link added url=%s starting sync", request.url)
    report = repo().sync()
    return {"sync": report.model_dump()}


@app.post("/api/sources/{source_id}/comments", response_model=CommentRecord)
def create_comment(source_id: str, request: CommentCreateRequest) -> CommentRecord:
    repository = repo()
    require_source(repository, source_id)
    logger.info("Comment create on source=%s triggers full sync", source_id)
    return repository.write_comment(source_id, request.user_email, request.body)


@app.put("/api/comments/{comment_id}", response_model=CommentRecord)
def update_comment(comment_id: str, request: CommentUpdateRequest) -> CommentRecord:
    comments, _ = repo().read_comments()
    existing = next((comment for comment in comments if comment.comment_id == comment_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Comment not found.")
    logger.info("Comment update comment=%s triggers full sync", comment_id)
    return repo().write_comment(existing.source_id, request.user_email, request.body, existing_id=comment_id)


@app.post("/api/sources/{source_id}/tags", response_model=HumanTagRecord)
def create_tag(source_id: str, request: TagCreateRequest) -> HumanTagRecord:
    repository = repo()
    require_source(repository, source_id)
    logger.info("Tag create on source=%s triggers full sync", source_id)
    return repository.write_tag(source_id, request.user_email, request.tag)


@app.get("/api/tags", response_model=list[TagSuggestion])
def list_tags(q: str = "", limit: int = 50) -> list[TagSuggestion]:
    return repo().list_tag_suggestions(q=q, limit=limit)


@app.put("/api/tags/{tag_id}", response_model=HumanTagRecord)
def update_tag(tag_id: str, request: TagUpdateRequest) -> HumanTagRecord:
    tags, _ = repo().read_tags()
    existing = next((tag for tag in tags if tag.tag_id == tag_id), None)
    if existing is None:
        raise HTTPException(status_code=404, detail="Tag not found.")
    logger.info("Tag update tag=%s triggers full sync", tag_id)
    return repo().write_tag(existing.source_id, request.user_email, request.tag, existing_id=tag_id)

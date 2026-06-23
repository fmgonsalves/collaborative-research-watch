from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl


SUPPORTED_DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".csv"} #TODO: add this to the Readme


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ValidationIssue(BaseModel):
    code: str
    message: str
    path: str | None = None


class UserRecord(BaseModel):
    name: str
    email: str

#TODO: not a very good way of modeling this - too many optionals here. Maybe break down into generic SourceRecord and implementations for filesystem docs and links
class SourceRecord(BaseModel):
    source_id: str
    type: Literal["document", "link"]
    title: str
    lifecycle_status: str = "available" #TODO: check if lifecycle status can take other values now or in the future; either remove the property or use an enumerated or Literal to represent possible values
    date_added: str
    last_seen_at: str #TODO: not required, remove
    updated_at: str
    relative_path: str | None = None
    original_url: str | None = None
    content_size: int | None = None
    content_mtime: float | None = None


class CommentRecord(BaseModel):
    comment_id: str
    source_id: str
    user_email: str
    created_at: str
    updated_at: str
    body: str


class HumanTagRecord(BaseModel):
    tag_id: str
    source_id: str
    user_email: str
    tag: str
    created_at: str
    updated_at: str


class SourceSummary(BaseModel):
    source_id: str
    type: str
    title: str
    lifecycle_status: str
    date_added: str
    updated_at: str
    relative_path: str | None = None
    original_url: str | None = None
    human_tags: list[str] = Field(default_factory=list)
    comment_count: int = 0


class SourceDetail(SourceSummary):
    open_url: str | None = None
    open_path: str | None = None
    comments: list[CommentRecord] = Field(default_factory=list)
    tag_records: list[HumanTagRecord] = Field(default_factory=list)


class WorkspaceState(BaseModel):
    path: str | None = None
    initialized: bool = False
    has_users: bool = False
    users: list[UserRecord] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class SyncSourceEvent(BaseModel):
    source_id: str
    title: str
    type: Literal["document", "link"]
    relative_path: str | None = None
    original_url: str | None = None


class SyncReport(BaseModel):
    workspace_path: str
    sources_total: int
    created: int = 0
    updated: int = 0
    changed: int = 0
    removed: int = 0
    removed_comments: int = 0
    removed_tags: int = 0
    invalid: int = 0
    created_sources: list[SyncSourceEvent] = Field(default_factory=list)
    changed_sources: list[SyncSourceEvent] = Field(default_factory=list)
    updated_sources: list[SyncSourceEvent] = Field(default_factory=list)
    removed_sources: list[SyncSourceEvent] = Field(default_factory=list)
    issues: list[ValidationIssue] = Field(default_factory=list)


class WorkspaceSelectRequest(BaseModel):
    path: str


class BootstrapUserRequest(BaseModel):
    name: str
    email: str


class LinkCreateRequest(BaseModel):
    url: HttpUrl
    title: str | None = None


class CommentCreateRequest(BaseModel):
    user_email: str
    body: str


class CommentUpdateRequest(BaseModel):
    user_email: str
    body: str


class TagCreateRequest(BaseModel):
    user_email: str
    tag: str


class TagUpdateRequest(BaseModel):
    user_email: str
    tag: str


class TagSuggestion(BaseModel):
    tag: str
    count: int

# TODO: is this the right place to have this function
def display_title_for_path(path: Path) -> str:
    title = path.stem.replace("_", " ").replace("-", " ").strip()
    return title.title() if title else path.name

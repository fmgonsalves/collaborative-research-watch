from __future__ import annotations

import hashlib
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic import ValidationError

from .csv_store import read_links, read_users
from .markdown_store import read_markdown_record, write_markdown_record
from .models import (
    CommentRecord,
    HumanTagRecord,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    SourceDetail,
    SourceRecord,
    SourceSummary,
    SyncReport,
    ValidationIssue,
    display_title_for_path,
    utc_now,
)


def source_id() -> str:
    return f"src_{uuid.uuid4().hex[:12]}"


def comment_id() -> str:
    return f"comment_{uuid.uuid4().hex[:12]}"


def tag_id() -> str:
    return f"tag_{uuid.uuid4().hex[:12]}"


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path.rstrip("/") or "/"
    return urlunparse((scheme, netloc, path, "", parsed.query, ""))


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ResearchRepository:
    def __init__(self, root: Path) -> None:
        self.root = root

    @property
    def sources_dir(self) -> Path:
        return self.root / "sources"

    @property
    def source_records_dir(self) -> Path:
        return self.root / "records" / "sources"

    @property
    def comments_dir(self) -> Path:
        return self.root / "records" / "comments"

    @property
    def tags_dir(self) -> Path:
        return self.root / "records" / "human-tags"

    def read_source_records(self) -> tuple[list[SourceRecord], list[ValidationIssue]]:
        records: list[SourceRecord] = []
        issues: list[ValidationIssue] = []
        for path in sorted(self.source_records_dir.glob("src_*.md")):
            frontmatter, _ = read_markdown_record(path)
            try:
                records.append(SourceRecord.model_validate(frontmatter))
            except ValidationError as error:
                issues.append(
                    ValidationIssue(
                        code="invalid_source_record",
                        message=str(error),
                        path=str(path),
                    )
                )
        return records, issues

    def write_source_record(self, record: SourceRecord) -> None:
        body_lines = [f"# {record.title}", "", f"- Type: {record.type}", f"- Status: {record.lifecycle_status}"]
        if record.relative_path:
            body_lines.append(f"- Path: {record.relative_path}")
        if record.original_url:
            body_lines.append(f"- URL: {record.original_url}")
        write_markdown_record(
            self.source_records_dir / f"{record.source_id}.md",
            record.model_dump(exclude_none=True),
            "\n".join(body_lines),
        )

    def read_comments(self) -> tuple[list[CommentRecord], list[ValidationIssue]]:
        comments: list[CommentRecord] = []
        issues: list[ValidationIssue] = []
        for path in sorted(self.comments_dir.glob("comment_*.md")):
            frontmatter, body = read_markdown_record(path)
            try:
                comments.append(CommentRecord.model_validate({**frontmatter, "body": body.strip()}))
            except ValidationError as error:
                issues.append(ValidationIssue(code="invalid_comment_record", message=str(error), path=str(path)))
        return comments, issues

    def read_tags(self) -> tuple[list[HumanTagRecord], list[ValidationIssue]]:
        tags: list[HumanTagRecord] = []
        issues: list[ValidationIssue] = []
        for path in sorted(self.tags_dir.glob("tag_*.md")):
            frontmatter, _ = read_markdown_record(path)
            try:
                tags.append(HumanTagRecord.model_validate(frontmatter))
            except ValidationError as error:
                issues.append(ValidationIssue(code="invalid_tag_record", message=str(error), path=str(path)))
        return tags, issues

    def sync(self) -> SyncReport:
        now = utc_now()
        existing, record_issues = self.read_source_records()
        by_path = {record.relative_path: record for record in existing if record.type == "document" and record.relative_path}
        by_url = {
            normalize_url(record.original_url): record
            for record in existing
            if record.type == "link" and record.original_url
        }
        seen_ids: set[str] = set()
        report = SyncReport(workspace_path=str(self.root), sources_total=0, issues=record_issues)

        self.sources_dir.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.sources_dir.rglob("*")):
            if not path.is_file() or any(part.startswith(".") for part in path.relative_to(self.sources_dir).parts):
                continue
            relative_path = path.relative_to(self.root).as_posix()
            if path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
                report.invalid += 1
                report.issues.append(
                    ValidationIssue(
                        code="unsupported_document_type",
                        message=f"Unsupported document extension: {path.suffix or '(none)'}.",
                        path=relative_path,
                    )
                )
                continue
            content_hash = hash_file(path)
            record = by_path.get(relative_path)
            if record is None:
                record = SourceRecord(
                    source_id=source_id(),
                    type="document",
                    title=display_title_for_path(path),
                    relative_path=relative_path,
                    content_hash=content_hash,
                    date_added=now,
                    last_seen_at=now,
                    updated_at=now,
                    lifecycle_status="available",
                )
                report.created += 1
            else:
                record.last_seen_at = now
                record.updated_at = now
                if record.content_hash and record.content_hash != content_hash:
                    record.lifecycle_status = "changed"
                    report.changed += 1
                elif record.lifecycle_status == "missing":
                    record.lifecycle_status = "available"
                    report.updated += 1
                record.content_hash = content_hash
            seen_ids.add(record.source_id)
            self.write_source_record(record)

        links, link_issues = read_links(self.root / "links.csv")
        report.issues.extend(link_issues)
        seen_urls: set[str] = set()
        for row in links:
            normalized = normalize_url(row["url"])
            if normalized in seen_urls:
                report.invalid += 1
                report.issues.append(
                    ValidationIssue(code="duplicate_link_url", message=f"Duplicate link URL: {row['url']}.", path="links.csv")
                )
                continue
            seen_urls.add(normalized)
            record = by_url.get(normalized)
            if record is None:
                title = row["title"] or normalized
                record = SourceRecord(
                    source_id=source_id(),
                    type="link",
                    title=title,
                    original_url=normalized,
                    date_added=now,
                    last_seen_at=now,
                    updated_at=now,
                    lifecycle_status="available",
                )
                report.created += 1
            else:
                record.last_seen_at = now
                record.updated_at = now
                if row["title"] and row["title"] != record.title:
                    record.title = row["title"]
                    report.updated += 1
                if record.lifecycle_status == "missing":
                    record.lifecycle_status = "available"
                    report.updated += 1
            seen_ids.add(record.source_id)
            self.write_source_record(record)

        for record in existing:
            if record.source_id in seen_ids:
                continue
            if record.lifecycle_status != "missing":
                record.lifecycle_status = "missing"
                record.updated_at = now
                record.last_seen_at = now
                self.write_source_record(record)
                report.missing += 1

        users, user_issues = read_users(self.root / "users.csv")
        report.issues.extend(user_issues)
        all_records, source_issues = self.read_source_records()
        report.issues.extend(source_issues)
        self.write_index(all_records, users)
        report.sources_total = len(all_records)
        return report

    def write_index(self, records: list[SourceRecord], users: object) -> None:
        comments, _ = self.read_comments()
        tags, _ = self.read_tags()
        comments_by_source = defaultdict(list)
        tags_by_source = defaultdict(list)
        for comment in comments:
            comments_by_source[comment.source_id].append(comment)
        for tag in tags:
            tags_by_source[tag.source_id].append(tag)
        lines = ["# Collaborative Research Watch Index", "", "This catalog is generated by the app.", "", "## Sources", ""]
        for record in sorted(records, key=lambda item: item.title.lower()):
            target = record.original_url or record.relative_path or ""
            lines.append(f"### {record.title}")
            lines.append("")
            lines.append(f"- ID: `{record.source_id}`")
            lines.append(f"- Type: {record.type}")
            lines.append(f"- Status: {record.lifecycle_status}")
            if target:
                lines.append(f"- Source: {target}")
            source_tags = sorted({tag.tag for tag in tags_by_source[record.source_id]})
            if source_tags:
                lines.append(f"- Human-created tags: {', '.join(source_tags)}")
            if comments_by_source[record.source_id]:
                lines.append(f"- Comments: {len(comments_by_source[record.source_id])}")
            lines.append("")
        self.root.joinpath("index.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    def summaries(self, search: str = "", type_filter: str = "", status: str = "", tag: str = "", sort: str = "title") -> list[SourceSummary]:
        records, _ = self.read_source_records()
        comments, _ = self.read_comments()
        tags, _ = self.read_tags()
        comments_by_source = defaultdict(list)
        tags_by_source = defaultdict(list)
        for comment in comments:
            comments_by_source[comment.source_id].append(comment)
        for tag_record in tags:
            tags_by_source[tag_record.source_id].append(tag_record)
        rows: list[SourceSummary] = []
        search_lower = search.lower().strip()
        for record in records:
            human_tags = sorted({tag_record.tag for tag_record in tags_by_source[record.source_id]})
            comment_text = " ".join(comment.body for comment in comments_by_source[record.source_id])
            haystack = " ".join([record.title, record.type, record.lifecycle_status, record.original_url or "", record.relative_path or "", " ".join(human_tags), comment_text]).lower()
            if search_lower and search_lower not in haystack:
                continue
            if type_filter and record.type != type_filter:
                continue
            if status and record.lifecycle_status != status:
                continue
            if tag and tag not in human_tags:
                continue
            rows.append(
                SourceSummary(
                    source_id=record.source_id,
                    type=record.type,
                    title=record.title,
                    lifecycle_status=record.lifecycle_status,
                    date_added=record.date_added,
                    updated_at=record.updated_at,
                    relative_path=record.relative_path,
                    original_url=record.original_url,
                    human_tags=human_tags,
                    comment_count=len(comments_by_source[record.source_id]),
                )
            )
        key_map = {
            "title": lambda item: item.title.lower(),
            "date_added": lambda item: item.date_added,
            "status": lambda item: item.lifecycle_status,
            "recently_updated": lambda item: item.updated_at,
        }
        reverse = sort in {"date_added", "recently_updated"}
        return sorted(rows, key=key_map.get(sort, key_map["title"]), reverse=reverse)

    def detail(self, source_id_value: str) -> SourceDetail | None:
        records, _ = self.read_source_records()
        record = next((item for item in records if item.source_id == source_id_value), None)
        if record is None:
            return None
        comments, _ = self.read_comments()
        tags, _ = self.read_tags()
        source_comments = [comment for comment in comments if comment.source_id == source_id_value]
        source_tags = [tag_record for tag_record in tags if tag_record.source_id == source_id_value]
        human_tags = sorted({tag_record.tag for tag_record in source_tags})
        open_path = str(self.root / record.relative_path) if record.relative_path else None
        return SourceDetail(
            source_id=record.source_id,
            type=record.type,
            title=record.title,
            lifecycle_status=record.lifecycle_status,
            date_added=record.date_added,
            updated_at=record.updated_at,
            relative_path=record.relative_path,
            original_url=record.original_url,
            human_tags=human_tags,
            comment_count=len(source_comments),
            content_hash=record.content_hash,
            open_url=record.original_url,
            open_path=open_path,
            comments=source_comments,
            tag_records=source_tags,
        )

    def write_comment(self, source_id_value: str, user_email: str, body: str, existing_id: str | None = None) -> CommentRecord:
        now = utc_now()
        comments, _ = self.read_comments()
        existing = next((comment for comment in comments if comment.comment_id == existing_id), None) if existing_id else None
        if existing:
            record = existing.model_copy(update={"body": body.strip(), "user_email": user_email.lower(), "updated_at": now})
        else:
            record = CommentRecord(
                comment_id=comment_id(),
                source_id=source_id_value,
                user_email=user_email.lower(),
                created_at=now,
                updated_at=now,
                body=body.strip(),
            )
        write_markdown_record(
            self.comments_dir / f"{record.comment_id}.md",
            record.model_dump(exclude={"body"}),
            record.body,
        )
        self.sync()
        return record

    def write_tag(self, source_id_value: str, user_email: str, tag: str, existing_id: str | None = None) -> HumanTagRecord:
        now = utc_now()
        tags, _ = self.read_tags()
        existing = next((tag_record for tag_record in tags if tag_record.tag_id == existing_id), None) if existing_id else None
        clean_tag = tag.strip()
        if existing:
            record = existing.model_copy(update={"tag": clean_tag, "user_email": user_email.lower(), "updated_at": now})
        else:
            record = HumanTagRecord(
                tag_id=tag_id(),
                source_id=source_id_value,
                user_email=user_email.lower(),
                tag=clean_tag,
                created_at=now,
                updated_at=now,
            )
        write_markdown_record(self.tags_dir / f"{record.tag_id}.md", record.model_dump(), "")
        self.sync()
        return record

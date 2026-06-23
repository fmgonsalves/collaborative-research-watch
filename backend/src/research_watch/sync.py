from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
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
    SyncSourceEvent,
    TagSuggestion,
    ValidationIssue,
    display_title_for_path,
    utc_now,
)

logger = logging.getLogger(__name__)


def format_bytes(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B"


def elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


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


def file_content_snapshot(path: Path) -> tuple[int, float]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime


def document_content_changed(record: SourceRecord, size: int, mtime: float) -> bool:
    if record.content_size is None or record.content_mtime is None:
        return False
    return record.content_size != size or record.content_mtime != mtime


def sync_source_event(record: SourceRecord) -> SyncSourceEvent:
    return SyncSourceEvent(
        source_id=record.source_id,
        title=record.title,
        type=record.type,
        relative_path=record.relative_path,
        original_url=record.original_url,
    )


@dataclass(frozen=True)
class IntakeSnapshot:
    links_mtime_ns: int
    links_size: int
    sources_dir_mtime_ns: int
    document_stats: tuple[tuple[str, int, float], ...]


class ResearchRepository:
    def __init__(self, root: Path) -> None:
        self.root = root
        self._source_records_cache: tuple[list[SourceRecord], list[ValidationIssue]] | None = None
        self._comments_cache: tuple[list[CommentRecord], list[ValidationIssue]] | None = None
        self._tags_cache: tuple[list[HumanTagRecord], list[ValidationIssue]] | None = None
        self._intake_snapshot: IntakeSnapshot | None = None

    def invalidate_read_cache(self) -> None:
        self._source_records_cache = None
        self._comments_cache = None
        self._tags_cache = None

    def invalidate_intake_snapshot(self) -> None:
        self._intake_snapshot = None

    def _capture_intake_snapshot(self, by_path: dict[str, SourceRecord], links_path: Path) -> IntakeSnapshot:
        links_stat = links_path.stat()
        sources_stat = self.sources_dir.stat()
        document_stats: list[tuple[str, int, float]] = []
        for relative_path in sorted(by_path):
            path = self.root / relative_path
            if path.is_file():
                size, mtime = file_content_snapshot(path)
                document_stats.append((relative_path, size, mtime))
        return IntakeSnapshot(
            links_mtime_ns=links_stat.st_mtime_ns,
            links_size=links_stat.st_size,
            sources_dir_mtime_ns=sources_stat.st_mtime_ns,
            document_stats=tuple(document_stats),
        )

    def _intake_unchanged(self, snapshot: IntakeSnapshot, by_path: dict[str, SourceRecord], links_path: Path) -> bool:
        try:
            links_stat = links_path.stat()
            sources_stat = self.sources_dir.stat()
        except OSError:
            return False
        if (links_stat.st_mtime_ns, links_stat.st_size) != (snapshot.links_mtime_ns, snapshot.links_size):
            return False
        if sources_stat.st_mtime_ns != snapshot.sources_dir_mtime_ns:
            return False
        expected_paths = {item[0] for item in snapshot.document_stats}
        if set(by_path.keys()) != expected_paths:
            return False
        expected_stats = {item[0]: (item[1], item[2]) for item in snapshot.document_stats}
        for relative_path, expected in expected_stats.items():
            path = self.root / relative_path
            if not path.is_file() or file_content_snapshot(path) != expected:
                return False
        return True

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
        if self._source_records_cache is not None:
            return self._source_records_cache
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
        self._source_records_cache = (records, issues)
        return records, issues

    def write_source_record(self, record: SourceRecord, *, invalidate_cache: bool = True) -> None:
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
        if invalidate_cache:
            self.invalidate_read_cache()
            self.invalidate_intake_snapshot()

    def delete_source_record(self, record: SourceRecord, *, invalidate_cache: bool = True) -> None:
        path = self.source_records_dir / f"{record.source_id}.md"
        if path.exists():
            path.unlink()
        if invalidate_cache:
            self.invalidate_read_cache()
            self.invalidate_intake_snapshot()

    def delete_collaboration_for_source(self, source_id_value: str, *, invalidate_cache: bool = True) -> tuple[int, int]:
        comments_removed = 0
        for path in self.comments_dir.glob("comment_*.md"):
            frontmatter, _ = read_markdown_record(path)
            if frontmatter.get("source_id") == source_id_value:
                path.unlink()
                comments_removed += 1
        tags_removed = 0
        for path in self.tags_dir.glob("tag_*.md"):
            frontmatter, _ = read_markdown_record(path)
            if frontmatter.get("source_id") == source_id_value:
                path.unlink()
                tags_removed += 1
        if invalidate_cache:
            self.invalidate_read_cache()
            self.invalidate_intake_snapshot()
        return comments_removed, tags_removed

    def read_comments(self) -> tuple[list[CommentRecord], list[ValidationIssue]]:
        if self._comments_cache is not None:
            return self._comments_cache
        comments: list[CommentRecord] = []
        issues: list[ValidationIssue] = []
        for path in sorted(self.comments_dir.glob("comment_*.md")):
            frontmatter, body = read_markdown_record(path)
            try:
                comments.append(CommentRecord.model_validate({**frontmatter, "body": body.strip()}))
            except ValidationError as error:
                issues.append(ValidationIssue(code="invalid_comment_record", message=str(error), path=str(path)))
        self._comments_cache = (comments, issues)
        return comments, issues

    def read_tags(self) -> tuple[list[HumanTagRecord], list[ValidationIssue]]:
        if self._tags_cache is not None:
            return self._tags_cache
        tags: list[HumanTagRecord] = []
        issues: list[ValidationIssue] = []
        for path in sorted(self.tags_dir.glob("tag_*.md")):
            frontmatter, _ = read_markdown_record(path)
            try:
                tags.append(HumanTagRecord.model_validate(frontmatter))
            except ValidationError as error:
                issues.append(ValidationIssue(code="invalid_tag_record", message=str(error), path=str(path)))
        self._tags_cache = (tags, issues)
        return tags, issues

    def list_tag_suggestions(self, q: str = "", limit: int = 50) -> list[TagSuggestion]:
        tags, _ = self.read_tags()
        counts: dict[str, int] = defaultdict(int)
        for tag_record in tags:
            counts[tag_record.tag] += 1
        query = q.strip().lower()
        suggestions = [
            TagSuggestion(tag=tag, count=count)
            for tag, count in counts.items()
            if not query or query in tag.lower()
        ]
        suggestions.sort(key=lambda item: item.tag.lower())
        cap = min(max(limit, 1), 100)
        return suggestions[:cap]

    def sync(self) -> SyncReport:
        sync_started = time.perf_counter()
        logger.info("Sync started workspace=%s", self.root)
        now = utc_now()
        load_started = time.perf_counter()
        existing, record_issues = self.read_source_records()
        load_elapsed_ms = elapsed_ms(load_started)
        logger.info("Loaded %d existing source records (%dms)", len(existing), load_elapsed_ms)
        current_by_id = {record.source_id: record for record in existing}
        by_path = {record.relative_path: record for record in existing if record.type == "document" and record.relative_path}
        by_url = {
            normalize_url(record.original_url): record
            for record in existing
            if record.type == "link" and record.original_url
        }
        seen_ids: set[str] = set()
        report = SyncReport(workspace_path=str(self.root), sources_total=0, issues=record_issues)
        links_path = self.root / "links.csv"
        snapshot = self._intake_snapshot
        collaboration_cache_warm = self._comments_cache is not None and self._tags_cache is not None
        if snapshot and collaboration_cache_warm and self._intake_unchanged(snapshot, by_path, links_path):
            all_records = list(current_by_id.values())
            self._source_records_cache = (all_records, record_issues)
            report.sources_total = len(all_records)
            total_elapsed_ms = elapsed_ms(sync_started)
            logger.info("Sync fast path: intake unchanged (%dms) total=%d", total_elapsed_ms, report.sources_total)
            return report

        self.sources_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Scanning sources/")
        documents_started = time.perf_counter()
        processed_document_paths: set[str] = set()
        for relative_path, record in sorted(by_path.items()):
            path = self.root / relative_path
            if not path.is_file():
                continue
            processed_document_paths.add(relative_path)
            file_size, file_mtime = file_content_snapshot(path)
            record.last_seen_at = now
            if document_content_changed(record, file_size, file_mtime):
                logger.info("Document %s (%s) changed (size/mtime)", relative_path, format_bytes(file_size))
                record.lifecycle_status = "changed"
                record.updated_at = now
                record.content_size = file_size
                record.content_mtime = file_mtime
                report.changed += 1
                report.changed_sources.append(sync_source_event(record))
                self.write_source_record(record, invalidate_cache=False)
            else:
                logger.info("Document %s (%s) unchanged (size/mtime)", relative_path, format_bytes(file_size))
                record.content_size = file_size
                record.content_mtime = file_mtime
            seen_ids.add(record.source_id)
            current_by_id[record.source_id] = record
        for path in sorted(self.sources_dir.rglob("*")):
            if not path.is_file() or any(part.startswith(".") for part in path.relative_to(self.sources_dir).parts):
                continue
            relative_path = path.relative_to(self.root).as_posix()
            if relative_path in processed_document_paths:
                continue
            if path.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
                report.invalid += 1
                logger.info("Document %s unsupported extension: %s", relative_path, path.suffix or "(none)")
                report.issues.append(
                    ValidationIssue(
                        code="unsupported_document_type",
                        message=f"Unsupported document extension: {path.suffix or '(none)'}.",
                        path=relative_path,
                    )
                )
                continue
            file_size, file_mtime = file_content_snapshot(path)
            if by_path.get(relative_path) is not None:
                continue
            logger.info("Document %s (%s) new", relative_path, format_bytes(file_size))
            record = SourceRecord(
                source_id=source_id(),
                type="document",
                title=display_title_for_path(path),
                relative_path=relative_path,
                content_size=file_size,
                content_mtime=file_mtime,
                date_added=now,
                last_seen_at=now,
                updated_at=now,
                lifecycle_status="available",
            )
            report.created += 1
            report.created_sources.append(sync_source_event(record))
            self.write_source_record(record, invalidate_cache=False)
            seen_ids.add(record.source_id)
            current_by_id[record.source_id] = record
        documents_elapsed_ms = elapsed_ms(documents_started)
        logger.info(
            "Documents processed in %dms created=%d changed=%d updated=%d invalid=%d",
            documents_elapsed_ms,
            report.created,
            report.changed,
            report.updated,
            report.invalid,
        )

        links_started = time.perf_counter()
        links, link_issues = read_links(links_path)
        report.issues.extend(link_issues)
        logger.info("Processing %d links", len(links))
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
                report.created_sources.append(sync_source_event(record))
                self.write_source_record(record, invalidate_cache=False)
            else:
                record.last_seen_at = now
                if row["title"] and row["title"] != record.title:
                    record.title = row["title"]
                    record.updated_at = now
                    report.updated += 1
                    report.updated_sources.append(sync_source_event(record))
                    self.write_source_record(record, invalidate_cache=False)
            seen_ids.add(record.source_id)
            current_by_id[record.source_id] = record
        links_elapsed_ms = elapsed_ms(links_started)
        logger.info("Links processed in %dms", links_elapsed_ms)

        removal_started = time.perf_counter()
        for record in existing:
            if record.source_id in seen_ids:
                continue
            event = sync_source_event(record)
            report.removed_sources.append(event)
            comments_removed, tags_removed = self.delete_collaboration_for_source(record.source_id, invalidate_cache=False)
            report.removed_comments += comments_removed
            report.removed_tags += tags_removed
            self.delete_source_record(record, invalidate_cache=False)
            report.removed += 1
            current_by_id.pop(record.source_id, None)
            logger.info(
                "Removed source %s (%s) cascade: %d comments, %d tags",
                record.source_id,
                record.title,
                comments_removed,
                tags_removed,
            )
        removal_elapsed_ms = elapsed_ms(removal_started)
        if report.removed_comments or report.removed_tags:
            self._comments_cache = None
            self._tags_cache = None
        logger.info(
            "Removed %d sources (%dms) cascade: %d comments, %d tags",
            report.removed,
            removal_elapsed_ms,
            report.removed_comments,
            report.removed_tags,
        )

        users, user_issues = read_users(self.root / "users.csv")
        report.issues.extend(user_issues)
        all_records = list(current_by_id.values())
        intake_changed = report.created + report.changed + report.updated + report.removed + report.invalid > 0
        collaboration_cache_cold = self._comments_cache is None or self._tags_cache is None
        if intake_changed or collaboration_cache_cold:
            self.write_index(all_records, users)
        else:
            logger.info("Skipping index.md regeneration; intake and collaboration unchanged")
        self._source_records_cache = (all_records, record_issues)
        report.sources_total = len(all_records)
        final_by_path = {
            record.relative_path: record
            for record in all_records
            if record.type == "document" and record.relative_path
        }
        self._intake_snapshot = self._capture_intake_snapshot(final_by_path, links_path)
        total_elapsed_ms = elapsed_ms(sync_started)
        logger.info(
            "Sync finished in %dms created=%d changed=%d updated=%d removed=%d invalid=%d total=%d",
            total_elapsed_ms,
            report.created,
            report.changed,
            report.updated,
            report.removed,
            report.invalid,
            report.sources_total,
        )
        return report

    def write_index(self, records: list[SourceRecord], users: object) -> None:
        started = time.perf_counter()
        logger.info("Writing index.md")
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
        logger.info("Wrote index.md for %d sources (%dms)", len(records), elapsed_ms(started))

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
        self._comments_cache = None
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
        self._tags_cache = None
        self.sync()
        return record

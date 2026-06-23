from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from pydantic import ValidationError

from .ai_generation import AIConfigurationError, AIGenerationError, AIGenerator, generate_with_openai
from .ai_input import build_ai_safe_source_input
from .ai_store import read_ai_record, read_ai_records, write_ai_record
from .csv_store import read_links, read_users
from .extractors import extract_document_text, fetch_link_text
from .markdown_store import read_markdown_record, write_markdown_record
from .models import (
    AIRecord,
    CommentRecord,
    ExtractionResult,
    HumanTagRecord,
    SUPPORTED_DOCUMENT_EXTENSIONS,
    SourceDetail,
    SourceAIEnrichment,
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


def source_ai_enrichment(record: AIRecord) -> SourceAIEnrichment:
    return SourceAIEnrichment(
        status=record.status,
        generated_at=record.generated_at,
        ai_generated_tags=record.ai_generated_tags,
        summary=record.summary,
        error_summary=record.error_summary,
    )


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

    def source_record(self, source_id_value: str) -> SourceRecord | None:
        records, _ = self.read_source_records()
        return next((item for item in records if item.source_id == source_id_value), None)

    def delete_source_record(self, record: SourceRecord) -> None:
        path = self.source_records_dir / f"{record.source_id}.md"
        if path.exists():
            path.unlink()

    def delete_collaboration_for_source(self, source_id_value: str) -> tuple[int, int]:
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
        return comments_removed, tags_removed

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
        logger.info("Loaded %d existing source records (%dms)", len(existing), elapsed_ms(load_started))
        by_path = {record.relative_path: record for record in existing if record.type == "document" and record.relative_path}
        by_url = {
            normalize_url(record.original_url): record
            for record in existing
            if record.type == "link" and record.original_url
        }
        seen_ids: set[str] = set()
        report = SyncReport(workspace_path=str(self.root), sources_total=0, issues=record_issues)

        self.sources_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Scanning sources/")
        documents_started = time.perf_counter()
        for path in sorted(self.sources_dir.rglob("*")):
            if not path.is_file() or any(part.startswith(".") for part in path.relative_to(self.sources_dir).parts):
                continue
            relative_path = path.relative_to(self.root).as_posix()
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
            record = by_path.get(relative_path)
            if record is None:
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
            else:
                record.last_seen_at = now
                record.updated_at = now
                if document_content_changed(record, file_size, file_mtime):
                    logger.info("Document %s (%s) changed (size/mtime)", relative_path, format_bytes(file_size))
                    record.lifecycle_status = "changed"
                    report.changed += 1
                    report.changed_sources.append(sync_source_event(record))
                else:
                    logger.info("Document %s (%s) unchanged (size/mtime)", relative_path, format_bytes(file_size))
                record.content_size = file_size
                record.content_mtime = file_mtime
            seen_ids.add(record.source_id)
            self.write_source_record(record)
        logger.info(
            "Documents processed in %dms created=%d changed=%d updated=%d invalid=%d",
            elapsed_ms(documents_started),
            report.created,
            report.changed,
            report.updated,
            report.invalid,
        )

        links_started = time.perf_counter()
        links, link_issues = read_links(self.root / "links.csv")
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
            else:
                record.last_seen_at = now
                record.updated_at = now
                if row["title"] and row["title"] != record.title:
                    record.title = row["title"]
                    report.updated += 1
                    report.updated_sources.append(sync_source_event(record))
            seen_ids.add(record.source_id)
            self.write_source_record(record)
        logger.info("Links processed in %dms", elapsed_ms(links_started))

        removal_started = time.perf_counter()
        for record in existing:
            if record.source_id in seen_ids:
                continue
            event = sync_source_event(record)
            report.removed_sources.append(event)
            comments_removed, tags_removed = self.delete_collaboration_for_source(record.source_id)
            report.removed_comments += comments_removed
            report.removed_tags += tags_removed
            self.delete_source_record(record)
            report.removed += 1
            logger.info(
                "Removed source %s (%s) cascade: %d comments, %d tags",
                record.source_id,
                record.title,
                comments_removed,
                tags_removed,
            )
        logger.info(
            "Removed %d sources (%dms) cascade: %d comments, %d tags",
            report.removed,
            elapsed_ms(removal_started),
            report.removed_comments,
            report.removed_tags,
        )

        users, user_issues = read_users(self.root / "users.csv")
        report.issues.extend(user_issues)
        logger.info("Reloading source records before index write")
        all_records, source_issues = self.read_source_records()
        report.issues.extend(source_issues)
        self.write_index(all_records, users)
        report.sources_total = len(all_records)
        logger.info(
            "Sync finished in %dms created=%d changed=%d updated=%d removed=%d invalid=%d total=%d",
            elapsed_ms(sync_started),
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

    def list_ai_tag_suggestions(self, q: str = "", limit: int = 50) -> list[TagSuggestion]:
        ai_records, issues = read_ai_records(self.root)
        for issue in issues:
            logger.warning("invalid_ai_record path=%s message=%s", issue.path, issue.message)
        counts: dict[str, int] = defaultdict(int)
        for record in ai_records:
            for tag in record.ai_generated_tags:
                counts[tag] += 1
        query = q.strip().lower()
        suggestions = [
            TagSuggestion(tag=tag, count=count)
            for tag, count in counts.items()
            if not query or query in tag.lower()
        ]
        suggestions.sort(key=lambda item: item.tag.lower())
        cap = min(max(limit, 1), 100)
        return suggestions[:cap]

    def summaries(
        self,
        search: str = "",
        type_filter: str = "",
        status: str = "",
        tag: str = "",
        ai_tag: str = "",
        ai_status: str = "",
        sort: str = "title",
    ) -> list[SourceSummary]:
        records, _ = self.read_source_records()
        comments, _ = self.read_comments()
        tags, _ = self.read_tags()
        ai_records, ai_issues = read_ai_records(self.root)
        for issue in ai_issues:
            logger.warning("invalid_ai_record path=%s message=%s", issue.path, issue.message)
        ai_by_source = {record.source_id: record for record in ai_records}
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
            ai_record = ai_by_source.get(record.source_id)
            ai_generated_tags = sorted(ai_record.ai_generated_tags) if ai_record is not None else []
            ai_summary = ai_record.summary if ai_record is not None else ""
            ai_status_value = ai_record.status if ai_record is not None else None
            comment_text = " ".join(comment.body for comment in comments_by_source[record.source_id])
            haystack = " ".join(
                [
                    record.title,
                    record.type,
                    record.lifecycle_status,
                    record.original_url or "",
                    record.relative_path or "",
                    " ".join(human_tags),
                    comment_text,
                    " ".join(ai_generated_tags),
                    ai_summary,
                ]
            ).lower()
            if search_lower and search_lower not in haystack:
                continue
            if type_filter and record.type != type_filter:
                continue
            if status and record.lifecycle_status != status:
                continue
            if tag and tag not in human_tags:
                continue
            if ai_tag and ai_tag not in ai_generated_tags:
                continue
            if ai_status and ai_status != ai_status_value:
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
                    ai_status=ai_status_value,
                    ai_generated_tags=ai_generated_tags,
                    ai_summary=ai_summary,
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
        record = self.source_record(source_id_value)
        if record is None:
            return None
        comments, _ = self.read_comments()
        tags, _ = self.read_tags()
        source_comments = [comment for comment in comments if comment.source_id == source_id_value]
        source_tags = [tag_record for tag_record in tags if tag_record.source_id == source_id_value]
        human_tags = sorted({tag_record.tag for tag_record in source_tags})
        ai_record, ai_issues = read_ai_record(self.root, source_id_value)
        for issue in ai_issues:
            logger.warning("invalid_ai_record source_id=%s path=%s message=%s", source_id_value, issue.path, issue.message)
        ai = source_ai_enrichment(ai_record) if ai_record is not None else None
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
            ai=ai,
        )

    def source_document_path_for_enrichment(self, record: SourceRecord) -> Path | None:
        if record.type != "document" or not record.relative_path:
            return None
        source_path = (self.root / record.relative_path).resolve(strict=False)
        sources_root = self.sources_dir.resolve(strict=False)
        if not source_path.is_relative_to(sources_root) or not source_path.is_file():
            return None
        return source_path

    def enrich_document_source(self, record: SourceRecord, generator: AIGenerator | None = None) -> SourceAIEnrichment:
        now = utc_now()
        path = self.source_document_path_for_enrichment(record)
        if path is None:
            ai_record = AIRecord(
                source_id=record.source_id,
                status="extraction_failed",
                generated_at=now,
                source_title=record.title,
                source_type=record.type,
                error_summary="Source file is not available for extraction.",
                extractor="document",
            )
            write_ai_record(self.root, ai_record)
            return source_ai_enrichment(ai_record)

        extraction = extract_document_text(record, path)
        if extraction.extracted is None:
            ai_record = AIRecord(
                source_id=record.source_id,
                status="extraction_failed",
                generated_at=now,
                source_title=record.title,
                source_type=record.type,
                error_summary=extraction.error_summary or "Could not extract readable text.",
                extractor=extraction.extractor,
            )
            write_ai_record(self.root, ai_record)
            return source_ai_enrichment(ai_record)

        return self.enrich_extracted_source(record, extraction, now, generator=generator)

    def enrich_link_source(self, record: SourceRecord, generator: AIGenerator | None = None) -> SourceAIEnrichment:
        now = utc_now()
        extraction = fetch_link_text(record)
        if extraction.extracted is None:
            ai_record = AIRecord(
                source_id=record.source_id,
                status="fetch_failed",
                generated_at=now,
                source_title=record.title,
                source_type=record.type,
                error_summary=extraction.error_summary or "Could not fetch readable link content.",
                extractor=extraction.extractor,
            )
            write_ai_record(self.root, ai_record)
            return source_ai_enrichment(ai_record)
        return self.enrich_extracted_source(record, extraction, now, generator=generator)

    def enrich_source(self, record: SourceRecord, generator: AIGenerator | None = None) -> SourceAIEnrichment:
        if record.type == "link":
            return self.enrich_link_source(record, generator=generator)
        return self.enrich_document_source(record, generator=generator)

    def enrich_extracted_source(
        self,
        record: SourceRecord,
        extraction: ExtractionResult,
        now: str,
        generator: AIGenerator | None = None,
    ) -> SourceAIEnrichment:
        if extraction.extracted is None:
            raise ValueError("Cannot enrich source without extracted text.")
        active_generator = generator or generate_with_openai
        source_input = build_ai_safe_source_input(record, extraction.extracted)
        existing_ai_record, _ = read_ai_record(self.root, record.source_id)
        try:
            generation = active_generator(source_input)
        except AIConfigurationError as error:
            logger.warning("AI generation skipped source_id=%s reason=%s", record.source_id, error.safe_message)
            raise
        except AIGenerationError as error:
            if existing_ai_record is not None:
                logger.warning(
                    "AI generation failed source_id=%s existing_record=preserved reason=%s",
                    record.source_id,
                    error.safe_message,
                )
                raise
            logger.warning(
                "AI generation failed source_id=%s writing_status=generation_failed reason=%s",
                record.source_id,
                error.safe_message,
            )
            ai_record = AIRecord(
                source_id=record.source_id,
                status="generation_failed",
                generated_at=now,
                source_title=record.title,
                source_type=record.type,
                error_summary=error.safe_message,
                extractor=extraction.extractor,
            )
            write_ai_record(self.root, ai_record)
            return source_ai_enrichment(ai_record)
        ai_record = AIRecord(
            source_id=record.source_id,
            status="generated",
            generated_at=now,
            source_title=record.title,
            source_type=record.type,
            ai_generated_tags=generation.ai_generated_tags,
            summary=generation.summary,
            extractor=extraction.extractor,
            model=generation.model,
        )
        write_ai_record(self.root, ai_record)
        return source_ai_enrichment(ai_record)

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

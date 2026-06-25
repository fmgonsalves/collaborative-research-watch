# Workspace Schema

This document describes the on-disk layout and file formats for a Collaborative Research Watch workspace as implemented today. Product-level entity definitions and data-classification rules remain in `PRD.md`. See `PATH_2_DESIGN.md` for AI enrichment behavior and extraction/fetching boundaries.

The implementation source of truth for record shapes is `backend/src/research_watch/models.py`. Validation and read/write behavior live in `csv_store.py`, `markdown_store.py`, `ai_store.py`, and `sync.py`.

## Workspace Layout

```text
<workspace-root>/
  sources/                 # user-managed document intake
  links.csv                # user-managed link intake
  users.csv                # user-managed team registry
  records/
    sources/               # app-managed source registry (src_*.md)
    comments/              # app-managed comments (comment_*.md)
    human-tags/            # app-managed human tag assignments (tag_*.md)
    ai/                    # app-managed AI output (Path 2; src_*.md)
  index.md                 # app-generated catalog (do not edit by hand)
```

### Ownership Summary

| Path | Managed by | Purpose |
| --- | --- | --- |
| `sources/` | User | Drop supported document files for intake. |
| `links.csv` | User | Add or edit web links for intake. |
| `users.csv` | User | Team member registry (`name`, `email`). |
| `records/sources/` | App | Canonical source registry and metadata. |
| `records/comments/` | App | Team comments on sources. |
| `records/human-tags/` | App | Human-created tag assignments on sources. |
| `records/ai/` | App | AI summaries and AI-generated tags (Path 2). |
| `index.md` | App | Human-readable catalog regenerated on resync and collaboration writes. |

On resync, user-facing intake (`sources/`, `links.csv`) is authoritative. If an intake entry disappears, the app deletes its source record and cascades removal of associated comments and human tags.

## Conventions

### Timestamps

All app-written timestamps are UTC ISO-8601 strings with second precision, for example `2026-06-17T14:30:00+00:00`.

### IDs and Filenames

| Entity | ID format | Filename |
| --- | --- | --- |
| Source | `src_` + 12 lowercase hex chars | `records/sources/<source_id>.md` |
| Comment | `comment_` + 12 lowercase hex chars | `records/comments/<comment_id>.md` |
| Human tag | `tag_` + 12 lowercase hex chars | `records/human-tags/<tag_id>.md` |
| AI output | Same as source ID | `records/ai/<source_id>.md` |

Source IDs are assigned during resync. They are not written back into `links.csv`.

### Markdown Records

App-managed records use YAML frontmatter between `---` delimiters, followed by an optional Markdown body:

```markdown
---
field: value
---

Optional Markdown body.
```

The app omits `null` optional fields when writing source records (`exclude_none=True`).

## User-Managed Files

### `sources/`

- Contains raw document files only. Do not store comments, tags, or app metadata inside source documents.
- Supported extensions: `.pdf`, `.docx`, `.txt`, `.md`, `.csv`.
- Files with other extensions are reported as invalid during resync and do not receive source records.
- Hidden path segments (names starting with `.`) are ignored.
- Documents are matched to source records by normalized relative path under the workspace root (for example `sources/paper.md`).
- Content changes are detected via file size and modification time (`content_size`, `content_mtime` on the source record), then confirmed with a full-file streaming SHA-256 hash when needed.
- Hashes are computed from raw file bytes, not extracted text, and only for supported document files.

### `links.csv`

Required header (exact column order):

```csv
url,title
```

| Column | Required | Notes |
| --- | --- | --- |
| `url` | Yes | Public or team-approved URL. Normalized on read (scheme lowercased, default `https`, trailing slash on path trimmed except root). |
| `title` | No | Display title. If empty, the normalized URL is used. |

Validation rules:

- Header must be exactly `url,title`. Other column orders are rejected.
- Each row must have a non-empty `url`.
- Duplicate normalized URLs in one file are reported as invalid; the duplicate row is skipped.

Do not add source IDs, comments, tags, attribution, preferences, or AI fields to this file.

### `users.csv`

Required header (exact column order):

```csv
name,email
```

| Column | Required | Notes |
| --- | --- | --- |
| `name` | Yes | Team-facing display name. |
| `email` | Yes | Unique canonical user key. Stored lowercase. |

Validation rules:

- Header must be exactly `name,email`.
- Each row must have non-empty `name` and `email`.
- Duplicate emails are reported as invalid; the duplicate row is skipped.

## App-Managed Records

### Source Record — `records/sources/src_<id>.md`

Frontmatter fields (validated by `SourceRecord`):

| Field | Type | Required | Classification | Notes |
| --- | --- | --- | --- | --- |
| `source_id` | string | Yes | `source_public` | Matches filename stem. |
| `type` | `document` \| `link` | Yes | `source_public` | |
| `title` | string | Yes | `source_public` | |
| `lifecycle_status` | string | Yes | `source_public` | Path 1: `available` or `changed`. |
| `date_added` | string | Yes | `source_public` | UTC ISO timestamp. |
| `last_seen_at` | string | Yes | `app_internal` | Updated each resync when intake entry is present. |
| `updated_at` | string | Yes | `app_internal` | Updated on create, resync touch, or metadata change. |
| `relative_path` | string | For documents | `source_public` | Workspace-relative path (for example `sources/paper.md`). |
| `original_url` | string | For links | `source_public` | Normalized URL. |
| `content_size` | integer | For documents | `app_internal` | Last seen size in bytes. |
| `content_mtime` | float | For documents | `app_internal` | Last seen modification time (filesystem epoch). |
| `content_hash` | string | For documents | `app_internal` | Full-file SHA-256 hash in `sha256:<hex>` form. |
| `content_updated_at` | string | For documents | `app_internal` | Last detected document content update. |

The Markdown body is human-readable summary text generated by the app (title heading plus type, status, path or URL). It is not the operational source of truth.

Example (document):

```markdown
---
source_id: src_a1b2c3d4e5f6
type: document
title: Research Paper
lifecycle_status: available
date_added: '2026-06-17T12:00:00+00:00'
last_seen_at: '2026-06-17T14:00:00+00:00'
updated_at: '2026-06-17T14:00:00+00:00'
relative_path: sources/research-paper.md
content_size: 2048
content_mtime: 1718632800.0
content_hash: sha256:a1b2c3...
content_updated_at: '2026-06-17T12:00:00+00:00'
---

# Research Paper

- Type: document
- Status: available
- Path: sources/research-paper.md
```

Example (link):

```markdown
---
source_id: src_f6e5d4c3b2a1
type: link
title: Example Research
lifecycle_status: available
date_added: '2026-06-17T12:00:00+00:00'
last_seen_at: '2026-06-17T14:00:00+00:00'
updated_at: '2026-06-17T14:00:00+00:00'
original_url: https://example.com/research
---

# Example Research

- Type: link
- Status: available
- URL: https://example.com/research
```

Legacy records may contain extra frontmatter keys (for example `content_hash`). Unknown keys are ignored on read if required fields validate. On the next resync, document records are rewritten with current fields including `content_size` and `content_mtime`.

### Comment Record — `records/comments/comment_<id>.md`

Frontmatter fields (validated by `CommentRecord`):

| Field | Type | Required | Classification |
| --- | --- | --- | --- |
| `comment_id` | string | Yes | `team_confidential` |
| `source_id` | string | Yes | `team_confidential` |
| `user_email` | string | Yes | `team_confidential` |
| `created_at` | string | Yes | `team_confidential` |
| `updated_at` | string | Yes | `team_confidential` |

The Markdown body is the comment text (`body` in the API model).

Example:

```markdown
---
comment_id: comment_1a2b3c4d5e6f
source_id: src_a1b2c3d4e5f6
user_email: ada@example.com
created_at: '2026-06-17T12:05:00+00:00'
updated_at: '2026-06-17T12:05:00+00:00'
---

Worth discussing in the next review.
```

### Human Tag Record — `records/human-tags/tag_<id>.md`

Frontmatter fields (validated by `HumanTagRecord`):

| Field | Type | Required | Classification |
| --- | --- | --- | --- |
| `tag_id` | string | Yes | `team_confidential` |
| `source_id` | string | Yes | `team_confidential` |
| `user_email` | string | Yes | `team_confidential` |
| `tag` | string | Yes | `team_confidential` |
| `created_at` | string | Yes | `team_confidential` |
| `updated_at` | string | Yes | `team_confidential` |

Human tag files have an empty Markdown body.

Example:

```markdown
---
tag_id: tag_9f8e7d6c5b4a
source_id: src_a1b2c3d4e5f6
user_email: ada@example.com
tag: methods
created_at: '2026-06-17T12:10:00+00:00'
updated_at: '2026-06-17T12:10:00+00:00'
---

```

## App-Generated Catalog — `index.md`

Regenerated by the app after resync and after comment or tag writes. Not an operational source of truth.

Current structure:

- Title: `# Collaborative Research Watch Index`
- Note that the catalog is app-generated.
- `## Sources` section with one `### <title>` block per source, sorted by title.
- Per source: ID, type, status, source path or URL, human-created tags (comma-separated), comment count.

Do not edit `index.md` by hand; changes are overwritten.

## AI Records

AI enrichment writes one app-managed record per enriched source. Storage convention:

```text
records/ai/<source_id>.md
```

Frontmatter fields (validated by `AIRecord`):

| Field | Type | Required | Classification | Notes |
| --- | --- | --- | --- | --- |
| `source_id` | string | Yes | `source_public` | Matches the source ID and filename stem. |
| `status` | `generated` \| `extraction_failed` \| `fetch_failed` \| `generation_failed` | Yes | `source_public` | Current AI enrichment result. |
| `generated_at` | string | Yes | `source_public` | UTC ISO timestamp for the enrichment attempt. |
| `source_title` | string | Yes | `source_public` | Safe source title at enrichment time. |
| `source_type` | `document` \| `link` | Yes | `source_public` | Source kind. |
| `ai_generated_tags` | list of strings | No | `source_public` | AI-generated tags. Empty on failures. |
| `error_summary` | string | No | `source_public` | Safe user-facing failure summary. |
| `extractor` | string | No | `source_public` | Extractor/fetcher label, for example `python-docx`, `pdf`, `html`, or `simple-text`. |
| `model` | string | No | `source_public` | Model identifier when generation succeeded. Omitted on extraction/fetch failures and configuration failures. |

The Markdown body contains the AI-generated summary. It is empty on safe extraction, fetch, or generation failures.

Example (generated):

```yaml
source_id: src_...
status: generated
generated_at: "2026-..."
model: "..."
ai_generated_tags:
  - tag
source_title: "..."
source_type: document | link
extractor: python-docx
```

Example (safe failure):

```yaml
source_id: src_...
status: fetch_failed
generated_at: "2026-..."
ai_generated_tags: []
source_title: "..."
source_type: link
error_summary: "Could not fetch link content."
extractor: html
```

The app discovers AI output by the `records/ai/<source_id>.md` path convention. Source records do not store a separate `ai_record_path` field.

Parser diagnostics, raw HTTP errors, local paths, comments, human-created tags, users, and attribution are not written into AI records.

## Validation Behavior

- Malformed CSV headers, invalid rows, bad frontmatter, and unsupported documents are reported in the sync validation report.
- Valid records continue processing; invalid records are skipped without failing the entire sync.
- Removing a document from `sources/` or a link row from `links.csv` and resyncing deletes the source record and cascades deletion of its comments and human tags.

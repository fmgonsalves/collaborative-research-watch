# Path 2 Design: Per-Source AI Enrichment

## Goal

Path 2 adds bounded AI enrichment for individual sources. The app extracts or fetches source-public content, generates an AI summary and AI-generated tags, stores them as app-managed Markdown records, and displays them distinctly from human-created collaboration data.

AI remains an enrichment layer. It must not become the app's organizing architecture, source of truth, wiki, topic graph, chat system, vector store, or cross-source synthesis engine.

## Scope

In scope for Path 2 v1:

- Extract readable text from supported local documents where practical.
- Fetch readable text from public web links where practical.
- Generate one AI summary per source.
- Generate AI-generated tags per source.
- Store AI output under `records/ai/`.
- Display AI summary and AI-generated tags on source detail.
- Keep AI-generated tags visually and structurally distinct from human-created tags.
- Allow browse/search/filter to use AI summary and AI-generated tags after generation.
- Report extraction, fetch, and generation failures without breaking sync or browse.

Out of scope for Path 2 v1:

- Vector search or RAG.
- Cross-source synthesis.
- Autonomous topic graphs or wiki pages.
- Background job queues.
- Scheduled enrichment.
- Use of human comments, human-created tags, users, emails, preferences, or full local paths in prompts.

## Data Boundary

AI workflows may receive only `source_public` data:

- source ID
- source type
- title
- original URL for links
- safe relative filename/title metadata
- extracted/fetched source text

AI workflows must not receive:

- human comments
- human-created tags
- user names
- user emails
- attribution metadata
- selected user identity
- full local paths
- content size/mtime
- parser diagnostics
- cache metadata
- raw app errors
- app-internal run details

Prompt construction must be isolated behind a testable function. Negative tests must prove forbidden fields are absent from model inputs.

## Storage

AI records are app-managed Markdown files under:

```text
records/ai/<source_id>.md
```

For example, source `src_abc123` writes to `records/ai/src_abc123.md`.

Each AI record uses YAML frontmatter for machine-readable fields and Markdown body for the summary.

Minimum frontmatter fields:

```yaml
source_id: src_...
status: generated | extraction_failed | fetch_failed | generation_failed
generated_at: "2026-..."
ai_generated_tags:
  - tag
source_title: "..."
source_type: document | link
error_summary: null
extractor: "..."
model: "..."
```

The Markdown body contains only the AI-generated summary. Failure records may have an empty body and an `error_summary`.

AI records are rebuildable enrichment outputs, not canonical human collaboration data. Rebuildable means they can be regenerated on explicit user request; it does not mean schema migrations may discard or silently regenerate existing AI records.

## Trigger Model

Path 2 v1 uses manual enrichment actions only:

- Enrich one source from source detail.
- Optionally enrich all currently listed sources after single-source enrichment works.

Manual resync does not call the model. Sync may discover sources and existing AI records, but it must not automatically enrich.

## Extraction And Fetching

Document extraction should produce plain text plus internal diagnostics. Only plain extracted source text may enter AI prompts.

Extraction components should be replaceable. The rest of the AI enrichment workflow should depend on normalized extracted text and safe diagnostics, not on a specific parser's API or output shape.

Path 2 v1 starts with boring, lightweight extraction:

- `.txt`, `.md`, `.csv`: Python standard library.
- `.pdf`: `pypdf`.
- `.docx`: `python-docx`.

Docling may be evaluated later if the app needs richer document conversion, layout-aware extraction, table handling, OCR support, or Markdown output. Do not make Docling a required Path 2 v1 dependency.

Link fetching should start simple:

- Use HTTP fetch with timeout.
- Extract readable text conservatively from HTML.
- Treat paywalled, login-only, blocked, or non-HTML responses as fetch failures.

Diagnostics and raw parser errors are `app_internal`.

## API Shape

Add backend endpoints for enrichment:

- `POST /api/sources/{source_id}/ai/enrich`
- `GET /api/sources/{source_id}` includes AI record summary/tags/status when present.
- `GET /api/sources` includes AI-generated tags/status enough for browse/filter.

Exact payloads may remain minimal in v1. Errors should be returned as safe summaries, not raw internal exceptions.

## UI

Source detail shows:

- Human-created tags in the existing human tag area.
- AI-generated tags in a separate AI-labeled area.
- AI summary in a separate AI-labeled section.
- AI status or safe error summary when generation failed.

Browse/search/filter may include AI fields after records exist, but human-created tags remain separate from AI-generated tags.

## Tests

Required before or alongside implementation:

- AI prompt input includes source-public fields only.
- AI prompt input excludes comments, human-created tags, user names, user emails, full local paths, size/mtime, and parser diagnostics.
- AI Markdown record round-trips frontmatter and summary body.
- Failed extraction/fetch/generation writes safe status/error summary without breaking source detail.
- Existing Path 1 sync/browse/comment/tag tests continue passing.

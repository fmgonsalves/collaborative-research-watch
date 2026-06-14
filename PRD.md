# Collaborative Research Watch PRD

## 1. Product Vision

Collaborative Research Watch is a local/shared-repository demo app for teams that collect, summarize, browse, and discuss research documents and web links. The product lets users add documents to a shared folder and links to a shared CSV file, then uses an LLM-wiki intelligence layer to incrementally build a persistent Knowledge Base.

The first proof path intentionally avoids confidential collaboration data so the team can prove the core loop quickly:

```text
source added -> resync -> ingest -> wiki update -> browse/search -> Q&A -> newsletter preview
```

Later phases add users, app-managed private annotations, private tags, newsletter preferences, privacy guardrails, Excel compatibility, and wiki health checks. The long-term product goal is a collaborative research workspace where the agent can freely use public source content and generated wiki knowledge, while private human collaboration data is never exposed to the model.

## 2. At-a-Glance Roadmap

| Functionality | Required Phase | Notes |
| --- | --- | --- |
| Shared source folder | Path 1 | Users can drop supported documents into `sources/`. |
| UI document upload | Path 1 | Uploads write into the shared source workflow. |
| Shared link CSV | Path 1 | Users can add public web links through `links.csv`. |
| App-generated source IDs | Path 1 | Resync assigns stable IDs to new documents and link rows in SQLite. |
| Manual resync | Path 1 | Detects new, changed, stale, failed, and invalid sources. |
| PDF, DOCX, text, and public web link ingestion | Path 1 | Public pages only; blocked/login-only links are marked failed or needs-manual-content. |
| Sanitized extracted text | Path 1 | Extracted content is keyed by `source_id` and excludes local path leakage. |
| Generated LLM-wiki | Path 1 | Includes `wiki/index.md`, `wiki/log.md`, per-source pages, topic pages, and tag pages. |
| Browse/search/filter/sort | Path 1 | Covers source metadata, public summaries, public tags, and lifecycle status. |
| Q&A over Knowledge Base | Path 1 | Uses wiki plus simple search; cites safe title and `source_id`. |
| Newsletter preview | Path 1 | Generates preview-only newsletters with safe citations; no sending. |
| Shared user CSV | Path 2 | `users.csv` is canonical and minimal; email must be unique. |
| App-managed private comments and private tags | Path 2 | Created in the app, stored in SQLite, and never model-visible. |
| Newsletter preferences | Path 2 | Created in the app, stored in SQLite, and used for app-side filtering only. |
| Clean shared intake files | Path 2 | `sources/`, `links.csv`, and `users.csv` stay minimal and free of comment/preference metadata. |
| Prompt/data boundary enforcement | Path 3 | Agent workflows receive only approved `agent_visible` fields. |
| Automated privacy negative tests | Path 3 | Prove forbidden fields never enter prompts, wiki, answers, or newsletter previews. |
| Agent run metadata audit logs | Path 3 | Log run metadata and source IDs, not full prompts by default. |
| Excel compatibility | Path 4 | `.xlsx` import/export or workbook compatibility for link intake and user registry data. |
| Demo hardening and seed data | Path 4 | Adds sample dataset, reset/rebuild flows, setup polish, and better error handling. |
| LLM-wiki lint/health check | Later | Scans generated wiki only for stale claims, contradictions, or missing links. |

## 3. Phased Delivery

### Path 1: Public Knowledge Base PoC

Path 1 proves the core Knowledge Base experience without users or private collaboration data.

Required capabilities:

- Add documents through a shared `sources/` folder and through UI upload.
- Add web links through `links.csv` and through the UI.
- Support PDF, DOCX, text files, and public web links.
- Run manual resync to detect new or changed sources.
- Assign app-generated `source_id` values during resync.
- Store source registry state in SQLite.
- Keep the same `source_id` when a registered document changes; mark it stale and reingest it.
- Extract source text into sanitized artifacts keyed by `source_id`.
- Generate summaries, public tags, per-source wiki pages, topic/tag pages, `wiki/index.md`, and `wiki/log.md`.
- Browse, search, filter, and sort available sources.
- Ask questions over the generated wiki plus simple search.
- Generate newsletter previews from selected topics/tags.
- Show safe citations in answers and newsletter previews.

Path 1 non-goals:

- No real authentication.
- No users, private comments, private tags, or newsletter subscriptions.
- No real email sending.
- No filesystem watcher.
- No vector database requirement.
- No production security guarantee.

### Path 2: App-Managed Collaboration Layer

Path 2 adds human collaboration records while preserving the rule that private collaboration data is not model-visible. Shared files remain clean intake and registry surfaces; comments, private tags, and preferences are created and managed inside the app.

Required capabilities:

- Add `users.csv` as the canonical user registry.
- Require user email addresses to be unique.
- Let users identify themselves locally in the UI without real authentication.
- Store private comments, private tags, and newsletter preferences in SQLite.
- Require private comments, private tags, and newsletter preferences to be edited through the app UI.
- Keep `sources/`, `links.csv`, and `users.csv` minimal and free of app-managed collaboration metadata.
- Keep private collaboration data human-facing only.

Path 2 non-goals:

- No password, OAuth, SSO, or production auth.
- No use of private comments, private tags, users, emails, or user preferences in model prompts.
- No private-data-driven agent answers or newsletters.
- No direct spreadsheet/CSV editing for private comments, private tags, or newsletter preferences.

### Path 3: Privacy Guardrails and Enforcement

Path 3 turns the intended privacy boundary into enforceable behavior.

Required capabilities:

- Add automated negative tests proving `app_internal` and `private_sensitive` fields never appear in prompts, generated wiki content, Q&A answers, or newsletter previews.
- Add prompt/input construction boundaries so agent workflows receive only approved `agent_visible` fields.
- Add metadata audit logs for model/agent runs.
- Log run ID, workflow type, source IDs used, status, timestamps, and error class where relevant.
- Do not log full prompts by default.
- Ensure source citations generated by the model use safe source handles only.

Path 3 non-goals:

- No full production access-control model.
- No deployment-grade security certification.
- No guarantee that humans cannot manually copy private data into public source documents.

### Path 4: Excel Compatibility and Demo Hardening

Path 4 adds compatibility, polish, and stronger demo readiness.

Required capabilities:

- Support `.xlsx` import/export or workbook compatibility for link intake and user registry data.
- Preserve the same data classification and model-visibility rules for Excel-backed records.
- Provide a small seed dataset that proves ingestion, browsing, Q&A, and newsletter preview.
- Improve validation, reset/rebuild flows, error messages, and demo setup.
- Keep CSV as the initial canonical shared format unless a later design explicitly replaces it.

### Later: LLM-wiki Lint and Health Check

The lint operation is a committed later capability, not a Path 1 blocker.

Required capabilities:

- Scan generated wiki pages for stale claims, contradictions, orphan pages, missing cross-references, missing topic pages, and source coverage gaps.
- Produce a human-readable health report.
- Suggest safe wiki maintenance actions.
- Never inspect or use private collaboration data.

## 4. Shared Repository and Knowledge Base Architecture

The shared repository is the product's portable source of truth. Users and beta testers should be able to share this directory through a filesystem, shared drive, synced folder, or repository-like workflow.

Recommended layout:

```text
research-watch-root/
  sources/
    ...
  extracted/
    src_...txt
  wiki/
    index.md
    log.md
    sources/
    topics/
    tags/
  links.csv
  users.csv
  app.sqlite
```

`wiki/sources/` contains generated per-source wiki pages such as `wiki/sources/src_abc123.md`. These are not raw source files; they are agent-generated summaries and synthesis pages keyed by safe `source_id` values.

Path 1 requires `sources/`, `extracted/`, `wiki/`, `links.csv`, and `app.sqlite`. Later paths add `users.csv` records and additional SQLite tables for app-managed collaboration records.

Shared files have intentionally narrow roles:

- `sources/`: human-editable document intake.
- `links.csv`: human-editable public link intake.
- `users.csv`: human-editable user registry with `name` and unique `email`.
- `app.sqlite`: app-managed state, including source registry records, local document paths, content hashes, ingest status, private comments, private tags, newsletter preferences, audit metadata, cache/index data, and run metadata.

Users may add sources outside the UI only by dropping documents into `sources/` or adding public links to `links.csv`. Users may edit the user registry outside the UI only through `users.csv`. All comments, private tags, and newsletter preferences must be created and edited in the app.

### SQLite Source Registry vs Wiki Index

The canonical source registry lives in `app.sqlite`, not in a CSV file. It stores app-managed source records, including stable source IDs, source type, source location, content hash, ingest lifecycle status, generated summary, generated public tags, and generated wiki page references.

The source registry intentionally contains mixed-visibility fields. Some fields are `agent_visible`, such as source ID, source type, safe title, generated public summary, generated public tags, and wiki page references. Other fields are `app_internal`, such as full local document paths, content hashes, parser metadata, run IDs, and internal error details.

`wiki/index.md` is a sanitized agent-readable projection. It helps humans and the agent navigate the generated wiki, but it is not the operational source registry.

The agent may read generated wiki files and sanitized source metadata derived by the app. The agent must not receive local document paths, content hashes, parser internals, user data, private annotations, private tags, newsletter preferences, or raw SQLite records.

### Source Identity

Source IDs are app-generated. Users may manually add documents without IDs and may add link rows without IDs. During resync, the app assigns missing IDs and records each source in the SQLite source registry. The app does not need to write source IDs back into `links.csv`.

Matching rules:

- Documents are matched by existing registry record, normalized relative location, and content hash.
- Links are matched by existing SQLite registry record or normalized public URL.
- Changed documents keep the same `source_id`, receive an updated content hash, and become `stale` until reingested.
- Ambiguous duplicates are reported for human review instead of silently merged.

### Data Classification

Every product entity and field should be classified with one of these categories:

| Classification | Meaning | Examples |
| --- | --- | --- |
| `agent_visible` | May appear in prompts, generated wiki pages, Q&A answers, and newsletter previews. | source ID, source type, safe title, public URL, extracted document content, public summary, public tags |
| `app_internal` | App/backend may use it; model must not see it. | full local path, content hash, ingest run ID, parser error detail, cache keys, SQLite index metadata |
| `private_sensitive` | Human/user collaboration data; model must never see it. | names, emails, private comments, private tags, user preferences, sensitive project annotations |

Important privacy rules:

- Full local document paths are never available to the model.
- Human users may see full local paths in the UI.
- Filenames and titles may be model-visible when treated as safe display metadata.
- Public web URLs may be model-visible and may appear in citations.
- Full extracted document content is model-visible for ingestion and Q&A.
- Private comments, private tags, user identities, user emails, and newsletter preferences never influence agent-generated answers or newsletters.

## 5. Product Requirements

### Source Intake and Resync

Users can add sources in two ways:

- Drop supported documents into `sources/`.
- Add public web links to `links.csv` or through the UI.

The app provides a manual resync action. Resync scans shared inputs, validates CSV rows, assigns missing source IDs, detects changed content, updates lifecycle status, and queues sources for ingestion.

Malformed or conflicting CSV rows are validated and reported. Valid rows continue processing; invalid rows are skipped without failing the entire sync.

Supported lifecycle statuses:

- `pending`: detected but not yet ingested.
- `ingesting`: currently being processed.
- `ingested`: successfully represented in the Knowledge Base.
- `stale`: source content changed after ingestion.
- `failed`: attempted ingestion failed.
- `skipped_invalid`: row/source could not be processed because of validation errors.

Public web links only are required for Path 1. Blocked, paywalled, login-only, or inaccessible pages are marked failed or needs-manual-content.

Shared intake files should remain clean and minimal. `links.csv` must not be used for private comments, private tags, user-specific notes, or newsletter preferences. Document files in `sources/` should remain raw source documents, not app metadata containers.

### Browsing and Source Detail

Users can browse all registered sources with title, type, date added, ingest status, summary, public tags, and safe citation metadata.

Users can:

- Search by title, summary, and public tags.
- Filter by type, tag, and status.
- Sort by title, date added, and status.
- Open original documents through app-resolved paths.
- Open public web URLs directly.

The model may cite title and `source_id`; the app resolves local document paths separately for the UI.

### LLM-wiki Generation

The app uses the LLM-wiki pattern from `llm-wiki.md`: raw sources are treated as source truth, and the agent maintains a persistent generated markdown wiki that compounds knowledge over time.

Required generated artifacts:

- `wiki/index.md`: sanitized content-oriented index.
- `wiki/log.md`: chronological append-only activity log.
- Per-source summary pages.
- Topic pages.
- Tag pages.
- Cross-links between related sources, topics, and tags.

The wiki is agent-owned generated content. Users can read it, but normal app workflows should treat agent workflows as responsible for keeping it consistent.

### Q&A

Users can ask questions about the Knowledge Base. Path 1 Q&A uses generated wiki files, source summaries, public tags, and simple text search. Vector search is not required in Path 1.

Answers must:

- Use only `agent_visible` content.
- Cite title and `source_id`.
- Include public URL citations for public web links when useful.
- Never include full local document paths.
- Never use private comments, private tags, users, emails, or user preferences.

The agent may reread extracted source content when needed or requested, but the app must provide content through safe source IDs, not local paths.

### Newsletter Preview

Users can select topics/tags and generate a newsletter preview in the UI.

Path 1 newsletter previews:

- Are generated on demand.
- Are not emailed.
- Do not require users or subscriptions.
- Include safe citations using title and `source_id`.
- May include public URLs for public web links.
- Never include local document paths.

Later phases add user newsletter preferences in SQLite, but those preferences remain `private_sensitive` and must not be sent to the model. The app may use preferences to select eligible source IDs before invoking a newsletter workflow, but the model must not receive user identity or preference records.

### Collaboration Layer

In Path 2 and later, collaboration data is app-managed and edited only through the UI. The shared repository still contains clean intake files, but private collaboration records live in SQLite.

Entities:

- `User`: name and unique email in `users.csv`.
- `PrivateAnnotation`: source ID, user email, comment, created/updated timestamps in SQLite.
- `PrivateTag`: source ID, user email, private tag, created/updated timestamps in SQLite.
- `NewsletterPreference`: user email and topic/tag selection in SQLite.

All user and collaboration entities are `private_sensitive`. They are for human collaboration and app-side filtering only. They must not be included in prompts, wiki pages, Q&A answers, newsletter model calls, or agent-readable logs.

The UI may show comments, private tags, and attribution to human users. These records must not be exported into `links.csv`, generated wiki pages, source documents, or any other agent-readable artifact.

## 6. Product-Level Schema

The PRD defines product-level entities and visibility rules. Exact database tables, migrations, and API payloads belong in later technical design.

### Source

Represents a document or web link known to the app. Source records are stored in SQLite.

| Field | Classification | Notes |
| --- | --- | --- |
| `source_id` | `agent_visible` | App-generated stable ID. |
| `type` | `agent_visible` | `document` or `link`. |
| `title` | `agent_visible` | Safe display title. |
| `original_path` | `app_internal` | Full local path for documents. Never model-visible. |
| `original_url` | `agent_visible` | Public URL for web links. |
| `content_hash` | `app_internal` | Used for freshness detection. |
| `date_added` | `agent_visible` | Safe metadata. |
| `last_ingested_at` | `app_internal` | Operational status metadata. |
| `ingest_status` | `agent_visible` | Lifecycle status shown in UI. |
| `agent_summary` | `agent_visible` | Generated public summary. |
| `agent_tags` | `agent_visible` | Generated public tags. |
| `wiki_pages` | `agent_visible` | Sanitized wiki page references. |

### Link Row

Represents a user-editable link input in `links.csv`. Link rows should stay minimal; source IDs and ingest state are stored in SQLite.

| Field | Classification | Notes |
| --- | --- | --- |
| `url` | `agent_visible` | Public URL only in Path 1. |
| `title` | `agent_visible` | Optional user-provided title. |

### Extracted Text

Represents sanitized text extracted from a source.

| Field | Classification | Notes |
| --- | --- | --- |
| `source_id` | `agent_visible` | Links extracted content to source. |
| `content_text` | `agent_visible` | Full source content is allowed in model calls. |
| `extraction_metadata` | `app_internal` | Parser details, errors, or internal diagnostics. |

### Wiki Page

Represents generated markdown wiki content.

| Field | Classification | Notes |
| --- | --- | --- |
| `page_path` | `agent_visible` | Path under `wiki/`, not raw source path. |
| `title` | `agent_visible` | Page title. |
| `related_source_ids` | `agent_visible` | Safe source references. |
| `tags` | `agent_visible` | Public/generated tags. |
| `content` | `agent_visible` | Generated public wiki content. |

### User

Represents a human collaborator in `users.csv`.

| Field | Classification | Notes |
| --- | --- | --- |
| `name` | `private_sensitive` | Human-facing only. |
| `email` | `private_sensitive` | Unique canonical user key. |

### Private Annotation, Private Tag, Newsletter Preference

Represents later app-managed collaboration data stored in SQLite.

| Field | Classification | Notes |
| --- | --- | --- |
| `source_id` | `private_sensitive` | Private record association to a public source. |
| `user_email` | `private_sensitive` | Links to `users.csv`. |
| `comment` | `private_sensitive` | Private annotation text. |
| `private_tag` | `private_sensitive` | User/company-sensitive tag. |
| `topic_or_tag` | `private_sensitive` | Newsletter preference selection. |
| `created_at` / `updated_at` | `private_sensitive` | Private collaboration metadata. |

## 7. Agent Workflows

LangGraph is the recommended default orchestration framework for backend agent workflows. The PRD does not require exact graph nodes and edges, but each workflow must define inputs, outputs, allowed data classes, and success criteria.

### Resync Workflow

Inputs:

- Shared repository root.
- `links.csv`.
- `sources/` document folder.
- Existing SQLite source registry.

Steps:

- Scan documents and link rows.
- Validate CSV shape and required fields.
- Assign missing source IDs.
- Detect new, changed, stale, failed, and invalid sources.
- Update SQLite source registry and lifecycle status.

Outputs:

- Updated SQLite source registry.
- Validation report.
- Queue/list of sources requiring ingestion.

Allowed data:

- May use `app_internal` fields inside the app/backend.
- Must not send `app_internal` or `private_sensitive` fields to the model.

### Ingest Workflow

Inputs:

- Source ID.
- Source type.
- Safe title.
- Public URL for web links.
- Extracted source content.
- Existing sanitized wiki index and relevant wiki pages.

Steps:

- Extract or fetch readable content.
- Persist sanitized extracted text.
- Summarize source.
- Generate public tags.
- Create/update per-source wiki page.
- Create/update topic and tag pages.
- Update `wiki/index.md`.
- Append to `wiki/log.md`.
- Update ingest status.

Outputs:

- Source summary.
- Public tags.
- Generated/updated wiki pages.
- Updated safe index and log.

Allowed data:

- May use full document content.
- May use public URL content.
- Must not use full local paths, content hashes, private comments, private tags, users, emails, or preferences.

### Query Workflow

Inputs:

- User question.
- Sanitized wiki pages.
- Safe source metadata.
- Extracted content for relevant source IDs when needed.

Steps:

- Search wiki index, summaries, public tags, and extracted text.
- Select relevant source IDs and wiki pages.
- Generate answer grounded in available content.
- Return safe citations.

Outputs:

- Answer text.
- Citations by title and `source_id`.
- Public URLs where appropriate.

Allowed data:

- Only `agent_visible` data.

### Newsletter Workflow

Inputs:

- Selected public topics/tags.
- Matching source IDs.
- Safe summaries, public tags, wiki pages, and extracted content as needed.

Steps:

- Select relevant public source material.
- Generate a readable newsletter preview.
- Include safe citations.

Outputs:

- Newsletter title.
- Newsletter body.
- Safe source list.

Allowed data:

- Only `agent_visible` data.
- Later phases may use SQLite-stored user preferences app-side to choose source IDs, but the model must not receive user or preference records.

### Lint Workflow

Inputs:

- Generated wiki files.
- Safe source registry projection.
- Public source summaries/tags.

Steps:

- Detect stale pages, contradictions, orphan pages, missing cross-links, missing concepts, and coverage gaps.
- Produce a health report and proposed maintenance actions.

Outputs:

- Wiki health report.
- Suggested safe updates.

Allowed data:

- Only `agent_visible` data.

## 8. Technology Defaults

These are recommended defaults for the demo implementation. Later technical design may refine specific packages, APIs, or folder structure while preserving the product requirements.

- Frontend: React.
- Backend: Python with FastAPI.
- Agent orchestration: LangGraph.
- Model provider: OpenAI-compatible chat/model APIs configured through environment variables.
- Shared intake and generated files: raw source files, `links.csv`, `users.csv`, extracted text files, and generated markdown wiki.
- App-managed SQLite: canonical store for source registry records, private comments, private tags, newsletter preferences, audit metadata, cache/index data, run metadata, and UI performance state.
- Search in Path 1: generated wiki plus simple text search.
- Search later: vector search may be added if needed, but it is not required for Path 1.
- Excel: required later as import/export or workbook compatibility for link intake and user registry data.

## 9. Acceptance Criteria

### Path 1 Acceptance

- Dropping a supported document into `sources/` and running resync creates or updates a SQLite source registry record.
- Adding a row to `links.csv` causes resync to assign a stable source ID in SQLite.
- Invalid CSV rows are reported and skipped without failing the entire sync.
- Supported documents and public links are extracted, summarized, tagged, and represented in the generated wiki.
- Changed documents keep the same source ID, become stale, and can be reingested.
- Browse/search/filter/sort works over registered sources.
- Q&A answers cite safe title and source ID.
- Q&A answers never include full local paths.
- Newsletter preview includes safe citations.
- A small seed dataset proves ingest, browse, Q&A, and newsletter flows.

### Path 2 Acceptance

- `users.csv` stores users with unique email addresses.
- `users.csv` contains only `name` and `email`.
- Private annotations, private tags, and newsletter preferences are created and edited only through the UI.
- Private annotations, private tags, and newsletter preferences are stored in SQLite.
- `links.csv` remains free of private comments, private tags, attribution columns, and newsletter preferences.
- Private records remain human-facing only.
- Agent workflows do not receive private collaboration data.

### Path 3 Acceptance

- Automated negative tests verify `app_internal` and `private_sensitive` fields do not appear in constructed prompts.
- Automated negative tests verify forbidden fields do not appear in generated wiki pages, Q&A answers, or newsletter previews.
- Metadata audit logs record model/agent run ID, workflow type, source IDs used, status, and timestamps.
- Full prompts are not logged by default.

### Path 4 Acceptance

- `.xlsx` import/export or workbook compatibility works for link intake and user registry data.
- Excel compatibility preserves the same field classifications and model-visibility rules as CSV.
- Demo reset/rebuild flow can recreate cache/index tables from canonical shared files, SQLite source records, and wiki artifacts.
- Seed data and setup instructions allow a new tester to run the demo quickly.

## 10. Open Decisions for Later Technical Design

- Exact React app structure and component system.
- Exact FastAPI route design.
- Exact CSV column order and validation schema for `links.csv` and `users.csv`.
- Exact SQLite schema for source registry records, private annotations, private tags, newsletter preferences, audit metadata, and cache/index data.
- Exact source ID format.
- Exact extracted text file format.
- Exact markdown page templates.
- Exact LangGraph graph nodes, state objects, and persistence/checkpointer choices.
- Whether vector search is needed after Path 1.
- Whether Excel becomes a canonical intake/user-registry format or remains compatibility import/export.
- Deployment, real authentication, and production access control.

## 11. References

- `llm-wiki.md`: project seed document describing the LLM-wiki architecture and operations.
- LangGraph documentation: recommended reference for stateful agent workflow orchestration, including workflow/agent patterns and persistence concepts.

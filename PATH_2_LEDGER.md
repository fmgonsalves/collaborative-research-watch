# Path 2 Progress Ledger

This ledger tracks implementation progress for Path 2: per-source AI enrichment.

Use `PATH_2_DESIGN.md` as the stable design/spec and `PATH_2_BUILD_ORDER.md` as the intended build sequence. This ledger records decisions, completed implementation work, test results, and remaining scope.

## Decisions Made

- Keep AI as bounded per-source enrichment, not a wiki, topic graph, RAG system, or cross-source synthesis layer.
- Store AI records as app-managed Markdown files with YAML frontmatter under `records/ai/`.
- Use `{source_id}.md` filenames for AI records, for example `records/ai/src_abc123.md`.
- Treat AI records as rebuildable enrichment outputs, not canonical human collaboration data; migrations should preserve existing AI records unless the user explicitly approves discarding or regenerating them.
- Store the AI summary in the Markdown body, not frontmatter.
- Keep `extractor` and `model` as optional top-level AI record fields so pre-model failures do not need placeholder model values.
- Report malformed AI records as validation issues and skip them instead of crashing callers.
- Build AI-safe model input as a structured typed payload first, not prompt text.
- Include only the filename basename for document source file metadata in AI-safe input; omit folders and full paths.
- Extract `.txt`, `.md`, and `.csv` content as raw decoded UTF-8 text in Step 4; do not strip Markdown syntax or reformat CSV rows.
- Extract PDF text with `pypdf` first; for PDFs longer than 50 pages, inspect only the first 50 pages instead of failing the whole extraction.
- Treat the first enrichment pass as document-based only; link enrichment returns `409` and writes no AI record until link fetching and HTML extraction exist.
- Use a deterministic local fake generator for Step 6 so API, extraction, AI-safe input, and AI record writing can be proven before model-provider work.
- Show AI enrichment in source detail before adding AI browse/search/filter behavior; link sources show a disabled generate action until link fetching exists.

## Build Steps

- [completed] Step 1: AI record storage.
- [completed] Step 2: Source detail AI loading.
- [completed] Step 3: AI-safe input boundary.
- [completed] Step 4: Simple text extractors.
- [completed] Step 5: PDF extractor.
- [completed] Step 6: Fake enrichment endpoint.
- [completed] Step 7: Source detail UI.
- [pending] Step 8: Real model adapter.
- [pending] Step 9: Browse/search/filter over AI fields.
- [pending] Step 10: DOCX extractor.
- [pending] Step 11: Link fetching and HTML extraction.

## Built Or Changed

- Added the Path 2 implementation ledger.
- Added typed AI record storage models for Path 2 Step 1.
- Added backend AI record read/write helpers for `records/ai/{source_id}.md`.
- Updated the Path 2 design filename example to use `{source_id}.md` instead of a double-prefixed path.
- Added backend source-detail loading for existing AI records through a nested `ai` response object.
- Kept AI-generated tags separate from `human_tags` and human tag records in source detail.
- Log malformed source-specific AI records as `invalid_ai_record` warnings while keeping source detail usable with `ai: null`.
- Added a backend AI-safe input boundary that converts source records plus extracted/fetched text into a typed `source_public` payload.
- Limited document file metadata in AI-safe input to the filename basename.
- Kept prompt rendering, model calls, extraction, API routes, and UI behavior out of Step 3.
- Added backend simple-text extraction for `.txt`, `.md`, and `.csv` using raw decoded text.
- Added safe extraction failure results for unsupported formats and unreadable/undecodable files.
- Kept extraction diagnostics separate from extracted text and AI-safe input.
- Added backend PDF extraction through the same extraction boundary using `pypdf`.
- Limited PDF extraction to the first 50 pages while still treating readable long PDFs as successful bounded extractions.
- Added safe PDF failures for malformed PDFs and PDFs with no readable text in the inspected pages.
- Added `backend/scripts/smoke_pdf_extract.py` for optional developer smoke testing of real PDF extraction with `uv run scripts/smoke_pdf_extract.py /path/to/file.pdf`.
- Added `POST /api/sources/{source_id}/ai/enrich` for manual document enrichment with deterministic fake output.
- Added safe `409` rejection for link enrichment until link fetching is implemented.
- Added safe extraction-failure AI record writing for missing, unsafe, unreadable, or unsupported document extraction cases.
- Kept manual sync separate from enrichment; sync does not create or update AI records.
- Added source-detail UI for AI enrichment status, AI-generated tags, summary text, and safe error summaries.
- Added a manual document-only `Generate AI` action that calls the fake enrichment endpoint and refreshes source detail.
- Kept link enrichment visible but disabled in the UI until link fetching and HTML extraction exist.

## Automated Tests Added And Passing

- Added backend unit tests for AI record frontmatter/body round trips.
- Added backend unit tests for success and failure AI record statuses.
- Added backend unit tests for invalid AI record validation issues.
- Added backend unit test proving missing AI records return no record and no issues.
- Reran backend tests after Step 1 storage work: 24 passed, 1 warning.
- Added backend API tests for generated AI detail, failed AI detail, missing AI detail, and human/AI tag separation.
- Added backend repository test proving malformed AI detail records are skipped and logged without crashing source detail.
- Reran backend tests after Step 2 source-detail loading: 28 passed, 1 warning.
- Added backend unit tests proving AI-safe input includes approved document/link fields.
- Added backend negative tests proving comments, human-created tags, users, emails, selected identity, full paths, folder names, size/mtime, diagnostics, raw errors, cache details, and run internals stay out of serialized AI-safe input.
- Reran backend tests after Step 3 AI-safe input boundary: 33 passed, 1 warning.
- Added backend unit tests for `.txt`, `.md`, and `.csv` raw text extraction, unsupported extension failure, bad encoding failure, and extraction-to-AI-safe-input flow.
- Reran backend tests after Step 4 simple text extractors: 40 passed, 1 warning.
- Added backend unit tests for PDF text extraction, first-50-pages extraction, no-text PDF failure, malformed PDF failure, and PDF diagnostics isolation.
- Reran targeted extractor tests after Step 5 PDF extraction: 12 passed.
- Reran backend tests after Step 5 PDF extraction: 45 passed, 1 warning.
- Added backend API tests for unknown-source enrichment, link `409` behavior, generated fake AI records, source-detail loading after enrichment, safe extraction failures, path-safety failures, confidentiality exclusions, and manual-sync non-enrichment.
- Reran targeted API tests after Step 6 fake enrichment endpoint: 18 passed, 1 warning.
- Reran backend tests after Step 6 fake enrichment endpoint: 52 passed, 1 warning.
- Reran frontend build after Step 7 source detail AI UI: passed.

## Automated Test Scope Remaining

- DOCX extraction tests are deferred until after the first end-to-end enrichment pass is proven.
- Link fetching and HTML extraction tests are deferred until after the first document-based enrichment pass is proven.
- Browse/search/filter tests for AI fields are deferred until Step 9.

## Manual/User Test Scope Remaining

- Step 7 manual browser verification passed: document generation worked, link generation was disabled, and human-created tags remained visually separate from AI-generated tags.

## Known Gaps, Risks, Follow-Ups

- Source removal does not yet cascade AI records; this is deferred until AI records are integrated into source detail and sync behavior.
- AI records are exposed through source-detail API responses and source-detail frontend display, but not yet browse/search/filter.
- User-visible malformed-AI-record diagnostics are deferred until the frontend has an AI section or broader diagnostics surface; Step 2 logs invalid records.
- DOCX extraction is intentionally deferred until after the first end-to-end enrichment pass.
- Link fetching and HTML extraction are intentionally deferred until after the first document-based enrichment pass; link enrichment returns `409` in the meantime.
- Prompt rendering and model-provider code do not exist yet.

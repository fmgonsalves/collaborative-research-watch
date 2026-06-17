# Path 2 Progress Ledger

This ledger tracks implementation progress for Path 2: per-source AI enrichment.

Use `PATH_2_DESIGN.md` as the stable design/spec and `PATH_2_BUILD_ORDER.md` as the intended build sequence. This ledger records decisions, completed implementation work, test results, and remaining scope.

## Decisions Made

- Keep AI as bounded per-source enrichment, not a wiki, topic graph, RAG system, or cross-source synthesis layer.
- Store AI records as app-managed Markdown files with YAML frontmatter under `records/ai/`.
- Use `{source_id}.md` filenames for AI records, for example `records/ai/src_abc123.md`.
- Treat AI records as rebuildable enrichment outputs, not canonical human collaboration data.
- Store the AI summary in the Markdown body, not frontmatter.
- Keep `extractor` and `model` as optional top-level AI record fields so pre-model failures do not need placeholder model values.
- Report malformed AI records as validation issues and skip them instead of crashing callers.

## Build Steps

- [active] Step 1: AI record storage.
- [pending] Step 2: Source detail AI loading.
- [pending] Step 3: AI-safe input boundary.
- [pending] Step 4: Simple text extractors.
- [pending] Step 5: PDF extractor.
- [pending] Step 6: DOCX extractor.
- [pending] Step 7: Fake enrichment endpoint.
- [pending] Step 8: Source detail UI.
- [pending] Step 9: Real model adapter.
- [pending] Step 10: Browse/search/filter over AI fields.

## Built Or Changed

- Added the Path 2 implementation ledger.
- Added typed AI record storage models for Path 2 Step 1.
- Added backend AI record read/write helpers for `records/ai/{source_id}.md`.
- Updated the Path 2 design filename example to use `{source_id}.md` instead of a double-prefixed path.

## Automated Tests Added And Passing

- Added backend unit tests for AI record frontmatter/body round trips.
- Added backend unit tests for success and failure AI record statuses.
- Added backend unit tests for invalid AI record validation issues.
- Added backend unit test proving missing AI records return no record and no issues.
- Reran backend tests after Step 1 storage work: 24 passed, 1 warning.

## Automated Test Scope Remaining

- Source detail API tests for loading AI records are deferred to Step 2.
- AI-safe input negative tests are deferred to Step 3.
- Extraction tests are deferred to extractor steps.
- Enrichment endpoint tests are deferred until fake enrichment endpoint work.

## Manual/User Test Scope Remaining

- No manual browser verification is needed for Step 1 because it is backend storage only.

## Known Gaps, Risks, Follow-Ups

- Source removal does not yet cascade AI records; this is deferred until AI records are integrated into source detail and sync behavior.
- AI records are not yet exposed through API responses or the frontend.
- No extraction, prompt construction, or model-provider code exists yet.

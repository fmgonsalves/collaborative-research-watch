# Path 2 Build Order

This build order breaks Path 2 into small, testable objectives. Prefer thin vertical slices that prove storage, boundaries, and failure handling before adding richer extraction or model behavior.

## 1. AI Record Storage

Build `records/ai/src_*.md` read/write support before extraction or model calls.

Tests:

- AI record round-trips YAML frontmatter and Markdown body.
- Generated, extraction-failed, fetch-failed, and generation-failed statuses serialize cleanly.
- Missing AI records do not break existing source detail behavior.

Done when:

- The app can read and write AI records deterministically without changing Path 1 source, comment, or human-tag records.

## 2. Source Detail AI Loading

Extend backend source detail data to include AI summary, AI-generated tags, and AI status when an AI record exists.

Tests:

- Source detail includes AI fields when an AI record exists.
- Source detail still works when no AI record exists.
- Human-created tags and AI-generated tags remain structurally separate.

Done when:

- Existing source detail API consumers still work and AI fields are additive.

## 3. AI-Safe Input Boundary

Build the testable function that converts source-public metadata plus extracted text into model input.

Tests:

- Includes allowed `source_public` fields.
- Excludes comments, human-created tags, user names, user emails, selected user identity, full local paths, size/mtime, parser diagnostics, raw app errors, and app-internal run details.

Done when:

- Negative tests prove forbidden fields cannot enter model input.

## 4. Simple Text Extractors

Implement the generic extraction shape with low-risk formats first.

Formats:

- `.txt`
- `.md`
- `.csv`

Tests:

- Supported text formats produce normalized extracted text.
- Bad encoding or unreadable input produces a safe extraction failure.
- Internal diagnostics stay out of AI-safe input.

Done when:

- The extraction boundary works without depending on PDF/DOCX libraries.

## 5. PDF Extractor

Implement PDF extraction with `pypdf` first. Keep the extraction boundary generic so another PDF implementation can replace it later.

Tests:

- Extracts text from a simple fixture PDF.
- Handles empty, scanned, or no-text PDFs safely.
- Parser exceptions are captured as internal diagnostics and safe error summaries.
- Raw parser errors do not enter model input or AI record body.

Done when:

- PDF sources can produce safe extracted text or a safe extraction failure.

## 6. DOCX Extractor

Implement DOCX extraction with `python-docx`.

Tests:

- Extracts paragraph text from a fixture DOCX.
- Handles empty or malformed DOCX files safely.
- Internal diagnostics stay out of AI-safe input.

Done when:

- DOCX sources can produce safe extracted text or a safe extraction failure.

## 7. Fake Enrichment Endpoint

Add the enrichment API without calling a real model. Use a deterministic fake generator to prove API, storage, and failure behavior.

Endpoint:

- `POST /api/sources/{source_id}/ai/enrich`

Tests:

- Unknown source returns `404`.
- Valid source writes an AI record.
- Extraction failure writes a failure AI record.
- Manual sync does not call enrichment.
- Existing Path 1 tests continue passing.

Done when:

- The app can manually enrich one source end-to-end using deterministic fake output.

## 8. Source Detail UI

Display AI enrichment on source detail.

UI behavior:

- Show AI summary in a separate AI-labeled section.
- Show AI-generated tags separately from human-created tags.
- Show AI status or safe error summary when enrichment fails.

Tests:

- Frontend build succeeds.
- Browser verification only when explicitly approved for the current task.

Done when:

- Users can distinguish human collaboration data from AI-generated enrichment.

## 9. Real Model Adapter

Add the real model call behind the same generation boundary used by the fake generator.

Tests:

- Provider calls are mocked in automated API tests.
- Provider errors write `generation_failed`.
- Mocked provider input contains only AI-safe fields.
- Prompt construction tests remain provider-independent.

Done when:

- One-source manual enrichment can call the configured model and write a valid AI record.

## 10. Browse/Search/Filter Over AI Fields

Add AI fields to browse/search/filter only after AI record read/write/display is stable.

Tests:

- Search can match AI summary text.
- AI-generated tag filtering works separately from human-created tag filtering.
- Human-created tag autocomplete remains human-only.

Done when:

- AI-generated metadata improves discovery without merging with human collaboration data.

## Ordering Notes

- Do not build all extractors before proving AI record storage and data-boundary tests.
- Do not add real model calls before the fake enrichment endpoint works.
- Do not let manual sync call enrichment in Path 2 v1.
- PDF comes before DOCX by default because the initial extraction-tool discussion centered on PDF. Swap these two only if real workspace priorities make DOCX more urgent.

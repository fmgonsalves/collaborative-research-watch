# Merge Conflict Ledger

Merge target: `origin/main` into `path-2-ai-enrichment`

Baseline:

- Current branch: `path-2-ai-enrichment`
- Current branch head before merge: `5c9222b32c6e04d1ab623361f381b0a4cc55df8b`
- Incoming `origin/main`: `3dce539a8d27c84755682f3e05c167a69e243494`
- Merge base: `5fc05f70fb7b95c5521e57e3a3c8f8c844b20563`

## Checklist

- [ ] Repository caching and AI enrichment integration
  - Files: `backend/src/research_watch/sync.py`.
  - `main` change: repository read caches, active repository reuse, sync fast path.
  - AI branch change: AI records, AI enrichment, AI browse/search/filter fields, link fetching.
  - Resolution: combined both by keeping repository read caches, intake snapshots, and fast sync behavior while preserving AI record reads, AI filters, AI tag suggestions, and document/link enrichment.
  - Impact: `API`, `model/schema types`.
  - Tests: targeted backend API/repository tests, then full backend suite.
  - Cache note: validate that source/comment/tag writes invalidate the right caches, active repository reuse resets on workspace selection, and AI record writes remain visible because AI records are read outside the source/comment/tag caches.
  - Validation finding: targeted API tests exposed a stale source-record cache on the enrichment endpoint after direct record-file edits; resolved by making enrichment read source records fresh before safety checks.
  - Status: validated with `uv run pytest tests/test_repository.py tests/test_api.py -q`.

- [ ] API repository reuse plus AI endpoints
  - Files: `backend/src/research_watch/api.py` auto-merged; verify behavior with tests.
  - `main` change: reusable active repository and reset on workspace selection.
  - AI branch change: AI enrichment endpoint, AI tag suggestions, AI filters.
  - Resolution: kept active repository reuse/reset with AI source filters, AI tag endpoint, and enrichment endpoint; enrichment refreshes source records before safety-sensitive extraction/fetching.
  - Impact: `API`.
  - Tests: targeted API tests.
  - Status: validated with `uv run pytest tests/test_api.py -q`.

- [ ] SourceRecord TODO/model comments
  - Files: `backend/src/research_watch/models.py`, `BACKLOG.md`.
  - `main` change: inline TODO comments for model cleanup.
  - AI branch change: expanded model types for AI enrichment.
  - Resolution: preserved AI model/status types, removed inline TODO comments, and moved durable follow-ups into `BACKLOG.md`.
  - Impact: `docs only` unless model fields actually change.
  - Tests: model/API tests if code changes.
  - Status: validated with `uv run pytest tests/test_repository.py tests/test_api.py -q`.

- [ ] Frontend browse panel
  - Files: `frontend/src/main.tsx`, `frontend/src/styles.css` auto-merged; verify behavior with build.
  - `main` change: Sources heading, style tweaks, source detail effect dependency cleanup.
  - AI branch change: AI filters, AI tag column, AI enrichment UI.
  - Resolution: kept auto-merge combining the Sources heading/effect cleanup with AI filters, AI tag column, and link-enabled Generate AI.
  - Impact: `API` compatibility assumptions only.
  - Tests: frontend build.
  - Status: validated with `bun run build`.

- [ ] Docs/schema docs
  - Files: `AGENTS.md`, `PRD.md`, `WORKSPACE_SCHEMA.md`, `README.md`, `PATH_2_DESIGN.md`, `PATH_2_LEDGER.md`, `PATH_2_BUILD_ORDER.md`, `BACKLOG.md`.
  - `main` change: expanded PRD schema docs and new `WORKSPACE_SCHEMA.md`.
  - AI branch change: completed Phase 2 docs, backlog, Path 2 ledgers.
  - Resolution: kept `WORKSPACE_SCHEMA.md`, updated stale Path 2-not-implemented wording, documented implemented AI record fields and safe failure records, and corrected PRD wording where it conflicted with implementation (`model` optional on failed records; failures write AI status rather than source lifecycle status).
  - Impact: `docs only`.
  - Tests: docs stale phrase scan and `git diff --check`.
  - Status: validated with stale-phrase scan and `git diff --check`.

## Validation Cadence

- After resolving `models.py`: stage the model/backlog/ledger edits, then defer validation until backend conflict markers are gone.
- After resolving `sync.py`: run targeted backend repository/API tests that exercise sync, source detail/listing, cache-sensitive writes, and AI enrichment visibility.
- After verifying the auto-merged `api.py`: run targeted API tests again if any API edits are needed.
- After verifying frontend auto-merges: run `bun run build` from `frontend/`.
- After docs/schema docs are reconciled: run stale-phrase scans and `git diff --check`.
- Before final merge commit: run full backend tests with `uv run pytest` from `backend/`, run frontend build, search for conflict markers, and ask for approval of the final merge summary.

## Final Validation

- Backend: `uv run pytest` from `backend/` passed, 78 tests.
- Frontend: `bun run build` from `frontend/` passed.
- Diff hygiene: `git diff --check` passed.
- Conflict markers: `rg -n "<<<<<<<|=======|>>>>>>>" .` returned no matches.

## Manual Testing

- User reported manual merged-app testing worked.
- Observation: adding a tag or comment logs a full sync and scan of unchanged sources because collaboration writes currently invalidate comment/tag caches and call `sync()` to refresh `index.md`. This is correct behavior, but noisy and potentially inefficient for larger workspaces.
- Follow-up recorded in `BACKLOG.md`: avoid full source-intake scans after comment/tag writes.

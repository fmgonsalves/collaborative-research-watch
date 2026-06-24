# Project Backlog

This backlog tracks cross-cutting known issues and follow-ups that should not be buried in phase-specific ledgers. Phase ledgers remain the detailed implementation history.

## Known Issues

- AI records do not cascade on source removal.
  - Area: sync/storage.
  - Source: `PATH_2_LEDGER.md`.
  - Notes: source removal currently cascades source records, comments, and human-created tags, but matching `records/ai/<source_id>.md` files remain.

## Follow-Ups

- Add user-visible diagnostics for malformed AI records.
  - Area: validation/UI.
  - Source: `PATH_2_LEDGER.md`.
  - Notes: malformed AI records are logged and skipped without crashing source detail or browse, but users do not yet see those diagnostics in the app.

- Improve public link extraction if the conservative first pass is not enough.
  - Area: AI enrichment/link fetching.
  - Source: `PATH_2_LEDGER.md`.
  - Notes: current link fetching does not include readability scoring, paywall bypassing, JavaScript rendering, authentication, CAPTCHA handling, or richer article extraction.

- Add chunking or richer token budgeting for long extracted/fetched content.
  - Area: AI generation.
  - Source: `PATH_2_LEDGER.md`.
  - Notes: model input is capped at the first 30,000 characters until chunking exists.

- Revisit source model shape.
  - Area: model/schema types.
  - Source: `origin/main` inline TODOs from `backend/src/research_watch/models.py`.
  - Notes: `SourceRecord` currently carries fields for both documents and links, which creates several optional fields. Consider splitting shared source metadata from document/link-specific fields if the model keeps growing.

- Tighten lifecycle status typing.
  - Area: model/schema types.
  - Source: `origin/main` inline TODOs from `backend/src/research_watch/models.py`.
  - Notes: `lifecycle_status` is currently a free string. Consider a `Literal` or enum if the active status set stabilizes beyond `available` and `changed`.

- Re-evaluate `last_seen_at`.
  - Area: model/schema types.
  - Source: `origin/main` inline TODOs from `backend/src/research_watch/models.py`.
  - Notes: confirm whether `last_seen_at` provides user or sync value beyond `updated_at`; remove it only with a workspace schema migration plan if it becomes unnecessary.

- Move `display_title_for_path` out of models if a better home emerges.
  - Area: code organization.
  - Source: `origin/main` inline TODOs from `backend/src/research_watch/models.py`.
  - Notes: the helper may fit better near sync/intake code, but it is harmless where it is today.

- Avoid full source-intake scans after comment/tag writes.
  - Area: sync performance and log noise.
  - Source: merge manual testing after repository caching landed.
  - Notes: comment/tag writes currently call `sync()` so `index.md` can refresh collaboration counts. Because collaboration caches are invalidated, the sync fast path does not run and the backend logs a scan of unchanged sources. This is correct today, but a narrower collaboration-index refresh would be quieter and scale better.

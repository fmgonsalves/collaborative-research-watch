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

# Path 1 Progress Ledger

This ledger tracks implementation progress for the Shared Research Collaboration MVP.

## Decisions Made

- Build a full local FastAPI + React app for Path 1.
- Use a user-entered absolute workspace path as the first app step.
- Read identity from `users.csv`; if missing, bootstrap it with one `name,email` row.
- Keep canonical app data in shared files: `sources/`, `links.csv`, `users.csv`, `records/`, and `index.md`.
- On resync, user-facing intake (`sources/`, `links.csv`) is the source of truth; stale app-managed records under `records/` are removed when intake entries disappear.
- Support document intake for `.pdf`, `.docx`, `.txt`, `.md`, and `.csv`.
- On resync, intake files (`sources/`, `links.csv`) supersede stale app records; removed intake entries delete `records/` source files and cascade comments/tags.
- Keep Path 1 free of AI, extraction, vector stores, authentication, roles, and filesystem watchers.

## Built Or Changed

- Created this progress ledger before feature implementation.
- Added backend project metadata with FastAPI, Pydantic, PyYAML, pytest, and HTTPX dependencies.
- Moved Python packaging metadata and `uv.lock` into `backend/` so backend commands run from the backend directory.
- Added backend models with explicit Path 1 record shapes.
- Added CSV helpers for `users.csv` and `links.csv`.
- Added Markdown frontmatter helpers for app-managed records.
- Added workspace initialization and first-user bootstrap behavior.
- Added filesystem repository sync, source record writes, human comment/tag writes, and generated `index.md`.
- Added FastAPI routes for workspace, users, sync, source browsing/detail, upload, links, comments, and tags.
- Added frontend project metadata, Vite config, React app, and CSS.
- Added frontend workspace-first flow, first-user bootstrap, user selection, resync, upload, link intake, browse/search/filter/sort, source detail, comments, and human-created tag forms.
- Added frontend edit controls for existing comments and human-created tags.
- Added explicit user selection after choosing an existing workspace so collaborators choose their identity before entering the main UI.
- Added human-created tag suggestions and tag autocomplete based on existing workspace tags.
- Added sync report details for created, changed, updated, and removed sources, including removal cascade counts for comments and tags.
- Added backend sync logging for startup, uploads, links, comments, tags, and resync operations.
- Updated document display-title generation so filename-derived titles are title-cased.
- Added React type dependencies and tightened the upload file loop.
- Added a README with backend-local and frontend-local run/test commands.
- Updated `.gitignore` for backend virtualenv/cache files and frontend dependency/build output.
- Removed old root `.venv` and `.pytest_cache` artifacts after moving the Python project boundary into `backend/`.
- Verified root Python artifacts are gone: no root `pyproject.toml`, `uv.lock`, `.venv`, or `.pytest_cache`.

## Automated Tests Added And Passing

- Added backend unit tests for workspace initialization, CSV validation, Markdown round trips, resync identity/change/removal behavior, unsupported documents, and separation of comments/tags from links/source records.
- Added backend API test for bootstrap, upload, link creation, browse/search/filter, detail, comments, tags, and generated index behavior.
- Ran backend tests once: 6 passed, 1 failed because document display titles stayed lowercase.
- Reran backend tests after the fix: 7 passed, 1 warning from FastAPI/Starlette TestClient dependency behavior.
- Ran frontend build once; it failed because React type packages were missing and upload `FileList` typing needed tightening.
- Installed frontend dependencies with Bun and reran the frontend build successfully.
- Added comment/tag edit UI after noticing the first frontend pass only exposed add/view.
- Final backend test run: 7 passed, 1 warning.
- Final frontend build run: succeeded.
- After moving Python metadata into `backend/`, reran backend tests from `backend/`: 7 passed, 1 warning.
- Verified backend-local uvicorn startup from `backend/`.
- Reran frontend build after the backend layout move: succeeded.
- Added backend API negative tests for unselected workspace, unknown source/comment/tag requests, invalid user registry, rejected uploads, and invalid request payloads.
- Reran backend tests after API hardening and user-selection changes: 19 passed, 1 warning.
- Reran frontend build after user-selection changes: succeeded.

## Automated Test Scope Remaining

- Broader malformed Markdown/frontmatter validation cases.
- Frontend tests are not yet added.
- Browser file chooser upload was not manually exercised because the current browser automation surface does not expose a file selection method; upload is covered by API test.

## Manual/User Tests Completed

- Opened the local React app in the in-app browser.
- Selected `/private/tmp/research-watch-smoke` as a workspace and confirmed workspace initialization.
- Bootstrapped first user `Ada Lovelace <ada@example.com>` from missing `users.csv`.
- Verified an existing workspace with `users.csv` now requires explicit user selection before entering the main UI.
- Added a link through the UI and confirmed it appeared in browse and detail views.
- Added and edited a human-created tag through the UI.
- Verified human-created tag autocomplete can reuse existing workspace tags.
- Added and edited a human comment through the UI.
- Verified search by comment text and filtering by human-created tag.
- Ran manual resync through the UI and confirmed the report updated.
- Verified generated `index.md` includes the source, human-created tag, and comment count.
- Verified `links.csv` stays limited to `url,title`.
- Verified source records do not contain human comment text or human-created tag values.
- Checked a narrow mobile viewport for basic layout presence.
- Verified desktop layout alignment, filter sizing, long source text handling, and table Type/Status spacing in the in-app browser.
- Verified unsupported source-file issues show the relevant file path and summarize hidden issues when there are more than four.

## Manual/User Test Scope Remaining

- None remaining per user confirmation.

## Known Gaps, Risks, Follow-Ups

- Backend dependencies installed successfully through `uv run pytest`.
- Backend tests pass with one FastAPI/Starlette TestClient deprecation warning from the installed dependency stack.
- The app stores selected workspace in backend process memory for Path 1; users reselect after backend restart.

---
name: research-watch-tests
description: Run the correct validation workflow for collaborative-research-watch. Use when testing, validating, running checks or builds, debugging CI-like failures, verifying code changes, or deciding which backend/frontend commands to run in this app.
---

# Research Watch Tests

## Commands

Run commands from the package directory that owns the tool config.

- Backend tests: run `uv run pytest` with workdir `backend/`.
- Targeted backend tests: run `uv run pytest tests/test_api.py -q` or a specific pytest node id with workdir `backend/`.
- Frontend validation: run `bun run build` with workdir `frontend/`.
- Full local validation: run backend pytest, then frontend build.

Do not set `PYTHONPATH` manually. `backend/pyproject.toml` already configures pytest with `pythonpath = ["src"]`, so root-level commands like `PYTHONPATH=backend/src uv run pytest` are the wrong habit for this repo.

## Dev Servers

Manual browser verification requires explicit user approval for the current task. Without that approval, limit validation to backend pytest and frontend build.

When the user approves manual browser verification:

- Backend: run `uv run uvicorn research_watch.api:app --host 127.0.0.1 --port 8000` with workdir `backend/`.
- Frontend: run `bun run dev` with workdir `frontend/`.

## Notes

- There is no separate frontend test runner right now; `bun run build` is the frontend check.
- Prefer targeted backend tests while iterating, then run full backend and frontend validation before reporting completion when risk warrants it.

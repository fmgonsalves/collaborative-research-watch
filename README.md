# Collaborative Research Watch

Filesystem-first shared research collaboration app for Path 1 of the PRD.

## Run Locally

Install frontend dependencies once after cloning, or whenever `frontend/package.json` or `frontend/bun.lockb` changes:

```bash
cd frontend
bun install
```

Start the backend:

```bash
cd backend
uv run uvicorn research_watch.api:app --host 127.0.0.1 --port 8000
```

Start the frontend:

```bash
cd frontend
bun run dev
```

Open `http://127.0.0.1:5173/`, enter an absolute workspace path, then create or select a user from that workspace's `users.csv`.

Backend logs print to the terminal where uvicorn is running. Set `RESEARCH_WATCH_LOG_LEVEL=DEBUG` for more verbose sync output.

## Test

```bash
cd backend
uv run pytest
cd ../frontend
bun run build
```

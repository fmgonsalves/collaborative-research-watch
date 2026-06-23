# Collaborative Research Watch

Filesystem-first shared research collaboration app with manual Path 2 AI enrichment.

The app lets a team collect documents and links in a shared workspace, browse/search/filter the collection, add human comments and human-created tags, and generate per-source AI summaries plus AI-generated tags. AI enrichment is manual: users can generate enrichment from supported local documents or public HTML links from a source detail page.

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

AI enrichment uses the OpenAI Responses API and requires explicit model configuration:

```bash
export OPENAI_API_KEY=...
export RESEARCH_WATCH_OPENAI_MODEL=...
```

Without these variables, collaboration, intake, sync, browse, comments, and tags still work. Manual AI generation returns a safe configuration error.

Start the frontend:

```bash
cd frontend
bun run dev
```

Open `http://127.0.0.1:5173/`, enter an absolute workspace path, then create or select a user from that workspace's `users.csv`.

Backend logs print to the terminal where uvicorn is running. Set `RESEARCH_WATCH_LOG_LEVEL=DEBUG` for more verbose sync output.

## AI Enrichment

Supported document extraction formats:

- `.txt`, `.md`, `.csv`
- `.pdf`
- `.docx`

Public link enrichment fetches static HTML with a timeout and extracts conservative visible text. It does not render JavaScript, bypass authentication, bypass paywalls, solve CAPTCHAs, or extract non-HTML responses.

## Test

```bash
cd backend
uv run pytest
cd ../frontend
bun run build
```

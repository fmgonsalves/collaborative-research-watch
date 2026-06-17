# AGENTS.md

## Project Source Of Truth

Read `PRD.md` before making product, architecture, storage, or AI workflow changes. Treat it as the source of truth for scope, phases, data ownership, and acceptance criteria.

For implementation-level file format examples and code pointers, see `WORKSPACE_SCHEMA.md`.

This project is a collaboration-first shared research repository. Preserve that center of gravity: users collect documents and links, add team comments and human tags, and browse/search the shared collection. AI is an enrichment layer, not the product's organizing architecture.

## Architectural Guardrails

- Keep canonical MVP data in shared readable files, not a required shared database.
- Use Markdown with YAML frontmatter for app-managed records when the app needs both machine-readable fields and human-readable content.
- Treat local SQLite, JSON indexes, vector stores, or other caches as optional rebuildable performance aids only.
- Do not introduce an autonomous AI-maintained wiki, topic graph, synthesis layer, or vector/RAG architecture unless the user explicitly asks for that direction.
- Keep generated `index.md` as an app-regenerated human-readable catalog, not the operational source of truth.

## Data Boundary

Use explicit data classification when adding fields or workflows:

- `source_public`: source content and safe source metadata that may be used for AI enrichment.
- `team_confidential`: team-visible human collaboration data, including users, emails, comments, human-created tags, attribution, and preferences.
- `app_internal`: implementation details such as full local paths, hashes, parser diagnostics, cache metadata, and run internals.

AI workflows may receive only `source_public` data. Do not send `team_confidential` or `app_internal` data to model prompts, generated AI summaries, AI-generated tags, logs, or later AI outputs.

## Tag And AI Output Rules

- Use the term "AI-generated tags" for model-created tags.
- Keep AI-generated tags structurally and visually distinct from human-created tags.
- Human-created tags are team collaboration data.
- AI summaries and AI-generated tags are bounded per-source enrichment outputs.

## Stack Defaults

Unless the user or a later technical design says otherwise:

- Backend: Python with FastAPI.
- Frontend: TypeScript with React.
- Shared records: Markdown with YAML frontmatter, plus CSV for simple intake files.
- Prefer standard, boring libraries for parsing CSV, YAML frontmatter, Markdown, and documents.

## Python Design Style

- Prefer small, typed, composable functions over monolithic procedures or deeply stateful objects.
- Prefer pure functions for transformations, validation, normalization, and policy checks. Keep filesystem, network, clock, process, and other side effects at clear edges.
- Treat functions as first-class building blocks. Pass behavior explicitly when it makes code easier to extend or test.
- Use explicit typing for public functions, data models, module boundaries, and test helpers. Choose the type tool that fits the problem: Pydantic models, dataclasses, `TypedDict`, `Protocol`, type aliases, or simple callable types.
- Keep implementation-specific details behind narrow typed functions or interfaces so equivalent implementations can be swapped without rewriting callers.
- Use `Protocol` or other interface-style typing when there is a real extension boundary; otherwise prefer simple functions and callable type aliases.
- Avoid speculative frameworks or abstraction layers. Add generic types or abstractions only when they clarify a real contract, protect an expected extension point, or remove meaningful duplication.
- Keep the style boring and readable. Functional composition is preferred, but not at the cost of obscure indirection.

## Implementation Style

- Prefer simple filesystem-first behavior that works for a few hundred documents and comments.
- Prefer deterministic app-owned writes for records and generated catalog files.
- On resync, user-facing intake (`sources/`, `links.csv`) supersedes stale app-managed records under `records/`.
- Validate malformed CSV/frontmatter records and report them without breaking the whole workspace.
- Keep non-technical users in mind: favor readable files, clear errors, and recoverable workflows.

## Validation

- Do not perform manual browser verification, browser-driven UI checks, or dev-server/browser verification flows unless the user explicitly approves it for the current task.

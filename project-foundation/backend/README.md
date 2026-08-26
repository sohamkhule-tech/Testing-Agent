# Project Foundation â€” Backend

FastAPI backend for the AI Agentic Testing Platform.

> **Complete setup & run instructions are in the root [`README.md`](../../README.md).** This file only covers the backend quick reference.

## Quick reference (backend only)

```bash
uv sync --extra dev                  # install dependencies (uv, not requirements.txt)
cp .env.example .env                 # Windows: Copy-Item .env.example .env
# edit .env â†’ set OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL

uv run playwright install chromium   # browser for the crawler
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: <http://localhost:8000/health>
- API docs (Swagger): <http://localhost:8000/api/docs>

## Tests & quality

```bash
uv run pytest
uv run ruff check app/
uv run mypy app/
```

## Note

The database is **optional** â€” the backend runs filesystem-only by default. See the root README for PostgreSQL setup.

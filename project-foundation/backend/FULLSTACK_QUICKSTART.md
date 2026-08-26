# Full-Stack Quick Start

> **This file is superseded by the root [`README.md`](../../README.md).** Follow that guide for the complete, up-to-date setup (it uses `uv` and covers the frontend too â€” this older doc referenced `requirements.txt` and MongoDB, which are no longer used).

## Summary

```bash
# 1. Backend
cd project-foundation
uv sync --extra dev
cp .env.example .env          # set OPENAI_API_KEY / OPENAI_BASE_URL / OPENAI_MODEL
uv run playwright install chromium
uv run uvicorn app.main:app --reload --port 8000

# 2. Frontend (new terminal)
cd frontend
cp .env.local.example .env.local
npm install
npm run dev
```

- Backend: <http://localhost:8000> (Swagger at `/api/docs`)
- Frontend: <http://localhost:3000>

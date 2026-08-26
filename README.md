# AI Agentic Testing Platform

An enterprise-grade, AI-powered web application testing platform. Describe what to test in plain English, and the platform autonomously crawls your application, designs a test plan, gets your approval, generates Playwright test code, executes it, and produces reports (including Allure).

**Design principle:** *AI Generates. Services Execute. Humans Approve.*

---

## Repository Layout

```
Testing Agent/
|-- README.md                      <- you are here
-- project-foundation/
|   |-- backend/                   # FastAPI backend (Python)
|   |   |-- app/                   # backend source
|   |   |-- tests/                 # backend test suite
|   |   |-- prompts/               # LLM system prompts
|   |   |-- pyproject.toml         # Python dependencies (uv)
|   |   |-- uv.lock                # locked dependency versions
|   |   +-- .env.example           # backend env template
|   +-- frontend/                  # Next.js frontend (TypeScript)
|-- docs/                          # architecture docs
+-- contracts/                     # JSON schema contracts
```

---

## Prerequisites

| Tool | Version | Why |
|------|---------|-----|
| Python | 3.12+ | Backend runtime |
| uv | latest | Python package manager (installs from `uv.lock`) |
| Node.js | 18+ (20 recommended) | Frontend |
| npm | comes with Node | Frontend packages |
| Git | any | clone the repo |

> **No database is required for basic usage.** The platform runs **filesystem-only** by default. PostgreSQL is optional (see [Database (optional)](#database-optional)).

---

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/sohamkhule-tech/Testing-Agent.git
cd Testing-Agent/project-foundation/backend
```

### 2. Install uv (skip if already installed)

```bash
# Windows (PowerShell)
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Mac / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. Set up the backend

```bash
cd project-foundation/backend

# Create .env from the template
cp .env.example .env        # Windows PowerShell: Copy-Item .env.example .env

# Install Python dependencies (from uv.lock)
uv sync --extra dev

# Install the Playwright browser (used by the crawler)
uv run playwright install chromium
```

**Edit `.env`** and set your LLM credentials:

```env
OPENAI_API_KEY=your-api-key-here
OPENAI_BASE_URL=https://api.mistral.ai/v1     # Mistral / OpenAI / DeepSeek / etc.
OPENAI_MODEL=mistral-medium-3-5
OPENAI_MAX_TOKENS=131072
OPENAI_TIMEOUT=540
```

> The LLM key is **required** to actually run a test (crawler, test design, etc.). You must provide your own key â€” it is never committed to the repo.

### 4. Run the backend

```bash
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verify it is up:

```bash
curl http://localhost:8000/health
```

Backend API docs (Swagger): <http://localhost:8000/api/docs>

### 5. Set up the frontend

In a **new terminal**:

```bash
cd project-foundation/frontend

# Create the frontend env file
cp .env.local.example .env.local   # Windows PowerShell: Copy-Item .env.local.example .env.local

# Install dependencies
npm install

# Start the dev server
npm run dev
```

Open <http://localhost:3000>.

---

## Environment Variables

### Backend - `project-foundation/backend/.env`

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_API_KEY` | âœ… | Your LLM provider API key |
| `OPENAI_BASE_URL` | âœ… | Provider base URL (Mistral / OpenAI / DeepSeek / OpenAI-compatible) |
| `OPENAI_MODEL` | âœ… | Model id to use (e.g. `mistral-medium-3-5`) |
| `OPENAI_MAX_TOKENS` | â€” | Max tokens per completion (default `4096`) |
| `OPENAI_TIMEOUT` | â€” | LLM request timeout in seconds (default `900`) |
| `LLM_PROVIDER` | â€” | `openai` / `ollama` / `azure` / `anthropic` |
| `DATABASE_URL` | â€” | PostgreSQL URL (only needed if DB persistence is enabled) |
| `ENVIRONMENT` | â€” | `development` (default) |
| `DEBUG` | â€” | `true` / `false` |

### Frontend â€” `project-foundation/frontend/.env.local`

| Variable | Required | Description |
|----------|----------|-------------|
| `NEXT_PUBLIC_API_URL` | âœ… | Backend URL (default `http://localhost:8000`) |

---

## Running a Test (end to end)

1. Start backend + frontend (steps above).
2. In the UI, create a **Project** (give it the app's URL).
3. On the Project page, enter test instructions (plain English) and choose the AI model.
4. Click **Analyse Prompt** (optional) then **Start Run**.
5. The pipeline runs: **Crawler â†’ Inventory â†’ Test Design â†’ Human Review â†’ Code Generation â†’ Execution â†’ Reporting**.
6. When the run pauses at **Human Review**, click **Approve** to continue.
7. View generated Playwright tests, execution results, and the **Allure report** on the run page.

---

## Database (optional)

The platform runs on the filesystem by default (`PERSISTENCE_POSTGRES_ENABLED=false`). To enable PostgreSQL persistence:

1. Start PostgreSQL (e.g. `docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres postgres:15-alpine`).
2. Set in `.env`:
   ```env
   DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/testing_platform
   PERSISTENCE_POSTGRES_ENABLED=true
   ```
3. Run migrations with Alembic (`alembic upgrade head`).

---

## Running Tests & Quality Checks

```bash
# Backend tests
uv run pytest

# Backend lint / type check
uv run ruff check app/
uv run mypy app/

# Frontend type check / lint
cd frontend
npm run type-check
npm run lint
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: No module named 'app'` | Run commands from inside `project-foundation/backend/` with the virtualenv active (use `uv run ...`) |
| Crawler can't launch browser | Run `uv run playwright install chromium` |
| LLM call returns 401/402 | Check `OPENAI_API_KEY` / `OPENAI_BASE_URL` in `.env` (subscription may be inactive) |
| Frontend can't reach backend | Backend must be on :8000; check `NEXT_PUBLIC_API_URL` in `frontend/.env.local` |
| Port 8000 busy | `uv run uvicorn app.main:app --reload --port 8001` and update `NEXT_PUBLIC_API_URL` |

---

## Security Notes

- `.env`, `.env.local`, and `storage/` are **git-ignored** â€” never commit API keys or run credentials.
- Always supply your own LLM API key; the template (`.env.example`) contains placeholders only.
- Run credentials are stored in `storage/` (encrypted at rest when `CREDENTIAL_ENCRYPTION_KEY` is set in production).

---

## License

MIT

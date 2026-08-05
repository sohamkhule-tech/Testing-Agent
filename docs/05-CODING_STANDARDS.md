# Coding Standards

## Document Metadata

| Field | Value |
|---|---|
| Document | Coding Standards |
| Document ID | SDD-STD-001 |
| Version | 1.0 |
| Status | Draft |
| Owner | Platform Architecture Team |
| Last Updated | 2026-07-20 |
| Review Frequency | Quarterly or on adoption of a new language/framework |

## Purpose

This document defines the engineering conventions that every developer and AI coding agent must follow when contributing to this project. It is the single source of truth for code style, structure, and quality.

These rules apply equally to human contributors and AI agents. Specifications reference this document rather than repeating conventions. A violation of these standards is a defect.

## General Engineering Principles

**Readability over cleverness.** Code is written once and read many times. Prefer clear, explicit code over terse or idiomatic shortcuts that obscure intent.

**Simplicity first.** Solve the problem at hand — not problems you anticipate but do not yet have. Build the simplest thing that meets the specification.

**Explicit over implicit.** Parameters, dependencies, and data flow should be visible in the code. Avoid global state, hidden side effects, and magical imports.

**Single Responsibility.** Every module, class, and function should have exactly one reason to change. If a component has multiple responsibilities, split it.

**Small, composable modules.** Modules should be small enough to be understood in a single reading. Favour composition over inheritance.

**Deterministic behaviour.** Functions that produce the same output for the same input should be pure where possible. I/O, randomness, and state mutation should be isolated and explicit.

**Specification First.** Code implements specifications — specifications do not document code. Never write code for which no specification exists.

**Backward compatibility.** Public interfaces and data contracts must not break existing consumers without a deprecation period and an ADR.

**Fail fast.** Validate inputs at the boundary. Catch errors as early as possible. Surface failures immediately rather than propagating invalid state.

**No premature optimization.** Write clear, correct code first. Measure before optimizing. Optimizations must be justified by data.

## Repository Standards

**Directory ownership.** Each top-level directory (`backend/`, `frontend/`, `docs/`) has a defined purpose. Cross-directory imports are forbidden — `backend/` never imports from `frontend/` and vice versa.

**Module boundaries.** Every Python module under `backend/app/agents/` and `backend/app/services/` owns one responsibility. Modules communicate only through the LangGraph state or the data contracts in `docs/contracts/`.

**One responsibility per module.** An agent module does one thing — trigger, crawl, analyse, design, or generate. If a module needs to do two things, it should be split. The module's name must reflect its single responsibility.

**No circular dependencies.** If module A depends on module B, module B must never depend on module A, directly or transitively. Extract shared code into a common module instead.

**No cross-layer imports.** Agents import from `services/` and `models/`. Services import from `models/`. Neither imports from `api/`. The API layer imports from `services/` and `agents/` only through the Orchestrator.

## Python Standards

**Formatting.** All Python code must be formatted with `black` (line length 100). Run `black .` before every commit.

**Linting.** All Python code must pass `ruff` with no errors. Ruff rules: E, F, I, N, W, UP, B, SIM, ARG, C4, TCH, PL. The `pyproject.toml` at the project root defines the exact configuration.

**Type hints.** Type hints are **mandatory** on all function signatures — parameters and return types. Variable annotations are encouraged but not required. Use `from __future__ import annotations` at the top of every file to enable deferred evaluation.

```python
def resolve_selectors(page_id: str, inventory: ApplicationInventory) -> list[Selector]: ...
```

**Docstrings.** Every public function, method, and class must have a docstring. Use Google-style docstrings. Private functions (prefixed with `_`) should have a docstring when the intent is not obvious from the name.

```python
def validate_run_config(config: RunConfig) -> RunConfig:
    """Validate and normalise a run configuration.

    Args:
        config: The raw run configuration from the API.

    Returns:
        A validated and normalised RunConfig.

    Raises:
        ValidationError: If the configuration fails validation.
    """
```

**Naming conventions.**
- Modules: `snake_case.py` — e.g. `trigger_agent.py`, `inventory_aggregator.py`
- Classes: `PascalCase` — e.g. `ApplicationInventory`, `RunConfig`
- Functions and methods: `snake_case` — e.g. `validate_run()`, `resolve_selectors()`
- Variables: `snake_case` — e.g. `run_id`, `page_elements`
- Constants: `UPPER_SNAKE_CASE` — e.g. `MAX_RETRY_COUNT`, `DEFAULT_TEMPERATURE`
- Private: prefix with `_` — e.g. `_validate_schema()`

**Imports.** Order: standard library, third-party, local. Groups separated by a blank line. Use absolute imports. Wildcard imports (`from x import *`) are forbidden.

```python
import uuid
from datetime import datetime

import pytest
from pydantic import BaseModel

from app.models.run import RunConfig
from app.services.inventory_aggregator import InventoryAggregator
```

**Constants.** Module-level constants are preferred over magic values. Define constants at the top of the file, after imports.

**Exceptions.** Define domain-specific exception classes in a dedicated `exceptions.py` per module. Never raise bare `Exception` or `RuntimeError` with a string message — always raise a typed exception.

```python
class CrawlTimeoutError(CrawlError):
    """Raised when the crawl exceeds the configured timeout."""
```

**Async guidelines.** Use `async def` for I/O-bound functions. CPU-bound work should remain synchronous or be offloaded to a thread pool. Avoid `asyncio.run()` inside async functions — use `await` instead.

**Dependency injection.** Agents and services receive their dependencies (LLM client, DB session, config) as constructor or function arguments. Never import a global singleton directly. This is what makes components independently testable and, later, independently deployable.

```python
class TriggerAgent:
    def __init__(self, llm_client: LLMClient, config: AppConfig) -> None: ...
```

**Configuration management.** All environment-specific values come from a single typed config module using Pydantic `BaseSettings`. No hardcoded configuration values scattered across agent files.

## FastAPI Standards

**Router organisation.** Group endpoints by domain in separate router modules under `app/api/`. Each router is a single `APIRouter` instance.

**Dependency injection.** Use FastAPI's `Depends` for shared dependencies (DB sessions, config, authenticated user). Dependencies are defined as callables in `app/api/dependencies.py`.

**Request validation.** Every endpoint receives a Pydantic request model. Never access `request.json()` directly. Validation errors are returned automatically by FastAPI.

**Response models.** Every endpoint declares a Pydantic response model in the `response_model` parameter. Responses are structured consistently — wrap lists in an envelope object rather than returning a bare array.

**Exception handling.** Define exception handlers at the router or app level for domain exceptions. Do not use try/except in endpoint functions for expected error cases — let the handler framework manage them.

```python
@app.exception_handler(ValidationError)
async def validation_error_handler(request: Request, exc: ValidationError) -> Response: ...
```

**Versioning.** All endpoints are prefixed with `/api/v1/`. Version bumps require an ADR.

**OpenAPI generation.** Use FastAPI's automatic OpenAPI generation. Do not suppress or override schema generation unless explicitly required. Every endpoint should have a `summary` and `description` for the generated documentation.

## SQLAlchemy Standards

**Models.** Define all ORM models in `app/models/`. Models inherit from a shared `Base` declared in `app/db/base.py`. Table names use `snake_case` and are explicitly declared — never rely on auto-generation.

**Relationships.** Use `relationship()` with explicit `back_populates`. Avoid `cascade="all, delete-orphan"` unless the lifecycle is strictly parent-owned. Lazy loading is the default — use `selectinload` or `joinedload` explicitly in queries.

**Session management.** Sessions are managed through FastAPI dependency injection (`Depends(get_db)`). Never create or close sessions manually in business logic. Use `db.commit()` only at the end of a successful operation — never in the middle of a multi-step workflow.

**Transactions.** Wrap multi-step write operations in a single transaction. If any step fails, the entire transaction rolls back. Do not catch exceptions inside a transaction and continue — let it roll back and handle the error at the boundary.

**Alembic migrations.** Every schema change requires an Alembic migration. Migrations are auto-generated with `alembic revision --autogenerate` and then manually reviewed. Never edit an existing migration that has been committed — create a new migration instead.

**No raw SQL.** Raw SQL is forbidden unless a query cannot be expressed in SQLAlchemy ORM and the performance difference has been measured and documented in a code comment.

## Frontend Standards

**Functional components only.** All React components are functional. Class components are forbidden.

**Strict typing.** TypeScript strict mode is enabled. `any` is forbidden in shared types and interfaces. Use `unknown` instead of `any` when the type is genuinely not known. Every function must have an explicit return type annotation on exported functions.

```typescript
export function useRunStatus(runId: string): RunStatus | null { ... }
```

**Hooks.** Custom hooks encapsulate reusable state logic. Hooks are named with the `use` prefix and reside in `frontend/hooks/`. No hook should contain JSX.

**State management.** Prefer React state and context for local state. External state management libraries are not used at MVP. Evaluate only if cross-component state becomes unmanageable.

**Folder organisation.**
- `app/` — Next.js App Router pages and layouts
- `components/` — Reusable UI components
- `hooks/` — Custom React hooks
- `lib/` — Utility functions, API client, types
- `styles/` — Global styles and CSS modules

**Props.** Every component defines its props as a TypeScript `interface` or `type` exported from a co-located `types.ts` file. Destructure props in the function signature. Use `interface` for public component props, `type` for unions and utility types.

```typescript
interface RunStatusBadgeProps {
  status: RunStatus;
  size?: "sm" | "md" | "lg";
}
```

**Error boundaries.** Each page-level component is wrapped in an error boundary. Error boundaries render a fallback UI and log the error. Do not use error boundaries for control flow — only for crash recovery.

## AI Standards

**Prompt versioning.** Every prompt template is versioned in `docs/prompts/` and tracked in source control. Prompt files are named after the agent that uses them (e.g. `code-generation-agent.md`). Prompts are never hardcoded in agent code.

**Stateless agents.** AI agents hold no state between invocations. All context is passed through the LangGraph state or read from the Inventory. Agents must not cache data in memory across runs.

**Structured output.** Every LLM call must specify a structured output schema. The prompt must include an explicit instruction to return only valid JSON matching that schema, with no prose or markdown fences. Output is parsed defensively — strip code fences if present — before schema validation.

**Retry policy.** If structured output fails schema validation, the agent receives exactly one corrective retry with the schema requirement repeated. If the retry also fails, a deterministic fallback is used. Never retry more than once. Never implement custom retry logic outside the bounded retry pattern.

**Schema validation.** All LLM output must be validated against a Pydantic model before it is trusted. Invalid output triggers the retry/fallback path. Output that passes validation is accepted without further review at the AI layer.

**No business logic inside prompts.** Prompts contain instructions, output schemas, and few-shot examples — never business rules, validation logic, or decision trees. Business logic lives in deterministic code, not in LLM prompts.

**Context minimization.** AI agents receive only the subset of the Inventory relevant to their task — never the full inventory, never raw DOM or HTML. Context size is capped. Every LLM call receives a purpose-built, compact JSON/text summary.

**Deterministic temperature.** All correctness-critical LLM calls use a temperature of 0.1–0.3. Do not rely on creative variation for correctness-critical output. Temperature changes must be documented in the prompt file.

## Logging Standards

**Structured logging.** All logs are structured JSON. Every log entry includes `run_id`, `component_name`, `timestamp`, `level`, and `message`. Use Python's `structlog` or `json.dumps` on a dict — never f-string formatting in log messages.

```python
logger.info("run_started", run_id=run_id, application_id=application_id)
```

**Correlation IDs.** The `run_id` is included in every log line emitted during a run. For non-run operations (e.g. application registration), generate a request-scoped correlation ID.

**Log levels.** `DEBUG` for detailed troubleshooting; `INFO` for state transitions (run started, milestone reached); `WARNING` for recoverable issues (retry triggered, fallback used); `ERROR` for failures that require human attention; `CRITICAL` for unrecoverable system failures.

**Never log secrets.** Credentials, tokens, API keys, and session cookies must never appear in log output. Redact them at the log boundary.

**Error context.** Every error log must include enough context to diagnose the failure without cross-referencing other systems: the component that failed, the input that caused the failure, the run ID, and the exception type and message.

## Error Handling Standards

**Domain exceptions.** Every module defines its own exception hierarchy rooted in a module-specific base exception. Module exceptions inherit from a project-wide `AppError` base class.

```python
class AgentError(AppError): ...
class CrawlError(AgentError): ...
class InventoryError(AppError): ...
```

**Validation errors.** Input validation happens at the boundary — the API layer for user input, the service boundary for inter-module calls. Validation errors are surfaced immediately with a clear message identifying the invalid field and the constraint violated.

**Infrastructure errors.** Database, network, and filesystem errors are caught at the service layer and wrapped in a domain exception with context. They are never propagated to the caller as raw `SQLAlchemyError` or `IOError`.

**User-friendly messages.** Errors surfaced to the user are expressed in domain terms, not stack traces. The system distinguishes between application errors (the target app is unreachable), platform errors (a component failed), and validation errors (the input is invalid).

**Fail fast.** Invalid state is detected and rejected at the earliest possible point. Do not propagate invalid data and fail later — the resulting error will be harder to diagnose.

**Retry policy.** Only AI agents have a retry policy (one corrective retry with bounded fallback). Deterministic services do not retry — they report errors to the Orchestrator, which decides the appropriate action.

## Testing Standards

**Backend (pytest).** Every function that contains logic must have a corresponding test. Tests are organised mirroring the module structure: `tests/agents/test_trigger_agent.py`, `tests/services/test_inventory_aggregator.py`. Use `pytest.fixture` for shared setup. Use `pytest.mark.asyncio` for async tests. Mock the LLM client in agent tests — never call a real model in unit tests.

```python
@pytest.mark.asyncio
async def test_validate_valid_config() -> None:
    config = RunConfig(url="https://example.com", prompt="Test login")
    result = await trigger_agent.validate(config)
    assert result.valid is True
```

**Frontend.** Component tests use React Testing Library. Test user interactions and rendered output, not implementation details (state, internal methods). Every page-level component must have a smoke test.

**AI — deterministic validation.** AI agent tests validate that the structured-output parsing, schema validation, and retry/fallback logic work correctly. Use pre-recorded LLM responses (fixtures) — never call a real model in tests. Test that invalid LLM output triggers the retry path and that two consecutive failures trigger the fallback.

**Playwright (end-to-end).** E2E tests validate the full pipeline against a known test application. These are integration-level — a single test per milestone scenario rather than exhaustive coverage. E2E tests are run separately from unit tests and are not required for every commit.

**Coverage expectations.** Backend: minimum 80% line coverage. Frontend: minimum 60% line coverage (UI-heavy code is inherently harder to test exhaustively). AI: 100% coverage of the structured-output parsing, validation, and retry/fallback logic. Coverage requirements apply at the project level, not per-module.

## Documentation Standards

**Specification before code.** Every feature has a written specification in `docs/specs/`. The specification is approved before any implementation begins. Code that implements a feature without a specification will be rejected.

**Contract updates.** When a cross-module interface changes, the corresponding contract in `docs/contracts/` must be updated as part of the same change. Never update a contract after the code is written.

**ADR for significant decisions.** Any change that affects the architecture — a new dependency, a different approach to a problem, a changed interface contract — requires an ADR in `docs/06-ADR.md`. The ADR is written before or during implementation, never after.

**PROJECT_STATE updates.** Every completed module or milestone must be reflected in `docs/04-PROJECT_STATE.md` before the change is considered complete.

**Code comments.** Comments explain _why_, not _what_. If the code is unclear, refactor it rather than comment it. Comments that duplicate the code's intent are noise and should be removed.

## Git Standards

**Branch naming.** Branches follow the pattern `{type}/{spec-id}-{short-description}`. Types: `feat`, `fix`, `docs`, `refactor`, `chore`. Spec ID is the specification number (e.g. `001`, `002`).

```
feat/001-project-setup
fix/002-trigger-agent-validation
docs/003-crawl-contract
```

**Commit messages.** Use conventional commits: `type(scope): description`. The description is imperative, lowercase, and under 72 characters. The body explains context and motivation.

```
feat(trigger): add URL validation and credential handling
docs(contract): define test-run-request.json schema
fix(crawler): handle timeout on slow page load
```

**PR expectations.** Every pull request references the specification it implements. PRs are small — one spec per PR. A PR must pass lint, type check, and all tests before review. The PR template includes a self-review checklist.

**Code review checklist.** Every review checks:
- Does the code match the specification?
- Are all type hints correct?
- Are there any cross-layer imports?
- Are all public functions documented?
- Are there tests for every logical path?
- Are error cases handled?
- Are secrets exposed in any way?
- Is the contract updated if the interface changed?

## Security Standards

**Secrets.** No secret — API key, database password, encryption key, credential — is ever committed to source control. Secrets are loaded from environment variables at runtime.

**Environment variables.** Every environment variable is declared in the typed config module with a default and a description. The `.env.example` file documents all required variables without real values.

**Credentials.** User-provided credentials are encrypted at rest. They are never written to logs, never included in LLM prompts, and never stored in generated scripts or reports. Credentials are injected into the Playwright browser context at runtime only.

**Input validation.** Every user-facing input — URL, prompt, credential fields — is validated at the API layer before it reaches any agent or service. Validation is strict: reject unknown fields, reject malformed data, reject out-of-range values.

**Least privilege.** The backend process runs with only the permissions it needs: read/write its own database file and workspace directories, outbound network access to the target application and Ollama. No elevated OS privileges.

**Dependency updates.** Dependencies are pinned to exact versions in `requirements.txt` and `package.json`. Automated dependency updates (Dependabot or equivalent) are reviewed before merging. Critical security patches are prioritised above feature work.

## Performance Standards

**No premature optimization.** Write correct, clear code first. Measure performance with realistic data before optimising. Never optimise based on assumptions about bottlenecks.

**Measure before optimizing.** Use profiling tools (cProfile, pytest-benchmark) to identify actual bottlenecks. Document the measurement and the expected improvement with every optimisation.

**Caching.** The Application Inventory is the primary cache — reused across runs until explicitly invalidated. Do not add additional caching layers without measuring the need.

**Database efficiency.** Use eager loading (`selectinload`) for relationships that are always accessed together. Avoid N+1 queries by examining the SQL emitted for every query. Index columns used in `WHERE`, `JOIN`, and `ORDER BY` clauses.

**Async I/O.** Use `asyncio` for network I/O — LLM calls, Playwright connections, database queries. CPU-bound work remains synchronous. Never block the event loop with synchronous I/O.

## Definition of Done

A feature is complete only when all of the following conditions are met:

- [ ] Specification implemented — all acceptance criteria in the spec are satisfied
- [ ] Tests pass — unit, integration, and (where applicable) E2E tests all pass
- [ ] Lint passes — `ruff` reports zero errors
- [ ] Formatting passes — `black` reports no changes needed
- [ ] Type checking passes — `mypy` reports zero errors
- [ ] Documentation updated — specifications, contracts, and project state reflect the change
- [ ] `docs/04-PROJECT_STATE.md` updated — status and progress reflect the completed work
- [ ] ADR recorded (if required) — any architectural decision made during implementation is recorded in `docs/06-ADR.md`

## Rules for AI Coding Agents

Every AI agent must follow this checklist.

**Before coding:**
- [ ] Read `docs/00-AI_CONTEXT.md`
- [ ] Read `docs/04-PROJECT_STATE.md`
- [ ] Read `docs/02-ARCHITECTURE.md`
- [ ] Read the relevant specification in `docs/specs/`
- [ ] Read the relevant contract in `docs/contracts/`

**During coding:**
- [ ] Follow naming conventions for the language
- [ ] Add type hints to every function signature
- [ ] Validate all LLM output against the schema
- [ ] Never invoke Playwright or modify persistent state
- [ ] Keep prompts versioned — never hardcode a prompt in agent code
- [ ] Log every state transition with `run_id` and `component_name`

**After coding:**
- [ ] Update `docs/04-PROJECT_STATE.md` to reflect the new state
- [ ] Record an ADR in `docs/06-ADR.md` if a significant decision was made
- [ ] Verify the Definition of Done checklist is complete

## Related Documents

| Document | Purpose |
|---|---|
| `docs/00-AI_CONTEXT.md` | AI onboarding, project summary, AI scope |
| `docs/01-PROJECT_OVERVIEW.md` | Business context, objectives, and success criteria |
| `docs/02-ARCHITECTURE.md` | Maintained architecture summary — component responsibilities |
| `docs/03-ROADMAP.md` | Delivery strategy and milestone breakdown |
| `docs/04-PROJECT_STATE.md` | Current implementation status and progress tracking |
| `docs/06-ADR.md` | Architecture Decision Records |
| `docs/specs/` | Feature specifications — source of truth for implementation |
| `docs/contracts/` | Typed data contracts for cross-component interfaces |

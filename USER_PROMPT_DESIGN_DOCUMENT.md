# User Prompt Driven AI Testing Workflow — Architecture & Implementation Plan

**Status:** Planning only. No code changes made.  
**Date:** 2026-07-31  
**Scope:** Full-stack — frontend, backend, LLM pipeline, database, workflow orchestration, security  

---

## Table of Contents

1. [Current Architecture Analysis](#1-current-architecture-analysis)
2. [Root Cause Analysis — Why the Prompt Is Ignored](#2-root-cause-analysis)
3. [Prompt Lifecycle Diagram](#3-prompt-lifecycle-diagram)
4. [Question 1 — Current Prompt Flow](#4-current-prompt-flow)
5. [Question 2 — UI Flow Analysis](#5-ui-flow-analysis)
6. [Question 3 — Prompt Persistence Strategy](#6-prompt-persistence-strategy)
7. [Question 4 — Prompt Builder Design](#7-prompt-builder-design)
8. [Question 5 — Credential Handling](#8-credential-handling)
9. [Question 6 — Prompt Types & Structure](#9-prompt-types-and-structure)
10. [Question 7 — Workflow Stage Integration](#10-workflow-stage-integration)
11. [Question 8 — Database Design](#11-database-design)
12. [Question 9 — API Design](#12-api-design)
13. [Question 10 — Security Considerations](#13-security-considerations)
14. [Question 11 — Future Extensibility](#14-future-extensibility)
15. [Recommended Architecture](#15-recommended-architecture)
16. [Step-by-Step Implementation Roadmap](#16-implementation-roadmap)
17. [Risk Assessment](#17-risk-assessment)
18. [Backward Compatibility Plan](#18-backward-compatibility-plan)

---

## 1. Current Architecture Analysis

### Stack Overview

| Layer | Technology | Location |
|---|---|---|
| Frontend | Next.js 14 (App Router), React Query, Tailwind | `project-foundation/frontend/src/` |
| Backend API | FastAPI | `project-foundation/app/api/routes/` |
| Workflow Engine | LangGraph | `project-foundation/app/workflows/trigger_workflow.py` |
| LLM Client | OpenAI-compatible SDK (AsyncOpenAI) | `project-foundation/app/llm/openai_client.py` |
| Prompt Templates | Jinja2 + Markdown files | `project-foundation/prompts/*.md` |
| DB (SQL) | PostgreSQL via SQLAlchemy + Alembic | `project-foundation/app/models/orm/core.py` |
| In-process state | LangGraph `PlatformWorkflowState` | (no persistence between runs) |

### Current Workflow Execution Path

```
POST /api/v1/runs
  ↓
create_run() [trigger.py:L63]
  ↓ extract user_prompt from body (L95)
  ↓
asyncio.create_task(_run_pre_review_workflow(..., user_prompt=user_prompt))
  ↓
execute_platform_workflow(..., user_prompt=user_prompt)
  ↓
PlatformWorkflowState(user_prompt=user_prompt)
  ↓ LangGraph graph executes nodes sequentially
  ↓
trigger_node      → does NOT receive or use user_prompt
crawler_node      → does NOT receive or use user_prompt
inventory_node    → does NOT receive or use user_prompt
test_design_node  → DOES pass user_prompt into TestDesignAgent.execute()
                    → appended as "## User's Test Instructions" section
                    → injected into the LLM user message only
human_review_node → does NOT receive or use user_prompt
code_gen_node     → does NOT receive or use user_prompt
execution_node    → does NOT receive or use user_prompt
```

### What the user_prompt currently does

- **Received**: `POST /api/v1/runs` body field `user_prompt` (or alias `test_instructions`)
- **Stored in state**: `PlatformWorkflowState.user_prompt` (in-memory only, not persisted to DB)
- **Consumed by**: Only `test_design_node` → passed to `TestDesignAgent._generate_test_plan()` → appended as a `## User's Test Instructions` section in the LLM user message
- **Not stored in DB**: The `runs` table has no `user_prompt` column. It is lost after the process ends.
- **Not passed to**: Crawler, Inventory, Code Generation, Execution

### Current system prompt source

- **File**: `project-foundation/prompts/test-design-agent.md`
- **Loaded by**: `PromptLoader` (Jinja2 + FileSystemLoader)
- **Called via**: `get_prompt("test-design-agent")` in `TestDesignAgent._generate_test_plan()`
- **Role in LLM call**: passed as the `system` message to `OpenAIClient.complete()`

---

## 2. Root Cause Analysis

### Why the prompt appears to "not work"

The system is **partially wired** — the frontend sends the prompt correctly and the backend receives it correctly. However there are **three separate failure modes**:

#### Failure 1 — Prompt is lost after process restarts (most critical)

The `user_prompt` exists only in-memory as part of `PlatformWorkflowState`. It is never written to the `runs` table or any other database record. If the server restarts mid-run, or if any code reads the run from the DB and re-creates workflow context, the prompt is gone.

#### Failure 2 — Prompt is ignored by 5 out of 6 stages

Only `test_design_node` passes `state.user_prompt` to its agent. The crawler, inventory aggregator, code generation, and execution nodes never read this field from state at all. Their `input_data` dicts do not include `user_prompt`.

#### Failure 3 — The "modal closes automatically" description

After reading the actual frontend code in `app/projects/[id]/page.tsx`, **there is no modal**. The user prompt is rendered as an inline `<textarea>` that is conditionally visible:

```tsx
{(!latestRun || latestRun.status === 'completed' || latestRun.status === 'failed' || latestRun.status === 'cancelled') && (
  <div ...>
    <textarea value={userPrompt} onChange={...} />
  </div>
)}
```

The textarea **disappears** as soon as `createRun.mutate()` succeeds and the router redirects to `/runs/${data.run_id}`. This is intentional UX, **not a bug** — but the user experiences it as "the prompt closes automatically." The underlying issue is:

1. There is no confirmation step between entering the prompt and launching the run.
2. The run starts immediately on clicking "Start Run," so the textarea disappears before the user can verify their prompt was captured.

**Root cause**: The prompt UX lacks a review/confirmation step. The workflow should pause on the prompt input, show a preview, and only launch after explicit confirmation.

---

## 3. Prompt Lifecycle Diagram

### Current (broken) lifecycle

```
User types prompt
      ↓
[textarea: userPrompt state]
      ↓
handleStartRun() called
      ↓
createRun.mutate({ projectId, userPrompt })
      ↓
POST /api/v1/runs { project_id, user_prompt }
      ↓
create_run() extracts user_prompt string
      ↓
asyncio.create_task(_run_pre_review_workflow(..., user_prompt))
      ↓
PlatformWorkflowState.user_prompt = "..." (in-memory only)
      ↓
trigger_node     ← user_prompt NOT used
crawler_node     ← user_prompt NOT used
inventory_node   ← user_prompt NOT used
test_design_node ← user_prompt used ✓ (appended to LLM user message)
human_review     ← user_prompt NOT used
code_gen_node    ← user_prompt NOT used
execution_node   ← user_prompt NOT used
      ↓
Process ends → user_prompt is DISCARDED (never persisted)
```

### Target lifecycle

```
User opens project page
      ↓
"AI Test Instructions" textarea (persistent, always visible)
      ↓
User types natural-language instructions
      ↓
[Optional: "Preview Prompt" panel shows assembled context]
      ↓
User clicks "Start Run"
      ↓
PromptContext assembled:
  - user_prompt (raw text)
  - parsed_sections (credentials, scope, exclusions, focus)
  - project_metadata (url, auth_type)
  ↓
POST /api/v1/runs { project_id, user_prompt, prompt_context }
      ↓
Backend:
  1. Persists user_prompt to runs.user_prompt_text (DB)
  2. Parses prompt into PromptContext
  3. Persists parsed context to runs.prompt_context_json
      ↓
PlatformWorkflowState.user_prompt = "..."
PlatformWorkflowState.prompt_context = { credentials, scope, exclusions, ... }
      ↓
trigger_node     ← receives project metadata (no prompt needed)
crawler_node     ← receives scope, excluded_pages, credentials from prompt_context
inventory_node   ← receives excluded_modules from prompt_context
test_design_node ← receives full user_prompt + focus_areas + coverage_preferences
code_gen_node    ← receives framework_preferences, assertion_style from prompt_context
execution_node   ← receives environment context
      ↓
user_prompt persisted → available for history, templates, future runs
```

---

## 4. Current Prompt Flow

### Q1: Where is the System Prompt stored?

`project-foundation/prompts/test-design-agent.md` — a Markdown file on disk.

### Q1: How is it loaded?

`PromptLoader` class uses **Jinja2 FileSystemLoader** pointing to `settings.prompt.prompt_base_path`. Called via `get_prompt("test-design-agent")` which calls `prompt_loader.render_prompt(name, variables)`. The rendered string becomes the `system` message in `OpenAIClient.complete()`.

### Q1: Which service builds the LLM prompt?

`TestDesignAgent._generate_test_plan()` manually builds the user message as a large f-string containing:
- Inventory summary JSON
- Pages, forms, APIs, navigation, user flows, inputs, buttons, tables, dialogs
- Optionally: `## User's Test Instructions` section (if `user_prompt_text` is non-empty)

There is no centralized `PromptBuilder` — each agent builds its own prompt independently.

### Q1: Which stages consume the system prompt?

Only `TestDesignAgent`. The `CrawlerAgent` calls `get_prompt("ai-crawler-agent")` but uses it internally (within `CrawlerService`, not surfaced in the workflow state or configurable per-run). The `IRGenerationAgent` (used by `CodeGenerationAgent`) builds its own hardcoded prompt.

### Q1: Is there already support for user prompts? Why is it not working?

**Yes, partially.** The plumbing exists (frontend → API → workflow state → test design agent) but is incomplete:
- Not persisted to DB (lost on restart)
- Only consumed by 1 of 6 stages
- No UI confirmation step before run starts
- No parsing into structured intent (credentials, scope, exclusions remain as unstructured text)

---

## 5. UI Flow Analysis

### Q2: Why does the prompt "close automatically"?

The textarea is shown inside a conditional block:

```tsx
{(!latestRun || ['completed', 'failed', 'cancelled'].includes(latestRun.status)) && (
  <div>
    <textarea value={userPrompt} ... />
  </div>
)}
```

When the user clicks "Start Run":
1. `createRun.mutate()` fires → run is created with status `running`
2. On success: `router.push('/runs/${data.run_id})` navigates away
3. The project page unmounts → the textarea disappears

This is a **navigation issue combined with missing UX confirmation step**. It is not a React state bug or re-render issue.

### Recommended UX

**Option A (Recommended): Inline Two-Step Flow**

```
Step 1 (before run exists or after completed/failed/cancelled):
┌─────────────────────────────────────────────────────┐
│ AI Test Instructions                                │
│ ┌───────────────────────────────────────────────┐  │
│ │ [textarea — multi-line, resizable]            │  │
│ └───────────────────────────────────────────────┘  │
│  "Tell the AI what to focus on..."                  │
│  [Preview Prompt ▶]    [Start Run →]               │
└─────────────────────────────────────────────────────┘

Step 2 (on clicking "Preview Prompt" — inline panel expands):
┌─────────────────────────────────────────────────────┐
│ ✓ Prompt Preview                                    │
│  Focus: Login form, Reports module                  │
│  Credentials: Detected (masked)                     │
│  Excluded: User Management                          │
│  Coverage: Negative scenarios emphasized            │
│  [Edit ✎]              [Confirm & Start Run →]     │
└─────────────────────────────────────────────────────┘
```

**Option B: Dedicated "Prompt" tab on project detail page**

Adds a persistent "Prompt" tab alongside "Overview" with an auto-save textarea. The prompt saved here becomes the default for the next run, but can be overridden at run creation time.

**Option C (Current behavior, fixed): Keep textarea, add confirmation dialog**

Before navigation, show a confirmation dialog: "Starting run with these instructions: [preview]. Confirm?"

**Recommendation**: Option A. It keeps the single-page experience intact, adds transparent preview, and requires no new routes. The prompt should also auto-save to `localStorage` so users do not lose their text on accidental navigation.

---

## 6. Prompt Persistence Strategy

### Q3: Should prompts be stored per project, per run, or both?

**Analysis:**

| Approach | Pros | Cons |
|---|---|---|
| Per project only | Simple, always has a default | Loses per-run history, can't audit what instructions produced a specific test plan |
| Per run only | Full audit trail, each run is self-contained | User must re-enter every time, no reuse |
| Both (recommended) | Default prompt at project level, override at run level, full history | Slightly more complex schema |

**Recommendation: Both, with a clear override hierarchy.**

```
projects.default_prompt_text  (optional, editable by user)
  ↓ used as pre-fill when creating a new run
runs.user_prompt_text          (the actual prompt used for this run — immutable after creation)
runs.prompt_context_json       (parsed structured context — also immutable after creation)
```

This mirrors how CI/CD systems handle environment variables: project-level defaults that can be overridden per run. It also enables:
- "Reuse last prompt" UX
- Prompt history across runs on the same project
- Auditing exactly what instructions produced each test plan

---

## 7. Prompt Builder Design

### Q4: Centralized Prompt Builder

Instead of each agent building its own prompt, introduce a single `PromptBuilder` service that assembles the final prompt from parts:

```
PromptBuilder.build(context: PromptBuildContext) → FinalPrompt
```

**Input (`PromptBuildContext`)**:
```python
@dataclass
class PromptBuildContext:
    # System identity
    agent_role: str                     # e.g. "test-design-agent"
    
    # User intent
    user_prompt_raw: str                # Raw natural-language input
    parsed_intent: ParsedPromptIntent   # Parsed structured sections
    
    # Project metadata
    project_name: str
    application_url: str
    auth_type: str | None
    environment: str                    # staging / production / development
    
    # Run-time data (injected as each stage produces it)
    inventory_summary: dict | None      # Available from inventory stage onward
    run_config: dict | None             # Crawl strategy, test level, etc.
```

**Output (`FinalPrompt`)**:
```python
@dataclass
class FinalPrompt:
    system_message: str    # From prompt template + project context
    user_message: str      # Inventory + intent + focus areas
    metadata: dict         # For logging (no credentials, no sensitive data)
```

**Assembly order inside PromptBuilder**:
```
system_message = render_template(agent_role) 
              + PROJECT_CONTEXT_SECTION(project_name, url, environment)
              + SCOPE_SECTION(include_pages, exclude_pages, excluded_modules)

user_message  = INVENTORY_SECTION(inventory_summary)
              + FOCUS_SECTION(parsed_intent.focus_areas)
              + COVERAGE_SECTION(parsed_intent.coverage_preferences)
              + EXCLUSION_SECTION(parsed_intent.excluded_modules)
              + OUTPUT_SECTION(parsed_intent.output_preferences)
              # NOTE: credentials are NEVER included in the assembled prompt
              # They are passed separately as structured auth_context
```

**Key design constraint**: No agent may concatenate strings directly into LLM messages. Every LLM call must go through `PromptBuilder.build()`. This is enforced architecturally by making `PromptBuilder` the only path to `ILLMClient.complete()`.

---

## 8. Credential Handling

### Q5: How should credentials be handled?

This is the highest-security concern. The recommendation is a **three-layer model**:

#### Layer 1 — Parsing (at ingestion)

When the user submits a run with `user_prompt`, the backend immediately parses credential patterns:

```python
# Regex patterns for detection
USERNAME_PATTERNS = [r"username[:\s]+(\S+)", r"email[:\s]+(\S+@\S+)", r"login[:\s]+(\S+)"]
PASSWORD_PATTERNS = [r"password[:\s]+(\S+)", r"pass[:\s]+(\S+)", r"pwd[:\s]+(\S+)"]
```

Detected credentials are:
- **Extracted** into a separate `AuthContext` structure
- **Replaced** in the stored `user_prompt_text` with `[CREDENTIAL REDACTED]` placeholder
- **Stored encrypted** in a separate `run_credentials` table (AES-256-GCM)

#### Layer 2 — Transmission (to agents)

```python
@dataclass
class AuthContext:
    username: str | None       # Plaintext (in-memory only, never logged)
    password: str | None       # Plaintext (in-memory only, never logged)
    login_url: str | None
    auth_strategy: str | None  # "form", "api", "basic"
```

`AuthContext` is passed to the Crawler agent as a separate parameter (not embedded in any prompt or log message). The crawler uses it to drive Playwright's `page.fill()` calls directly.

#### Layer 3 — What goes to the LLM

**Credentials NEVER appear in any LLM prompt.** Instead, the LLM is told:

```
Authentication is required for this application.
Login credentials have been provided separately and will be handled by the crawler.
Assume the crawler will authenticate before visiting protected pages.
Generate test scenarios that cover both authenticated and unauthenticated states.
```

#### Answers to specific sub-questions

| Question | Answer |
|---|---|
| Should credentials be parsed? | **Yes** — regex extraction at API ingestion time |
| Should they remain free text? | **No** — extracted and stored separately |
| Should they be stored separately? | **Yes** — `run_credentials` table, encrypted at rest |
| Should the crawler receive them? | **Yes** — as `AuthContext`, not embedded in prompts |
| Should Playwright automatically fill them? | **Yes** — crawler service uses `page.fill()` with values from `AuthContext` |
| Should sensitive values be masked in logs? | **Yes** — all logging middleware must scrub credential fields |

#### Structured input alternative (recommended long-term)

For a better UX than parsing free-text, add structured credential input fields alongside the textarea:

```
┌─────────────────────────────────────────────────────────┐
│ Authentication (optional)                               │
│  URL:       [________________]                          │
│  Username:  [________________]                          │
│  Password:  [________________] [show/hide]              │
└─────────────────────────────────────────────────────────┘
```

This eliminates parsing ambiguity and is unambiguously more secure than extracting creds from free text.

---

## 9. Prompt Types and Structure

### Q6: Single free-text vs. structured sections?

**Recommendation: Start with structured free-text sections, evolve to hybrid.**

#### Phase 1 — Structured sections within a single textarea

Guide users with section headers. The UI renders an expandable template:

```
## Focus Areas
(what to test, which modules, which features)

## Credentials
(login URL, username, password)

## Exclude
(modules or pages to skip)

## Coverage Preferences
(functional only / include negative / include boundary / security)

## Output Preferences
(API tests? Accessibility tests? Specific framework conventions?)
```

Users can fill only the sections they need. The backend parses each section by heading.

#### Phase 2 — Hybrid (structured fields + free-text override)

Add structured form fields for common sections (credentials, scope, exclusions) with a "Custom Instructions" free-text field for everything else. This is the enterprise standard (cf. GitHub Actions inputs).

#### Mapping to `ParsedPromptIntent`

```python
@dataclass
class ParsedPromptIntent:
    raw_text: str                      # Original unmodified text (credentials redacted)
    focus_areas: list[str]             # ["Reports module", "Login form"]
    excluded_modules: list[str]        # ["User Management", "Admin"]
    excluded_pages: list[str]          # URL patterns
    included_pages: list[str]          # URL patterns (scope)
    coverage_preferences: list[str]    # ["negative", "boundary", "security"]
    output_preferences: list[str]      # ["API tests", "accessibility"]
    credential_hints: list[str]        # ["credentials provided"] (masked)
    has_credentials: bool              # True if credentials were parsed
    custom_instructions: str           # Any instructions that don't fit categories
```

---

## 10. Workflow Stage Integration

### Q7: How each stage should consume prompt information

#### Trigger Node
- Receives: Project metadata, application URL, environment
- Prompt usage: None needed (sets up workspace, no LLM call)

#### Crawler Node ← **currently does not use user_prompt at all**
Should receive `ParsedPromptIntent` and `AuthContext`:

```python
input_data = {
    ...existing fields...,
    "scope": {
        "include_pages": parsed_intent.included_pages,    # restrict crawl
        "exclude_pages": parsed_intent.excluded_pages,    # skip pages
    },
    "auth_context": auth_context,    # credentials (not from prompt string)
}
```

The crawler uses `include_pages`/`exclude_pages` to configure Playwright navigation and `auth_context` for login.

#### Inventory Aggregator Node ← **currently does not use user_prompt at all**
Should receive excluded modules to tag or filter:

```python
input_data = {
    ...existing fields...,
    "excluded_modules": parsed_intent.excluded_modules,
}
```

Inventory items tagged from excluded modules are not removed (audit trail), but marked `excluded: true` so the test design agent skips them.

#### Test Design Node ← **already partially implemented**
Currently receives raw `user_prompt` string and appends it as a section. Should be upgraded:

```python
input_data = {
    ...existing fields...,
    "user_prompt": state.user_prompt,                         # keep for context
    "parsed_intent": state.prompt_context,                    # structured sections
    "project_metadata": { "name", "url", "auth_type" },      # from project
}
```

The `PromptBuilder` assembles the final LLM message from all these parts.

#### Code Generation Node ← **currently does not use user_prompt at all**
Should receive output preferences:

```python
input_data = {
    ...existing fields...,
    "output_preferences": parsed_intent.output_preferences,
    # e.g. ["Use async/await", "Add data-testid assertions", "Generate API tests"]
}
```

The IR generation agent appends these as a `## Code Style Preferences` section in the LLM prompt.

#### Execution Node
No LLM call. Does not consume user prompt directly. The generated tests already encode the intent. Could receive `auth_context` for tests that require credentials at execution time.

---

## 11. Database Design

### Q8: Recommended Schema

Three additions are required. One new table and two column additions.

#### Addition 1 — New column: `projects.default_prompt_text`

```sql
ALTER TABLE projects 
ADD COLUMN default_prompt_text TEXT;
```

Purpose: Stores the user's default reusable prompt for this project. Pre-fills the textarea on the project page. Editable at any time without creating a run.

#### Addition 2 — New columns on `runs`

```sql
ALTER TABLE runs
ADD COLUMN user_prompt_text          TEXT,
ADD COLUMN user_prompt_redacted_text TEXT,    -- version with credentials replaced by [REDACTED]
ADD COLUMN prompt_context_json       JSONB DEFAULT '{}',  -- ParsedPromptIntent
ADD COLUMN prompt_version            VARCHAR(32);          -- for future template versioning
```

- `user_prompt_text`: The raw user input (with credentials redacted at ingestion).  
- `user_prompt_redacted_text`: Separate field ensuring the display-safe version is always available without re-parsing.  
- `prompt_context_json`: The `ParsedPromptIntent` as structured JSON — used for replay, analytics, and to reconstruct workflow context without re-parsing.  
- `prompt_version`: Reserved for future prompt template versioning (e.g. `"v1.0"`, `"template:login-testing-v2"`).

#### Addition 3 — New table: `run_credentials`

```sql
CREATE TABLE run_credentials (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES runs(run_id) ON DELETE CASCADE,
    credential_type VARCHAR(32) NOT NULL,       -- 'form', 'api', 'basic'
    login_url       TEXT,
    username_enc    BYTEA NOT NULL,             -- AES-256-GCM encrypted
    password_enc    BYTEA NOT NULL,             -- AES-256-GCM encrypted
    encryption_key_id VARCHAR(64) NOT NULL,     -- KMS key reference
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_run_credentials_run_id ON run_credentials(run_id);
```

Credentials are **never** stored as plaintext. They are encrypted using a KMS-managed key before storage. The `encryption_key_id` references the key used so credentials can be rotated.

#### Future addition (Phase 2) — `prompt_templates` table

```sql
CREATE TABLE prompt_templates (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id       UUID NOT NULL,
    project_id      UUID REFERENCES projects(id),  -- NULL = tenant-wide template
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    template_text   TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ
);
```

---

## 12. API Design

### Q9: Recommended API changes

#### Modified: `POST /api/v1/runs`

Current request body is an untyped `dict`. Replace with a typed Pydantic model:

```python
class CreateRunRequest(BaseModel):
    project_id: UUID
    user_prompt: str | None = Field(None, max_length=10000)
    # Structured credential alternative (preferred over parsing free text)
    credentials: RunCredentialInput | None = None
    # Scope override (overrides prompt-parsed scope)
    scope_override: ScopeOverride | None = None

class RunCredentialInput(BaseModel):
    login_url: str | None = None
    username: str | None = None
    password: str | None = None          # handled as SecretStr in Pydantic
    auth_strategy: str = "form"

class ScopeOverride(BaseModel):
    include_pages: list[str] = []
    exclude_pages: list[str] = []
    excluded_modules: list[str] = []
```

Response: unchanged (`{ run_id, status }`)

#### New: `GET /api/v1/projects/{id}/prompt`

Returns the project's default prompt:

```json
{
  "project_id": "uuid",
  "default_prompt_text": "Test the login form...",
  "updated_at": "2026-07-31T10:00:00Z"
}
```

#### New: `PUT /api/v1/projects/{id}/prompt`

Saves the project's default prompt:

```json
// Request
{ "default_prompt_text": "..." }

// Response
{ "project_id": "uuid", "default_prompt_text": "...", "updated_at": "..." }
```

#### New: `GET /api/v1/runs/{id}/prompt`

Returns the prompt used for a specific run (for audit, replay, display):

```json
{
  "run_id": "uuid",
  "user_prompt_redacted_text": "Test the Reports module. Login using [CREDENTIAL REDACTED].",
  "prompt_context": {
    "focus_areas": ["Reports"],
    "excluded_modules": [],
    "has_credentials": true,
    "coverage_preferences": []
  },
  "prompt_version": "v1"
}
```

**Note**: This endpoint never returns the original credential values. It returns the redacted version only.

---

## 13. Security Considerations

### Q10: Full security model

#### Credentials in transit (HTTPS)
- All API calls must use TLS. Frontend `.env.local` must not allow HTTP endpoints for credential-carrying calls.
- Credentials sent in `POST /api/v1/runs` body must never be logged by FastAPI request logging middleware.
- Add a `SensitiveFieldScrubber` to the logging middleware that replaces `password`, `credentials`, `token` fields with `[REDACTED]` before any log write.

#### Credentials at rest (DB)
- Stored in `run_credentials` table as `BYTEA` (AES-256-GCM encrypted).
- Encryption key managed by a KMS (HashiCorp Vault or AWS KMS). Never stored in the same database.
- The application only holds the key reference (`encryption_key_id`), not the key itself.

#### Credentials in SSE events
- The `EventBus` emits events to the frontend via SSE. **No event may carry credential values.**
- `emit()` calls in the crawler node must never serialize `AuthContext` into event payloads.
- Add a compile-time check: if `AuthContext` is detected in any `EventType.*` payload, raise a build error.

#### Credentials in LLM prompts
- `PromptBuilder.build()` must never include `AuthContext` values in any prompt string.
- The user's `user_prompt_text` stored in the DB is always the **redacted version** (credentials replaced at ingestion).
- Test: unit tests for `PromptBuilder` must assert that `username` and `password` values from `ParsedPromptIntent` do not appear in the assembled `FinalPrompt`.

#### Credentials in generated test code
- The `CodeGenerationAgent` must use **environment variable references** for any credentials in generated Playwright code. Never hardcode.
- Generated code pattern: `process.env.TEST_USERNAME`, `process.env.TEST_PASSWORD`
- The execution service sets these env vars from decrypted `run_credentials` at test execution time, in a sandboxed process.

#### Credentials in reports / Excel
- The `ReportingAgent` and any export pipeline must explicitly exclude the `run_credentials` table from all data exports.
- If test step names include credential values (e.g. from free-text), a scrubbing pass must run before report generation.

#### Credentials in browser console
- All SSE event handlers in the frontend must strip or not forward any field matching the patterns `password|pass|pwd|secret|token|credential`.

---

## 14. Future Extensibility

### Q11: Design for future features

The schema and API design proposed above already accommodates all listed future features:

| Future Feature | How it is supported |
|---|---|
| Prompt Templates | `prompt_templates` table (Phase 2 DB addition). `POST /api/v1/prompt-templates`. UI: template picker dropdown in the run creation flow. |
| Saved Prompt Library | `prompt_templates` table with `project_id = NULL` (tenant-wide). |
| Team Prompt Library | Same `prompt_templates` table with RBAC on `created_by` / sharing flags. |
| Project Default Prompt | `projects.default_prompt_text` (Phase 1 DB addition). |
| Run Override Prompt | Already designed — `runs.user_prompt_text` overrides the project default at run creation. |
| AI Prompt Optimization | `POST /api/v1/projects/{id}/prompt/optimize` — LLM analyzes past runs and suggests prompt improvements based on which scenarios were approved vs. rejected in human review. |
| Prompt Version History | `prompt_templates.version` column + `runs.prompt_version` foreign reference. A `prompt_history` view joins these to show how prompts evolved. |

---

## 15. Recommended Architecture

### High-level component diagram

```
┌──────────────────────────────────────────────────────────────────┐
│  FRONTEND (Next.js)                                              │
│                                                                  │
│  ProjectDetailPage                                               │
│    ├── PromptInput (textarea + structured fields)                │
│    ├── CredentialFields (username / password / login URL)        │
│    ├── PromptPreviewPanel (collapsible)                          │
│    └── StartRunButton (only active after prompt reviewed)        │
└──────────────────────────┬───────────────────────────────────────┘
                           │ POST /api/v1/runs
                           │ { project_id, user_prompt, credentials? }
┌──────────────────────────▼───────────────────────────────────────┐
│  BACKEND API (FastAPI)                                           │
│                                                                  │
│  create_run()                                                    │
│    ├── PromptParser.parse(user_prompt)  → ParsedPromptIntent     │
│    ├── CredentialExtractor.extract()    → AuthContext            │
│    ├── CredentialStore.encrypt_and_save(run_id, auth_context)    │
│    ├── Persist: runs.user_prompt_text (redacted)                 │
│    ├── Persist: runs.prompt_context_json                         │
│    └── asyncio.create_task(execute_workflow(...))                │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  WORKFLOW (LangGraph)                                            │
│                                                                  │
│  PlatformWorkflowState                                           │
│    ├── user_prompt: str                                          │
│    ├── prompt_context: ParsedPromptIntent                        │
│    └── auth_context: AuthContext  (never logged)                 │
│                                                                  │
│  trigger_node     → unchanged                                    │
│  crawler_node     → receives scope + auth_context                │
│  inventory_node   → receives excluded_modules                    │
│  test_design_node → PromptBuilder.build(agent="test-design",     │
│                       intent=prompt_context, inventory=...)      │
│  code_gen_node    → PromptBuilder.build(agent="ir-generation",   │
│                       intent=prompt_context)                     │
│  execution_node   → receives decrypted auth_context for env vars │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│  PROMPT BUILDER (new service)                                    │
│                                                                  │
│  PromptBuilder.build(PromptBuildContext) → FinalPrompt           │
│    ├── load_template(agent_role)                                 │
│    ├── render_system_message(template, project_ctx, scope_ctx)   │
│    └── render_user_message(inventory, intent, focus, coverage)   │
│    NOTE: credentials NEVER included                              │
└──────────────────────────────────────────────────────────────────┘
```

---

## 16. Implementation Roadmap

All phases are designed to be **independently deployable** without breaking the existing workflow.

---

### Phase 1 — Prompt Persistence (No behavior change, just durability)
**Goal**: User prompt survives server restarts. No UX or workflow change.  
**Risk**: Very low (additive DB change only).

**Steps**:
1. **DB migration**: Add `user_prompt_text`, `user_prompt_redacted_text`, `prompt_context_json`, `prompt_version` to `runs` table.
2. **Backend**: In `create_run()`, after creating the `RunEntity`, write `user_prompt_text` to the DB via a repository update.
3. **API**: Add `GET /api/v1/runs/{id}/prompt` endpoint (returns redacted text only).
4. **Test**: Write unit test confirming `user_prompt_text` is present in the DB after run creation.

---

### Phase 2 — Project Default Prompt
**Goal**: Users can save a default prompt per project. Pre-fills the run creation textarea.  
**Risk**: Low.

**Steps**:
1. **DB migration**: Add `default_prompt_text TEXT` to `projects` table.
2. **Backend**: Add `GET /api/v1/projects/{id}/prompt` and `PUT /api/v1/projects/{id}/prompt` endpoints.
3. **Backend**: In `create_run()`, if no `user_prompt` is provided, fall back to `project.default_prompt_text`.
4. **Frontend**: In `useProject()`, when project loads, pre-fill `userPrompt` state with `project.default_prompt` (fetched from new endpoint).
5. **Frontend**: Add auto-save for prompt: on textarea blur, call `PUT /api/v1/projects/{id}/prompt`.
6. **Test**: Verify fallback behavior when run is created without explicit prompt.

---

### Phase 3 — UI Review Step
**Goal**: User sees their prompt is captured before the run starts. Eliminates the "disappears" experience.  
**Risk**: Low (UI only, no backend change).

**Steps**:
1. **Frontend**: Rename the current inline textarea section to "AI Test Instructions."
2. **Frontend**: Add a collapsible "Preview" panel below the textarea. It shows a parsed summary: Focus, Exclusions, Coverage. No credentials shown.
3. **Frontend**: On "Start Run" click, show a brief confirmation toast: "Starting run with your instructions..." before navigating.
4. **Frontend**: Persist `userPrompt` to `localStorage` keyed by `projectId` so it survives navigation. Clear on successful run creation.
5. **Frontend**: Add character counter and 10,000-character limit indicator.

---

### Phase 4 — Structured Credential Handling
**Goal**: Credentials provided via prompt or structured fields are handled securely.  
**Risk**: Medium (new security-critical code).

**Steps**:
1. **Backend**: Implement `CredentialExtractor` — regex-based parser that detects username/password patterns in `user_prompt`.
2. **Backend**: Implement `CredentialStore` — encrypts and persists credentials to `run_credentials` table.
3. **Backend**: In `create_run()`, after parsing prompt, run credential extraction and persist.
4. **Backend**: Modify `CreateRunRequest` schema to accept optional `credentials: RunCredentialInput` (structured alternative).
5. **Backend**: Modify logging middleware to scrub `password`, `credentials`, `token` fields from all log entries.
6. **Workflow**: Modify `_run_pre_review_workflow()` to load `AuthContext` from `CredentialStore` and pass into `PlatformWorkflowState`.
7. **Crawler Node**: Accept and use `auth_context` for Playwright login steps.
8. **Test**: Confirm credentials never appear in log output, SSE events, or LLM prompts.
9. **Frontend**: Add structured credential input fields to the prompt panel (optional alternative to free-text).

---

### Phase 5 — PromptBuilder Service
**Goal**: Single centralized prompt assembly. Eliminates manual f-string building in agents.  
**Risk**: Medium (refactors core LLM call path, needs thorough testing).

**Steps**:
1. **Backend**: Create `app/services/prompt_builder.py` with `PromptBuilder` class.
2. **Backend**: Define `PromptBuildContext`, `ParsedPromptIntent`, `FinalPrompt` dataclasses.
3. **Backend**: Implement `PromptParser.parse(raw_text) → ParsedPromptIntent` — section-based parser.
4. **Backend**: Update `TestDesignAgent._generate_test_plan()` to use `PromptBuilder.build()` instead of manual f-string.
5. **Backend**: Write unit tests for `PromptParser` covering all section types and edge cases (empty, malformed, credentials).
6. **Backend**: Write unit tests for `PromptBuilder` asserting no credential values appear in output.

---

### Phase 6 — Full Stage Integration
**Goal**: All workflow stages receive and use relevant prompt context.  
**Risk**: Medium.

**Steps**:
1. **Workflow State**: Add `prompt_context: dict | None` and `auth_context: dict | None` to `PlatformWorkflowState`.
2. **Crawler Node**: Pass `scope` (include/exclude pages) and `auth_context` to `CrawlerAgent.execute()`.
3. **Inventory Node**: Pass `excluded_modules` to inventory aggregator service for tagging.
4. **Code Gen Node**: Pass `output_preferences` from `ParsedPromptIntent` to `IRGenerationAgent`.
5. **Test**: End-to-end test confirming a prompt like "Only test Reports, skip User Management" results in no User Management scenarios in the test plan.

---

### Phase 7 — Prompt Templates (Future)
**Goal**: Reusable templates, team library, version history.  
**Risk**: Low (additive only).

**Steps**:
1. DB migration: Create `prompt_templates` table.
2. Backend: CRUD endpoints for templates.
3. Frontend: Template picker dropdown in run creation UI.
4. Backend: Link `runs.prompt_version` to template ID.

---

## 17. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|---|---|---|---|
| Credential extraction regex produces false positives | Medium | High (user prompt truncated) | Run extraction in shadow mode first; show user what was detected before run starts |
| Credential extraction regex misses patterns | Medium | High (creds passed as plain text to LLM) | Prefer structured credential fields (Phase 4) over regex parsing |
| KMS unavailable at run time | Low | High (runs blocked) | Cache decrypted credentials in-process for the lifetime of a single run; never cache across runs |
| PromptBuilder breaks existing test design quality | Medium | Medium | A/B test with feature flag; compare scenario counts from runs with/without PromptBuilder |
| Long user prompts exceed LLM context window | Low | Medium | Implement token counting before LLM call; truncate `inventory_summary` (not user intent) if approaching limit |
| DB migration locks `runs` table in production | Low | High | Use `ADD COLUMN ... DEFAULT NULL` (zero-downtime in PostgreSQL); deploy migration before code change |
| User expects credentials are private; SSE leaks them | Low | Critical | Enforce SSE scrubbing in Phase 4; add automated test that subscribes to SSE and checks for credential patterns |
| Backward compatibility: runs without user_prompt fail | Low | Low | All new columns are `NULLABLE`; existing code paths continue to work when `user_prompt = None` |

---

## 18. Backward Compatibility Plan

Every change in this plan is **additive and backward-compatible**:

1. **DB**: All new columns use `NULL` defaults. Existing rows are unaffected. The Alembic migration uses `ADD COLUMN ... DEFAULT NULL`, which in PostgreSQL is an instant metadata operation with no table lock.

2. **API**: `POST /api/v1/runs` currently accepts `body: dict = Body(...)`. Moving to a typed Pydantic model is backward-compatible as long as the model uses `Optional` for all new fields. Existing callers sending only `project_id` continue to work.

3. **Workflow**: All new state fields (`prompt_context`, `auth_context`) are `Optional` with `None` defaults. Existing node logic continues to work when these are `None`. New logic only runs if the values are present.

4. **Frontend**: The textarea is already present. Adding the preview panel and auto-save is purely additive. The "Start Run" button behavior is unchanged; the optional prompt step does not block users who skip it.

5. **System prompt templates**: The `prompts/test-design-agent.md` file is not modified in any phase. The `PromptBuilder` loads it as-is and appends user intent sections after it.

6. **Feature flags**: Phases 4–6 should be guarded by a feature flag (`settings.features.user_prompt_pipeline = True/False`) during rollout so they can be disabled without a code deployment if issues arise.

---

## Summary

The current system has the **plumbing in place** but is missing four things:

| Gap | Fix |
|---|---|
| Prompt not persisted to DB | Phase 1 — Add columns to `runs` table |
| Only TestDesign consumes prompt | Phase 6 — Full stage integration |
| No project-level default prompt | Phase 2 — Add `default_prompt_text` to `projects` |
| UI gives no confirmation step | Phase 3 — Add preview panel + auto-save |
| Credentials not handled securely | Phase 4 — `CredentialStore` + redaction |
| Each agent builds its own prompt | Phase 5 — Centralized `PromptBuilder` |

The implementation order (1 → 2 → 3 → 4 → 5 → 6 → 7) ensures that each phase delivers independent, shippable value while maintaining full backward compatibility with existing runs and the existing frontend.

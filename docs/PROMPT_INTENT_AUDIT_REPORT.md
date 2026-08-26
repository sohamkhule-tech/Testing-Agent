# MASTER END-TO-END ARCHITECTURE AUDIT
## Prompt-Intent Propagation: Where User Instructions Are Lost

**Scope:** Read-only forensic audit. Trace one natural-language user prompt (e.g. `"Crawl only Create RRF and ignore Reports"`) from the frontend prompt box through API → intent parser → execution planner → crawler → inventory → test design → human review → code generation → execution. Identify the first architectural failure where intent is lost.

**Method:** Every conclusion cites `file:line`. Where the code does not prove a claim, it is marked **Unable to verify from the current code**. Parser behaviour was empirically verified by executing `PromptParser` against the user's own example prompts (results in §2.3).

---

## 1. Executive Summary

The pipeline *does* propagate a parsed-intent object (`ParsedPromptIntent`) from the API layer into the workflow state, and the raw prompt text does reach the test-design LLM. However, user intent is **corrupted at Stage 3 (intent parser) and then progressively diluted at Stages 5, 6, 7, 9, and 10**. The single most damaging defect is in the intent parser: keyword-based focus detection scans the entire prompt (including negated clauses) and the `only`/`just` constraint converts that mis-detected focus into a crawl restriction. Empirically confirmed:

```
"Crawl only Create RRF and ignore Reports"
  focus_areas:      ['Reports']     ← WRONG (user asked for Create RRF)
  excluded_modules: ['Reports']     ← right, but contradicts focus_areas
  included_pages:   ['reports']     ← CATASTROPHIC: crawl restricted to /reports/* only
```

The result is a **self-contradictory scope** — the crawler is told to *only crawl Reports* while the inventory is told to *exclude Reports* — and the module the user actually wanted (Create RRF) is never crawled.

Beyond the parser, scope fidelity degrades at every downstream boundary:

| Stage | Intent element | Status |
|---|---|---|
| 1 Frontend | Raw prompt sent as `user_prompt` | OK |
| 2 API | Parsed into `ParsedPromptIntent`, persisted | OK (parsing bug applies) |
| 4 Planner | `prompt_context` in workflow state | OK |
| 5 Crawler | `included_pages` restrict crawl | Applied, but from WRONG focus areas |
| 6 Inventory | `excluded_modules` filter | **Partial only — filters pages, not forms/buttons/APIs** |
| 7 Test design | focus/exclude/coverage injected | Sent, but overridden by "generate ALL / min 8 per page" |
| 8 Human review | **auto-approve, no human, no intent** | N/A |
| 9 Code gen | `output_preferences` passed but **never read** | Dead parameter |
| 10 Execution | **no intent input at all** — runs everything | Missing |

There is **no execution planner**. Stage 4 is a linear LangGraph that unconditionally runs every stage; nothing plans or gates by intent.

---

## 2. Stage-by-Stage Trace with Evidence

### Stage 1 — Frontend (prompt box → HTTP)

- Prompt state + textarea: `frontend/src/app/projects/[id]/page.tsx:40` (`userPrompt`), `:255-261` (textarea, `MAX_PROMPT_CHARS = 10000`, placeholder teaches `##` section headers: Focus Areas, Credentials, Exclude, Coverage, Output).
- `buildFinalPrompt()` appends a `## Credentials` section from structured fields: `page.tsx:111-120`.
- `handleStartRun()` → `createRun.mutate({ projectId, userPrompt })`: `page.tsx:123-133`.
- `useCreateRun` → `runsService.create(projectId, userPrompt)`: `frontend/src/hooks/use-api.ts:140-156`.
- Wire body is `{ project_id, user_prompt }`: `frontend/src/services/api.service.ts:76-80`.

**Critical mismatch:** `userPrompt` is **not** a field of the declared `CreateRunRequest` DTO (`app/schemas/trigger.py:152-190`). The endpoint reads a raw dict instead (§Stage 2). The structured DTO — `scope.include_pages`, `scope.exclude_pages`, `scope.max_crawl_depth`, `scope.max_pages`, `execution_mode.crawl_strategy`, `test_level` — is **never populated by the frontend**; every run is effectively "full crawl, regression, depth 5, 50 pages" regardless of prompt.

**Analysis panel is decorative:** `handleAnalyzePrompt()` (`page.tsx:136-151`) calls `POST /runs/analyze-prompt` and renders the returned `parsed_intent`/`execution_plan` (`page.tsx:366-398`). The comment on `:387` claims *"Use parsed_intent from analysis so the run gets structured context"* — but `onApprove` just calls `handleStartRun(finalPrompt)` with the **raw text** (`page.tsx:386-390`). The analysed `parsed_intent` is discarded. The backend re-parses anyway, so this is wasted work and misleading UI, not a correctness bug.

### Stage 2 — API layer

- `POST /runs` (`app/api/routes/trigger.py:93-207`). `raw_prompt = body.get("user_prompt") or body.get("test_instructions") or ""` (`:120`).
- **Parsing happens here in the API handler**, not in a dedicated node: `parser.parse(raw_prompt)` (`:137-139`).
- `CreateRunRequest` built with hardcoded `scope={"max_pages": 50, "max_depth": 5}` (`:129-132`). Note `max_depth` is **not** a field of `ScopeInput` (it is `max_crawl_depth`, `app/schemas/trigger.py:75-80`); Pydantic silently drops it (`extra="ignore"` default), so max crawl depth stays the default 5 and the intended 5 is coincidental.
- Intent + raw prompt persisted on the run entity (`:170-178`): `prompt_context_json=parsed_intent.to_dict()`, `user_prompt_text`, `user_prompt_redacted_text`.
- Background workflow started with `user_prompt=raw_prompt` and `prompt_context=parsed_intent.to_dict()` (`:193-196`).
- Approve → `_run_post_review_workflow` → `continue_platform_workflow(...)` — **no `user_prompt` / `prompt_context` argument in the signature** (`:422-428`); it reloads `prompt_context_json` from the DB itself (`app/workflows/trigger_workflow.py:1423-1441`).
- Resume → `execute_resume_workflow` re-passes both (`app/api/routes/trigger.py:1050-1052`).
- `POST /runs/analyze-prompt` (`:1090-1156`) → `prompt_analyzer.analyze()`. Deterministic, no LLM (`app/services/prompt_analyzer.py:11-13`), feeds the UI panel only.

**Security observation:** `user_prompt_redacted_text=parsed_intent.raw_text` (`trigger.py:172-173`) — redacted and non-redacted fields are set to the **same value**. `raw_text` is only redacted when a `_CRED_PATTERNS` regex matched; credentials not matching the 7 regexes (e.g. passwords separated by other text) are persisted verbatim in the DB.

### Stage 3 — Intent parser (PromptParser)

File: `app/services/prompt_builder.py`.

- Entry: `parse()` (`:171-185`) → `_extract_credentials` → `_redact_credentials` → `_parse_sections`.
- Section-header parsing (`:210-244`): splits on `## Focus Areas / ## Exclude / ## Coverage / ## Output` (`_SECTION_HEADERS`, `:38-44`). Works when the user uses headers.
- No headers → heuristic extraction (`:232-236`):
  - `_heuristic_focus` (`:283-331`): three strategies — verb-phrase regex, "X page/module" regex, then **fallback keyword scan over the WHOLE text** against `_COMMON_MODULE_KEYWORDS` (`:57-63`) — **ignoring negation**. `"ignore Reports"` matches the `reports` keyword and becomes a focus area.
  - `_heuristic_exclusions` (`:393-403`): single regex for `ignore/skip/exclude …`.
  - `_heuristic_coverage` (`:405-413`): keyword scan.
- `only`/`just` scope restriction (`:238-243`): if `_has_only_constraint` (`:416-419`) and focus areas exist, `included_pages = _focus_areas_to_url_patterns(focus_areas)` (`:421-432`).
- `_focus_areas_to_url_patterns` embeds a regex-literal in the slug: `user(?:-|_|)management` (verified output). It happens to work because the crawler uses the string as a regex, but it is fragile and opaque.

**Empirically verified output (§1):** `"Crawl only Create RRF and ignore Reports"` → `focus_areas=['Reports']`, `excluded_modules=['Reports']`, `included_pages=['reports']`. Root causes: (a) `crawl` is not in the verb list, so `Create RRF` is never captured; (b) the keyword scan adds the *excluded* module as a *focus*; (c) the `only` clause then turns that wrong focus into a crawl allow-list.

**Code smell:** `_clean_focus_name` is defined twice (`:378-382` and `:385-391`); the first is dead code.

### Stage 4 — Execution planner

**There is no execution planner.** The "planner" is two linear LangGraphs:

- Pre-review: `create_platform_workflow` — Trigger → Crawler → Inventory → Test Design → END (`app/workflows/trigger_workflow.py:1174-1187`).
- Post-review: `create_post_review_workflow` — Human Review → Code Generation → (conditional) Execution (`:1190-1251`).
- `create_unified_workflow` (`:1254-1297`) adds checkpoint skipping via `_with_checkpoint` (`:1154-1171`).

No node decides *what* to do based on intent (e.g. skip crawl when `crawl_strategy="skip"`, restrict to focus pages, choose smoke vs regression). `execution_mode` is parsed into the DTO but never read by the workflow.

**Workflow state** `PlatformWorkflowState` carries `user_prompt`, `prompt_context` (ParsedPromptIntent serialised), `auth_context` (`:33-39`) — the transport is correct. Intent is lost at the boundaries, not in the state.

### Stage 5 — Crawler

Node: `app/workflows/trigger_workflow.py:183-301`. Agent: `app/agents/crawler_agent.py`. Service: `app/services/crawler_service.py`.

- Scope derivation in the node (`:211-225`): `included_pages = prompt_context.included_pages`, and **if empty, ALWAYS derives include patterns from `focus_areas`** (`PromptParser._focus_areas_to_url_patterns(focus_areas)`). So naming *any* focus module — even without "only" — restricts the crawl to that module's URL patterns.
- `exclude_pages` from prompt_context passed, but **`excluded_modules` is never passed to the crawler** (`:222-225`). Only the inventory stage sees `excluded_modules`.
- Agent: `include_patterns = scope_overrides.get("include_pages")` (`crawler_agent.py:102-103`), assigned to `self.service._include_patterns` (`:136-137`).
- **DTO bug:** crawler reads `max_depth = execution_mode.get("max_crawl_depth", 3)` and `max_pages = execution_mode.get("max_pages", 50)` (`crawler_agent.py:94-95`). But `max_crawl_depth`/`max_pages` live under `scope`, and `execution_mode` only has `crawl_strategy`/`test_level` (`app/schemas/trigger.py:33-43`). So the configured scope depth/pages are **silently ignored** — depth is always 3, pages always 50.
- BFS loop (`crawler_service.py:349-527`): bounded by `max_pages`; duplicate-safe via `_queued_urls`/`_visited_urls`; `_should_crawl_url` (`:1232-1252`) applies include/exclude as regexes.
- **Loop / repeated-screenshot candidates:**
  - `_discover_dynamic_links` (`:940-982`) clicks up to **30 nav buttons per page**, waits 300 ms each, records any URL change, extracts links, presses Escape, `go_back`. On SPAs this re-navigates and re-renders pages, and the escaped state is never verified — repeated work per page and possible re-discovery of the same routes.
  - `_frame()` helper that would emit live `BROWSER_FRAME` screenshots is **defined but never called** (`:581-598`; grep confirms no caller). The frontend live-preview (`workflow-store.ts:1152-1154`, `browser-activity.tsx:224-235`) waits for `browser_frame` events that never arrive, so it keeps re-showing the last per-page screenshot (`{page_id}.png`, `:756-779`). This explains the perceived "repeated screenshots / stuck frames".
  - Timeout path re-opens the page for diagnostics + a `.timeout.png` per timed-out URL (`:829-885`).

### Stage 6 — Inventory

`app/services/inventory_aggregator_service.py`.

- `excluded_modules` applied at `:73-76` via `_apply_scope_filter` (`:225-238`): removes pages whose **URL or title** contains the module name (case-insensitive substring).
- **Partial exclusion:** only `pages` are filtered (`:101`). `forms`, `inputs`, `buttons`, `dropdowns`, `tables`, `dialogs`, `api_calls`, `user_flows` are copied **wholesale** from the crawl package (`:145-165`). Excluded modules' forms/buttons/APIs still reach the test-design LLM.
- Substring matching is brittle: `"Reports"` also matches `myreports`, `reportsview`, etc.

### Stage 7 — Test design LLM

`app/agents/test_design_agent.py`.

- PromptBuilder correctly receives parsed intent + raw prompt: `PromptBuildContext(agent_role="test-design-agent", user_prompt_raw, parsed_intent)` (`:194-210`); `PromptBuilder.build` (`app/services/prompt_builder.py:553-626`) puts Scope Constraints (exclude), focus URL patterns, Focus Areas, Coverage Preferences, Output Preferences, Additional Instructions into the messages.
- The user prompt's intent sections are prepended to the inventory message (`test_design_agent.py:286-299`), so the LLM **does** see the parsed intent.
- **The prompt then overrides the intent:** hardcoded coverage requirements (`:395-403`):
  - *"For EVERY page or module discovered, generate a MINIMUM of 8 scenarios"* (`:397`)
  - *"DO NOT stop early. Generate ALL scenarios."* (`:401`)
  - *"If the user's instructions mention a specific page or module, generate EXTRA depth for that area (minimum 10 scenarios)"* (`:400`) — i.e. focus areas only get *more* depth; nothing tells the LLM to **skip** non-focus modules.
- Temperature 0.7, `max_tokens` default 4096 (`:407-412`); retried 3× via `with_retry` (`app/llm/openai_client.py:50`).

Net effect: even when the parser works (`"Test only Login"` → focus Login), the LLM is instructed to exhaustively generate for **everything** in the inventory.

### Stage 8 — Human review

- The in-graph `human_review_node` **auto-approves**: `ReviewRequest(... auto_approve=True, general_comments="Auto-approved by system")` (`app/workflows/trigger_workflow.py:668-674`).
- The user-facing gate is entirely manual/artificial: `execute_platform_workflow` returns, then `_run_pre_review_workflow` sets status `PAUSED` (`app/api/routes/trigger.py:51`); the user must call `POST /runs/{id}/approve`, which runs `continue_platform_workflow` — whose `human_review` node **also auto-approves** (`trigger_workflow.py:1453-1457`).
- No intent context (focus/exclude/coverage) is shown to or used by the review step. Review UI endpoints (`getReview` etc.) serve the test plan only.

### Stage 9 — Code generation

- Node passes `output_preferences` from `prompt_context` (`trigger_workflow.py:790-812`), plus `approved_test_plan_path`, `base_url`.
- **`CodeGenerationAgent.execute` reads only `workspace_path`, `approved_test_plan_path`, `base_url`, `overwrite`** (`app/agents/code_generation_agent.py:124-127`). `output_preferences` is **never read** — dead parameter. `user_prompt`, `focus_areas`, `excluded_modules`, `coverage_preferences` are absent.
- IR generation (`app/agents/ir_generation_agent.py:82-90`) receives only `approved_test_plan` + `base_url`; the IR prompt composer builds from the approved plan's pages/scenarios only (`app/core/ir/prompt_composer.py:30-85`). No intent reaches the IR LLM.
- Code is generated deterministically from IR via `TemplateEngine` (`code_generation_agent.py:78`, docstring `:44-61`).

### Stage 10 — Execution

- `execution_node` calls `execution_service.execute_tests(run_id, project_path, config=None)` (`trigger_workflow.py:995-1000`). `config=None` → default `ExecutionConfig` (`app/services/execution_service.py:51-52`).
- `ExecutionAgent.execute` reads `run_id`, `execution_id`, `project_path`, `config`, `skip_install` (`app/agents/execution_agent.py:35-45`).
- **No user prompt, scope, focus, or coverage input exists at this stage.** All generated spec files run. There is no smoke-only option, no module filtering, no way to run "only boundary tests" at execution time.

---

## 3. Context-Propagation Table (per stage)

`✓` = intent element present · `✗` = absent · `~` = partial/corrupted

| Intent element | 1 FE | 2 API | 4 State | 5 Crawler | 6 Inventory | 7 Test Design | 8 Review | 9 Codegen | 10 Execution |
|---|---|---|---|---|---|---|---|---|---|
| Raw user prompt | ✓ | ✓ persist | ✓ | ✗ | ✗ | ✓ (into prompt) | ✗ | ✗ | ✗ |
| focus_areas | (n/a) | ✓ parse | ✓ | ~ (used to restrict crawl) | ✗ | ✓ (extra depth only) | ✗ | ✗ | ✗ |
| excluded_modules | (n/a) | ✓ parse | ✓ | ✗ (not sent) | ~ (pages only) | ✓ (scope constraint note) | ✗ | ✗ | ✗ |
| included_pages | (n/a) | ✓ parse | ✓ | ✓ regex restrict | ~ | ✓ | ✗ | ✗ | ✗ |
| coverage_preferences | (n/a) | ✓ parse | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| output_preferences | (n/a) | ✓ parse | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ (passed but unread) | ✗ |
| custom_instructions | (n/a) | ✓ parse | ✓ | ✗ | ✗ | ✓ | ✗ | ✗ | ✗ |
| Execution plan | ✗ (panel only) | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |

---

## 4. Root-Cause Analysis

### RC-1 (P0) — Intent parser corrupts scope: negated modules become focus areas and `only` restricts the crawl to the wrong module
`app/services/prompt_builder.py:283-331` (whole-text keyword scan ignoring negation) + `:238-243` (`only`/`just` → `included_pages`) + `app/workflows/trigger_workflow.py:215-225` (fallback derive-from-focus). Empirically reproduced. This alone explains "crawls unrelated pages / continues after requested scope / tests the wrong module" for `"Crawl only X and ignore Y"` prompts.

### RC-2 (P0) — Test-design prompt is exhaustive-by-default and overrides scope
`app/agents/test_design_agent.py:395-403` mandates ≥8 scenarios per page/module, ≥15 for login, "DO NOT stop early", "Generate ALL scenarios". Focus areas only request extra depth; nothing requests skipping. Even a correct parse produces a plan for everything.

### RC-3 (P1) — Inventory exclusion is partial and substring-based
`app/services/inventory_aggregator_service.py:101-120,225-238`. Only `pages` are filtered; forms/buttons/APIs/flows from excluded modules still enter the test-design inventory.

### RC-4 (P1) — No execution planner; crawl scope config is dead
`crawler_agent.py:94-95` reads depth/pages from the wrong DTO key (`execution_mode` vs `scope`), so `scope.max_crawl_depth`/`max_pages` are silently ignored. No stage ever interprets `execution_mode.crawl_strategy`/`test_level`.

### RC-5 (P1) — Intent fully severed after review
`CodeGenerationAgent` drops `output_preferences` (`code_generation_agent.py:124-127`); IR prompt composer is plan-only (`prompt_composer.py:30-85`); `ExecutionService`/`ExecutionAgent` accept no intent (`execution_service.py:24-62`, `execution_agent.py:35-45`). The human-review gate is auto-approve (`trigger_workflow.py:668-674,1453-1457`), so nothing intercepts the corruption before codegen.

### RC-6 (P2) — Dead/misleading UX paths
`_frame()` never called (`crawler_service.py:581-598`) → live browser preview never updates, re-shows stale per-page screenshot (perceived "repeated screenshots"). Analysis panel (`page.tsx:386-390`) discards its own `parsed_intent`; `user_prompt_redacted_text == user_prompt_text` (`trigger.py:172-173`) persists unredacted credentials for non-matching formats.

### RC-7 (P2) — Key naming/typing mismatch
Frontend sends `{project_id, user_prompt}` while the declared DTO `CreateRunRequest` (`app/schemas/trigger.py:152-190`) has `target_application`, `scope`, etc. — the DTO is effectively dead contract, inviting drift.

---

## 5. Missing Architecture Components

1. **Intent contract as a first-class artifact** — `ParsedPromptIntent` exists but is only serialised to the DB; it is never written as a `contracts/user-intent.json` that every downstream node must read. Downstream agents get hand-picked slices.
2. **Execution planner node** — a node that turns `ParsedPromptIntent` + `execution_mode` into a concrete step plan (crawl-only pages matching include patterns, skip crawl when `crawl_strategy="skip"`, smoke vs regression, module whitelist/blacklist for test design AND codegen AND execution).
3. **Deterministic scope enforcement at every stage** — include/exclude lists applied to crawler, inventory (all component types, not just pages), test-design prompt (hard skip, not "extra depth"), codegen (scenario filter), execution (spec-file filter / smoke mode).
4. **Intent-aware test-design instruction layer** — replace the "generate ALL, ≥8 per page" block with scope-aware directives (e.g. "only modules X", "skip Y", "boundary/negative only").
5. **True human review with intent context** — show parsed intent + scope alongside the plan; require approval to be explicit; pass approval edits back into codegen.
6. **Output-preference plumbing** — actually consume `output_preferences` in `CodeGenerationAgent` → `IRGenerationAgent` prompt.
7. **Live-frame mechanism** — either call `_frame()` at bounded intervals or remove `BROWSER_FRAME` from the UI contract.
8. **Unified request DTO** — align `runsService.create` payload with `CreateRunRequest` (or vice-versa) so scope/execution-mode from the UI can flow in.

---

## 6. Recommendations (Priority)

### P0 — fix intent corruption (highest impact, low risk)
- Rewrite `_heuristic_focus` to respect negation: tokenise the prompt, remove the *entire* excluded clause from the focus scan before keyword matching, and only promote a focus area to `included_pages` when the clause is genuinely exclusive (`only X`/`just X`), not merely named.
- Add `crawl` / `test only` / `generate for` / `create` to the verb list so `"Crawl only Create RRF…"` is captured.
- Make `_focus_areas_to_url_patterns` produce plain slugs; keep the multi-form matching inside `_should_crawl_url` as an explicit, tested expansion.
- Do **not** derive `included_pages` from `focus_areas` in `crawler_node` unless the parsed intent is actually exclusive (drop the fallback at `trigger_workflow.py:216-221`).

### P1 — enforce scope downstream
- Hard scope directives in the test-design prompt: "Test ONLY the following modules: … ; generate nothing for excluded modules … ; if only coverage types are requested (negative/boundary), produce ONLY those categories." Remove/replace the "Generate ALL scenarios / ≥8 per page" block for scoped runs.
- Filter the *entire* inventory (forms, buttons, inputs, dialogs, API calls, user flows) by excluded modules, and match against module-derived URL prefixes, not substrings.
- Fix `crawler_agent.py:94-95` to read `scope.max_crawl_depth` / `scope.max_pages`; honour `crawl_strategy="skip"` by skipping the crawler node.
- Thread `parsed_intent` (or the approved-plan subset) into `CodeGenerationAgent` → IR prompt, and consume `output_preferences`.
- Add a post-review spec filter / smoke-mode to `ExecutionService` so execution honours scope.

### P2 — correctness & UX hygiene
- Call `_frame()` or remove the dead helper; otherwise the live preview is misleading.
- Set `user_prompt_redacted_text` from `parsed_intent.raw_text` after redaction and unit-test the redactor with realistic credential formats.
- Either forward the analysis panel's `parsed_intent` to run creation or remove the "structured context" comment/claim.
- Delete the duplicate `_clean_focus_name` (`prompt_builder.py:378-382`).
- Reconcile `CreateRunRequest` DTO with the actual wire contract and populate `scope` from the UI.

---

## 7. Verified vs. Unverified

**Verified (code + empirical run):** parser outputs for all 5 example prompts (§1, §2.3); `only` → `included_pages`; crawler include/exclude regex path; inventory page-only filtering; auto-approve review nodes; `output_preferences` dropped in `CodeGenerationAgent`; no intent input to `ExecutionService`/`ExecutionAgent`; dead `_frame()` (grep: no caller); `max_depth`/`max_pages` read from `execution_mode` not `scope`.

**Unable to verify from the current code:**
- Whether the LLM (default `gpt-4`, `app/config/settings.py:70`) actually obeys vs. overrides the scope directives — requires a live run + prompt capture.
- Exact runtime crawl counts / screenshot repetition in a live browser (no run data inspected; UI-side interpretation inferred from `workflow-store.ts`).
- Whether `analyze-prompt`'s discarded `parsed_intent` causes user-visible confusion in practice (UI behaviour not exercised).
- Whether real RRF URLs would match derived patterns like `create(?:-|_|)rrf` (app-specific).
- Log-level redaction of credentials in structured events (only the DB field mismatch at `trigger.py:172-173` is proven).

---

*Generated during a read-only audit. No code was modified. All file references are relative to the repository root (`project-foundation/` prefix for application code).*

# FINAL Engineering Audit Report

**Read-only audit · 10 audits · 14-item deliverable · Date: 2026-08-07**
**Repo:** `project-foundation/` (OneDrive path with spaces). **Method:** static code analysis only. Every claim cites `file`, `function`, `line`. Where code does not prove something, the report says *Unable to verify from the current code.*

Scope: browser lifecycle (1), inventory discovery (2), prompt quality (3), performance (4-5), security (6), Playwright quality (7), code quality (8), observability (9), production readiness (10). Prior reports (orchestration/LLM/reasoning, crawler execution, prompt-intent) are referenced, not re-audited.

---

# AUDIT 1 — Playwright / Browser Lifecycle

## 1.1 Browser architecture diagram

```
┌────────────────────────── PROCESS LIFETIME ──────────────────────────┐
│  ONE BrowserManager per process  (dependencies.py:53-61 @lru_cache)  │
│                                                                      │
│  BrowserManager.initialize()            browser_manager.py:56        │
│    ├─ async_playwright().start()        :71                          │
│    ├─ launcher.launch(headless=…, args=[…])  :91                     │
│    │    chromium args: --disable-blink-features=AutomationControlled │
│    │                   (+ --start-maximized / --window-size when headed :87-90)
│    └─ lazy: only when first context requested (:129-130)             │
│                                                                      │
│  PER CRAWL  (CrawlerService.crawl)                                    │
│    create_context()                     browser_manager.py:105       │
│      options: ignore_https_errors=True, bypass_csp=False :135-139    │
│      viewport (headless) | no_viewport (headed) :141-147             │
│      HAR/video opt-in  :150-163                                      │
│      crash-retry: cleanup()+initialize()+retry :165-172              │
│    new_page() :193 → goto() :219 → extract_all() → screenshot() :263 │
│    close_context() :297  (called in crawler finally)                 │
│                                                                      │
│  SHUTDOWN  main.py lifespan :73-74  → logs only                      │
│    BrowserManager.cleanup() :329  is NEVER invoked by the app        │
└──────────────────────────────────────────────────────────────────────┘
```

## 1.2 Verified lifecycle facts

- **Singleton:** `get_browser_manager()` is `@lru_cache()` (`dependencies.py:53-61`); `get_crawler_service()` also a singleton (`:64-67`). One browser process per server process.
- **Lazy init:** `create_context` calls `initialize()` only `if not self._browser` (`browser_manager.py:129-130`); `CrawlerService` also guards on `is_initialized` (`crawler_service.py:155-157`).
- **Context per crawl, closed:** crawler creates one context per crawl (`crawler_service.py:172`) and closes it in a `finally` (`:244-246`). Pages created per URL visit and closed after (`:558`, and page-close in per-page `finally`).
- **No browser teardown anywhere:** the app lifespan shutdown only logs `application_shutdown` (`main.py:73-74`). `BrowserManager.cleanup()` (`:329-361`) is only reachable via `CrawlerService.cleanup()` (`crawler_service.py:132-135`), which no workflow node or lifespan hook calls (verified by grep — the only `cleanup` callers are service definitions, not lifecycle wiring). **Browser and its Playwright subprocess stay resident for the whole process lifetime.**
- **No crash watchdog:** the only recovery is a single context-creation retry that tears down and relaunches the browser (`browser_manager.py:165-172`). A browser crash mid-navigation is surfaced as an exception, not recovered.
- **No popup / download / dialog management:** `context.on("page")`, `page.on("download")`, `page.on("dialog")` are never registered anywhere in `app/`. `target="_blank"` links and file downloads are not tracked.
- **No `storage_state`:** every crawl starts a fresh context — cookies/localStorage are not persisted, so authentication is re-executed on every run even against the same app.
- **Recording:** HAR (`record_har_mode="minimal"`, `:153`) and video (`:156-163`) are supported but opt-in; execution-stage screenshots/video/trace are delegated to the generated project via env flags (`playwright_runner.py:128-135`), not the manager.

## 1.3 Findings (AUDIT 1)

1. **P1 — Browser is never closed between runs or at shutdown.** Resident browser = memory + a single point of failure for the whole process; only process exit reclaims it. `main.py:73-74` should call `BrowserManager.cleanup()`.
2. **P1 — Single shared browser across concurrent runs** (singleton, `dependencies.py:53`). One `BrowserManager`/`CrawlerService` instance serves every workflow task; two concurrent runs share `self._contexts` state.
3. **P2 — `ignore_https_errors=True` on every context** (`browser_manager.py:136`) — TLS verification disabled; see AUDIT 6.
4. **P2 — No popup/download handling** — new-tab flows and downloads are invisible to the crawler and will produce broken generated tests.
5. **P3 — Fresh session each run** — no `storage_state` reuse; login cost paid per run.

---

# AUDIT 2 — Inventory Discovery Completeness

## 2.1 What is extracted

`extract_all(page)` (`dom_extractor.py:221`) runs one in-browser JS function `_EXTRACT_ALL_JS` (`:15-218`) returning typed element metadata.

| Element | Selector | Fields captured | Notes |
|---|---|---|---|
| inputs | `input:not([type=hidden/submit/button/file]), select, textarea` (:57) | type, name, label, placeholder, required, disabled, readonly, max/minLength, autocomplete, id, visible, bbox | labels resolved via `label[for]`, closest `label`, `aria-label`, `placeholder` (:17-30) |
| buttons | `button, input[type=submit/button], a[role=button]` (:83) | text, type, disabled, id, ariaLabel, role, visible | dedup by text/id (:88-90) |
| checkboxes | `input[type=checkbox]` (:107) | name, label, checked, required, disabled, visible | |
| radios | `input[type=radio]` (:120) | name, label, value, checked, visible | |
| dropdowns | `select` (:132) | name, label, options, multiple, disabled, required, visible | |
| forms | `form` (:148) | id, name, action, method, autocomplete, visible | |
| tables | `table` (:167) | id, caption, headers, rowCount, columnCount, visible | |
| dialogs | `dialog, [role=dialog], [aria-modal=true]` (:190) | dialogType (always "modal", :194), title, message (always null, :196), triggerElement (always null, :197) | |
| uploads | `input[type=file]` (:204) | name, label, accept, multiple, required, disabled | |

## 2.2 Coverage gaps (not captured at all)

| Not captured | Implication |
|---|---|
| Menus, tabs, breadcrumbs, nav bars, pagination, sort/filter controls, search bars, date pickers | No navigation-behaviour inventory |
| Headings / text content | No content understanding — the LLM designs scenarios from structure only |
| iframes / shadow DOM / web components | SPA component trees are invisible to `document.querySelectorAll` |
| canvas / svg / virtual lists / lazy-loaded / `IntersectionObserver` content | Client-rendered content may be absent from DOM at extraction time (no `waitForSelector`, AUDIT 7) |
| Anchor `href` links | Handled separately by crawler `_extract_links` (prior crawler audit), not by `_EXTRACT_ALL_JS` |

## 2.3 Robustness defects in the extractor

1. **Dialog extraction can throw and kill the whole page extraction.** `(el.querySelector('[role=heading]') || el.querySelector('h1, h2, h3, h4')).textContent` (`dom_extractor.py:192`) — if a modal has no heading, `null.textContent` throws inside `page.evaluate`, so `extract_all` fails for the entire page (no `try` in the JS).
2. **`isVisible` misclassifies `position:fixed` elements.** `if (el.offsetParent === null && el !== document.body) return false;` (`:33`) — fixed-position elements (modals, headers, sticky bars) report `offsetParent === null` and are marked invisible even when on screen.

## 2.4 Verdict (AUDIT 2)

Strong for conventional form/CRUD apps (label association, visibility filtering, bounding boxes all present). Weak for modern component-heavy SPAs: no iframe/shadow-DOM traversal, no text/heading capture, no interaction-behaviour (sort/filter/pagination) discovery, plus the two robustness defects in §2.3. **Coverage score: 6/10** for the target app class, **3/10** for component-heavy or canvas/iframe apps.

---

# AUDIT 3 — Prompt Quality

## 3.1 Inventory of prompt assets

| Prompt | Location | Lines | Score | Notes |
|---|---|---|---|---|
| Test Design Agent | `prompts/test-design-agent.md` | 34 | 6.5/10 | Role + coverage-density rules + constraints + "output valid JSON only". **No JSON schema, no field contract, no example, no priority/risk taxonomy, no module-grouping guidance.** Schema is enforced only downstream by Pydantic `TestPlan` + regex JSON repair. |
| AI Crawler Agent | `prompts/ai-crawler-agent.md` | 1 | 1/10 | Single sentence, no extraction schema, no format/output guidance. **Vestigial:** the crawler never calls an LLM (inventory extraction is deterministic DOM, `dom_extractor.py`). |
| IR generation | `app/core/ir/instruction_builder.py:21-464` | 444 | 7/10 content / 4/10 ops | Best-in-repo content: complete JSON schema, worked example, action/assertion enums, locator priority, `$ENV_VAR` data syntax. **But it is embedded in code, not a versioned prompt file; the call site passes `prompt=` with NO system message (`ir_generation_agent.py:221`); and there is no `response_format` JSON schema — correctness relies on prose + post-hoc repair.** |
| Code generation | none | — | n/a | Deterministic `TemplateEngine` (no LLM prompt). |
| Test-design system prompt | `PromptBuilder._build_system` `prompt_builder.py:568-603` | — | — | Loads `test-design-agent.md` via `get_prompt(ctx.agent_role)` (`prompt_loader.py`, Jinja2 `FileSystemLoader` on `settings.prompt.prompt_base_path` default `./prompts`, `settings.py:227`). |

## 3.2 Key quality issues

1. **`test-design-agent.md` demands "ALL scenarios" and "≥8 per module, ≥15 for auth" (`prompts/test-design-agent.md:18-23`) inside a 4096-token output cap** (`settings.py:72`) with a large inventory input — truncation is the likely failure mode (reinforces AUDIT 4).
2. **No output contract in the prompt** — the LLM guesses the JSON shape; `_extract_json` regex repair + Pydantic validation have to paper over drift.
3. **No structured output** — `response_format={"type":"json_object"}` exists in the client (`openai_client.py:209`, per prior audit) but is unused at all three call sites.
4. **Crawler prompt is a stub** — dead prompt, no harm to runtime but signals unfinished design.

---

# AUDIT 4 — LLM Performance: why stages take 5–30 minutes

## 4.1 The three LLM call sites (entire "AI" surface)

| # | Call site | Purpose | Temp | Output cap | Timeout budget |
|---|---|---|---|---|---|
| 1 | `test_design_agent.py:407` | test plan JSON from inventory | 0.7 (`settings.py:71`) | 4096 | SDK `wait_for` 900s (`openai_client.py:108-117`) + `@with_retry` 3 attempts (`openai_client.py:50`); **no node-level cap** |
| 2 | `ir_generation_agent.py:221` | IR JSON from approved plan | 0.3 | 4096 | `asyncio.wait_for(..., 960s)` `:212/:220-227` |
| 3 | `ir_generation_agent.py:772` | IR refinement (loop ≤3) | 0.2 | 4096 | `asyncio.wait_for(..., 960s)` `:769-778` |

## 4.2 Worst-case timing math

- **IR stage alone:** initial + ≤3 refinements = 4 completions, each up to 960s → **≈64 min worst case**, each refinement re-embedding the *entire* IR JSON (`ir_generation_agent.py:738-740`). The real ceiling is the node cap `asyncio.wait_for(code_gen_agent.execute(...), 1800s)` (`trigger_workflow.py:833-838`, env `CODE_GENERATION_TIMEOUT_SECONDS`, `:831`), which on timeout produces `CODE_GENERATION_FAILED`/`TimeoutError` (`:840-849`).
- **Test design:** up to 3 × 900s ≈ **45 min worst case**, and no stage-level cap bounds it.
- **Why 5–30 min in practice:** sequential calls on default `gpt-4` (`settings.py:70`) with large prompts (full inventory; full approved plan via `ContextBuilder`/`ScenarioBuilder`; full IR re-sent per refinement), a 4096-token output cap, high input sizes, plus up to 3 transport retries per call. Not CPU-bound — it is pure serial LLM latency.

## 4.3 Supporting performance facts

- Token accounting is word-counting `len(prompt.split())` (`ir_generation_agent.py:150,230`), not real tokenization.
- No context compaction/truncation strategy in `complete`; no result caching across runs (no memory subsystem).
- **Config drift hazard:** `.env.example` sets `OPENAI_TIMEOUT=60` (`.env.example:43`) but `settings.py:73` defaults `openai_timeout=900`. Copying the example `.env` silently shrinks every LLM call to 60s → routine timeouts/truncation.

## 4.4 Blocking event-loop subprocess (cross-cutting, AUDIT 4+5)

`subprocess.run(..., shell=True)` is called **synchronously from async functions**, blocking the entire asyncio event loop:

- `environment_manager.py:79,88,97,108` (node/npm/npx probes), `:136` (`npm install`, `timeout=300`), `:156` (`npx playwright install`, `timeout=600`), `:179,194` (validation probes)
- `playwright_runner.py:147-157` — test execution, `timeout = config.timeout_ms // 1000 + 300` default **1800s** (`:36`)

During any of these, **the whole server freezes**: all SSE streams, all API endpoints, all concurrent workflows. This is the single most severe performance defect (see AUDIT 5).

---

# AUDIT 5 — System Performance

1. **Event-loop blocking (critical).** See §4.4. Every execution stage (`EnvironmentManager`, `PlaywrightRunner`) is a blocking `subprocess.run` on the loop. Fix: `asyncio.to_thread` / `asyncio.create_subprocess_exec`.
2. **Event bus drops events under load.** Subscriber queues are capped at 512 (`event_bus.py:230`); when full, `publish` logs a warning and **drops the event** (`:262-269`) — silent data loss for the UI, no backpressure to producers. Replay buffer capped at 200 (`:237`); SSE heartbeats every 15s (`:322-327`).
3. **Unbounded log growth.** File handler is a plain `logging.FileHandler` (`logging/config.py:154-157`) — `LOG_FILE_ROTATION=10MB`/`LOG_FILE_RETENTION=30` (`.env.example:83-84`) are never applied.
4. **Browser memory held for process lifetime** (AUDIT 1.3-1).
5. **Crawler is serial** — one page at a time in BFS (prior crawler audit); no concurrency in the crawl path.
6. **LLM calls have no cross-run cache** and retries re-pay full cost.

---

# AUDIT 6 — Security

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **`shell=True` subprocess (7 sites) → command-injection surface.** Command lists are mostly fixed, but `PlaywrightRunner._build_command` appends `--grep <value>` (`:99`) and `test_file` (`:101-102`) from `ExecutionConfig`, then runs with `shell=True` (`:156`). Shell metacharacters in grep/test_file are interpreted. | Med | `playwright_runner.py:76-110,147-157`; `environment_manager.py:79-114,136-173,179-196` |
| 2 | **No authentication / API-key enforcement.** `.env.example` defines `SECRET_KEY` and `API_KEY_HEADER` (`:26-28`) but `middleware.py` implements only correlation/logging/scrub/exception middleware — no auth check. Any client can `POST /runs` and consume LLM quota, disk, and browser resources. No rate limiting. | High | `main.py:99-113`; `middleware.py` |
| 3 | **CORS wildcard + credentials.** `allow_origins=["*"]` with `allow_credentials=True` (`main.py:100-106`) — invalid per CORS spec (browsers reject the combination) and, if relaxed, a credential-leak vector. | High | `main.py:100-106` |
| 4 | **TLS disabled for the crawler.** `ignore_https_errors=True` on every context (`browser_manager.py:136`) — MITM can tamper with crawled content and credentials. | Med | `browser_manager.py:135-139` |
| 5 | **Crawl-seed origin not constrained.** The root URL is derived from the run's `next` parameter (prior crawler audit); the same-domain filter applies only to discovered links, not the seed — a crafted `next` can make the crawler visit an arbitrary origin (open-redirect → crawler SSRF). | Med | `crawler_service.py` `_derive_root_url` |
| 6 | **Credential-at-rest fallbacks.** `CredentialStore` encrypts with Fernet (`prompt_builder.py:493-516`), but (a) falls back to a per-process key when `CREDENTIAL_ENCRYPTION_KEY` is unset (`:476-484`) and (b) stores **plaintext** `run_credentials.json` if `cryptography` is missing (`:509-512`). Prod must pin the key and fail closed. | Med | `prompt_builder.py:440-537` |
| 7 | **Placeholder secrets baked into image.** `COPY .env.example ./.env` (`Dockerfile:25`). | Low | `Dockerfile:25` |
| 8 | **Error text printed to stdout.** Crawler prints `ERROR DETECTED: {error_text[:100]}` (prior crawler audit) — can surface sensitive page error content in logs. | Low | `crawler_service.py` |
| 9 | **No `eval`/`exec`/`os.system` anywhere** (grep clean) — only `subprocess`. Exception handler returns a generic 500 without internals (`middleware.py:223-248`). | Good | — |
| 10 | **Generated-project `.env` holds credentials in plaintext** on the workspace disk (`environment_manager.py:221-242`) — normal for Playwright, but the workspace must be access-controlled. | Info | — |

---

# AUDIT 7 — Playwright Quality

1. **Good:** IR generation mandates semantic locator priority (role → label → placeholder → text → testId → css → xpath) with `fallback_locators` (`instruction_builder.py:177-185,139-148`).
2. **Good:** crawler uses `wait_until="domcontentloaded"` (prior crawler audit), deliberately avoiding `networkidle`; `bypass_csp=False` (`browser_manager.py:138`).
3. **Bad — hardcoded sleeps.** Login flow uses fixed `wait_for_timeout(2000/3000)`; dynamic-link discovery uses `300ms` + 1500ms click timeout (prior crawler audit). Flaky on slow networks; no `waitForSelector` for SPA render completion.
4. **Bad — no SPA render wait.** Extraction happens after `domcontentloaded`; client-rendered content not yet in DOM is missed (AUDIT 2.2). No `page.wait_for_selector`/network idle heuristics.
5. **Bad — no popup/download/dialog handlers** (AUDIT 1.2) — generated tests for `target=_blank` flows are unreliable.
6. **Bad — no session reuse** (`storage_state` unused) — login re-run every crawl (AUDIT 1.2).
7. **Partial — failure evidence.** Screenshots/video/trace on failure are supported and wired through env flags to the generated project (`playwright_runner.py:128-135`); the crawler captures full-page screenshots (`browser_manager.py:263-268`, `full_page=True`) which can be very large.
8. **Retries:** context creation retries once after full teardown/re-init (`browser_manager.py:165-172`); crawl navigation uses a small exponential backoff (prior crawler audit). No retry for screenshots/HAR finalisation.

---

# AUDIT 8 — Code Quality

1. **Dead code — duplicate generator.** `app/generators/playwright_project_generator.py` (`PlaywrightProjectGenerator`) is exported only in `generators/__init__.py:7,10` and imported nowhere else; the live path is `TemplateEngine` (`app/generators/template_engine.py`) + `ArtifactWriter` (`app/core/artifact_writer.py`). Dead duplicate generation path.
2. **Validator is heuristic, not a compile.** `CodeValidator.validate_project` (`code_validator.py:35-67`) only counts braces/parens (`:276-300`) and `any` occurrences (`:303-314`), checks imports by file existence (`:397-428`) — it cannot catch real TypeScript syntax errors and never runs `tsc --noEmit`. "Validated" code can be uncompilable.
3. **Singleton mutation races.** All agents/services are `lru_cache` singletons (`dependencies.py:23-107`); `CodeGenerationAgent.execute` writes per-run ids onto shared instances (`code_generation_agent.py:267,329`), and `BrowserManager`/`CrawlerService` share one browser across concurrent runs (prior orchestration audit §12.1; AUDIT 1.3-2). Cross-run SSE leakage is possible.
4. **Config drift.** `OPENAI_TIMEOUT` 60 (`.env.example:43`) vs 900 (`settings.py:73`); rotation settings unused (AUDIT 5.3); `docker-compose.yml` declares named volumes (`:34-37`) but mounts bind volumes (`:15-19`); `DATABASE_URL` references Postgres but compose has no Postgres service; `API_WORKERS=4` (`.env.example:20`) is ignored by the single-process uvicorn CMD (`Dockerfile:46`).
5. **Hardcoded values that contradict configuration.** `ContextBuilder.build_environment_context` hardcodes browsers `["chromium","firefox","webkit"]` (`context_builder.py:52`); IR `metadata.model_used` hardcodes `"deepseek-v4-flash-free"` regardless of the configured `gpt-4` (`ir_generation_agent.py:620`, prior audit).
6. **Misleading telemetry.** `LLM_CALL_COMPLETED.response_tokens` is actually `scenario_count` (`trigger_workflow.py:485-488`, prior audit).
7. **Wrong middleware-order comment.** `main.py:108` says "first added = outermost" — in Starlette the **last** added is outermost. Functionally harmless (CorrelationID ends up outermost as intended) but the comment is wrong.
8. **DOM extractor defects** that can abort or misclassify whole pages — §2.3.
9. **Deprecated API:** `datetime.utcnow()` (`health.py:47`).
10. **Strictness is configured but unenforced.** `pyproject.toml` enables strict mypy (`:125-137`) and ruff; there is no CI pipeline (`.github/` absent) to run lint/type/test gates.

---

# AUDIT 9 — Observability

| Good | Gap |
|---|---|
| Structured JSON logging (structlog) with correlation/request/component context (`logging/config.py:19-76,103-132`) | **No log rotation** — unbounded `FileHandler` (`logging/config.py:154-157`) |
| HTTP request/response logging with duration + status (`middleware.py:47-104`) | `httpx`/`openai`/`urllib3` suppressed to WARNING (`logging/config.py:160-163`) hides LLM/HTTP debug |
| Sensitive-body scrubbing for `POST /api/v1/runs` at DEBUG (`middleware.py:163-176`) | Scrubbing is debug-level only and path-limited |
| Rich SSE event stream (~90 `EventType`s, `event_bus.py:40-169`); PING heartbeats; replay buffer | Events dropped when a subscriber queue is full (`event_bus.py:262-269`); many "AI reasoning" events are scripted, not real traces (prior audit §9) |
| Retry attempts logged at WARNING, exhaustion at ERROR (`retry.py:67,128`) | — |
| Health endpoints: `/health/`, `/health/ready`, `/health/live`, `/health/db` (`health.py`) | **Readiness never checks browser/node/LLM availability** — reports "ready" even when execution would fail (`health.py:52-78`) |
| DB metrics + migration head exposed at `/health/db` (`health.py:94-143`) | No LLM-call/token/duration metrics; `TELEMETRY_ENABLED=false`, `TRACING_ENABLED=false` defaults (`.env.example:90-92`) |
| `log_execution_time` decorator available (`logging/config.py:207-283`) | Applied nowhere in the audited hot paths |

**LLM telemetry is incomplete:** events exist (`LLM_CALL_STARTED/COMPLETED`, `event_bus.py:82-83`; `LLM_TIMEOUT`/`LLM_ERROR`, `:115-116`) but the token count is a fabricated value (AUDIT 8.6) and per-call latency/prompt-size are not recorded.

---

# AUDIT 10 — Production Readiness

| # | Finding | Severity | Evidence |
|---|---|---|---|
| 1 | **Docker image cannot run crawls or execute tests.** `python:3.12-slim` (`Dockerfile:2`) has **no Node.js**, and the image never runs `playwright install`/`playwright install-deps`. Execution uses `npm install` (`environment_manager.py:136`) and `npx playwright test` (`playwright_runner.py:77`) — both fail in the container. The healthcheck still reports healthy. | Critical | `Dockerfile:2-46` |
| 2 | **Healthcheck is shallow** — only `/health/` static response (`Dockerfile:42-43`); no readiness gate on Node/browser/LLM (AUDIT 9). | Med | `Dockerfile:42-43` |
| 3 | **No CI/CD pipeline** — `.github/` absent; lint/type/test gates in `pyproject.toml` never run automatically. | Med | repo tree |
| 4 | **No graceful browser shutdown** — app lifespan only logs (`main.py:73-74`); browser subprocess leaks on SIGTERM (AUDIT 1). | Med | `main.py:28-75` |
| 5 | **No auth/rate-limiting** on the API (AUDIT 6.2) — production exposure for a resource-heavy service. | High | `main.py`, `middleware.py` |
| 6 | **Multi-worker mismatch** — `API_WORKERS=4` (`.env.example:20`) vs single-process uvicorn CMD (`Dockerfile:46`); in-memory event bus/browser singletons are per-process, so multi-worker would break SSE and double browser resources. | Med | `.env.example:20`, `Dockerfile:46` |
| 7 | **Secrets handling** — `OPENAI_API_KEY` via env only; `CREDENTIAL_ENCRYPTION_KEY` documented as required for prod (`prompt_builder.py:479-484`) but not enforced at startup. | Med | `.env.example:34`, `prompt_builder.py:476-484` |
| 8 | **Startup validation exists** — persistence flags validated (`main.py:45-58`) and dependency/import checks (`main.py:62-69`, `app/validation/startup_checks.py`); good foundation, but LLM-key presence not verified here. | Info | `main.py:45-69` |
| 9 | **Postgres is additive and gated** — dual-repo wiring only activates when `postgres_enabled` (`dependencies.py:172-202`); file-based is the default. | Info | `dependencies.py:172-202` |
| 10 | **Tests exist** (`tests/`) but no runtime verification of coverage in this audit; no CI gate. | Info | `pyproject.toml:61-80` |

---

# DELIVERABLE 9 — Exact files responsible

| Concern | File(s) |
|---|---|
| Browser lifecycle | `app/infrastructure/browser_manager.py`, `app/dependencies.py:53-67`, `app/main.py:28-75` |
| Crawling & session | `app/services/crawler_service.py` |
| Inventory/DOM discovery | `app/services/dom_extractor.py`, `app/services/inventory_aggregator_service.py` |
| Prompt assembly | `prompts/test-design-agent.md`, `prompts/ai-crawler-agent.md`, `app/prompts/prompt_loader.py`, `app/services/prompt_builder.py`, `app/core/ir/instruction_builder.py`, `app/core/ir/context_builder.py`, `app/core/ir/scenario_builder.py` |
| LLM latency | `app/llm/openai_client.py`, `app/agents/test_design_agent.py`, `app/agents/ir_generation_agent.py`, `app/workflows/trigger_workflow.py:733-935` |
| Execution blocking | `app/execution/playwright_runner.py`, `app/execution/environment_manager.py`, `app/services/execution_service.py` |
| Security | `app/main.py:99-113`, `app/api/middleware.py`, `app/services/prompt_builder.py:440-537`, `app/execution/*.py`, `Dockerfile` |
| Code quality | `app/core/code_validator.py`, `app/generators/playwright_project_generator.py` (dead), `app/generators/template_engine.py`, `app/services/dom_extractor.py` |
| Observability | `app/logging/config.py`, `app/api/middleware.py`, `app/core/event_bus.py`, `app/api/health.py`, `app/utils/retry.py` |
| Production readiness | `Dockerfile`, `docker-compose.yml`, `.env.example`, `pyproject.toml` |

# DELIVERABLE 10 — Exact functions responsible

| Function | File:line | Impact |
|---|---|---|
| `BrowserManager.initialize` / `create_context` / `navigate` / `cleanup` | `browser_manager.py:56,105,219,329` | browser lifecycle, TLS off, no teardown |
| `CrawlerService.crawl` (+ login/session/discovery) | `crawler_service.py:129-246` and related | per-run browser use, seed origin |
| `extract_all` / `_EXTRACT_ALL_JS` | `dom_extractor.py:221,15-218` | inventory coverage + abort-on-no-heading bug |
| `OpenAIClient.complete` | `openai_client.py` (~`:50-166`) | all LLM latency; 900s SDK cap; retries |
| `IRGenerationAgent.execute` / `_validate_and_refine_ir` | `ir_generation_agent.py:58-126,670-720` | dominant 5–30 min cost; ≤3 refinements; re-sends full IR |
| `code_generation_node` | `trigger_workflow.py:733-935` (wait_for `:833-838`) | 30-min stage cap |
| `execution_node` / `ExecutionService.execute_tests` | `trigger_workflow.py:938-1070`; `execution_service.py:24-92` | execution orchestration |
| `PlaywrightRunner._execute_command` / `_build_command` | `playwright_runner.py:76-110,139-179` | blocking subprocess + `shell=True` injection surface |
| `EnvironmentManager._install_dependencies` / `_install_browsers` | `environment_manager.py:132-173` | 300s/600s blocking npm/playwright installs |
| `PromptBuilder.build` | `prompt_builder.py:553` | system/user message assembly (credentials never injected) |
| `CredentialStore.save` / `load` | `prompt_builder.py:493-537` | at-rest encryption + plaintext fallback |
| `CodeValidator.validate_project` | `code_validator.py:35-67` | heuristic-only validation |
| `WorkflowEventBus.publish` / `subscribe` | `event_bus.py:243,303` | SSE delivery; drop-on-full |
| `configure_logging` | `logging/config.py:79` | JSON logging, no rotation |
| `create_app` / `lifespan` | `main.py:28-124` | middleware order, CORS, no shutdown hooks |
| health endpoints | `health.py:17-143` | shallow readiness |

# DELIVERABLE 11 — Priorities (P0–P3)

**P0 (block release / data integrity):**
1. Fix event-loop blocking: wrap all `subprocess.run` in `asyncio.to_thread`/`asyncio.create_subprocess_exec` (`playwright_runner.py:147`, `environment_manager.py:136,156`).
2. Enforce real auth + rate limiting; fix CORS wildcard+credentials (`main.py:100-113`, `middleware.py`).
3. Make the Docker image executable: install Node.js + `playwright install`/`install-deps`; gate healthcheck on execution readiness (`Dockerfile:2-46`).
4. Route the 3 LLM calls through `response_format={"type":"json_object"}` + `complete_structured` (already implemented, `openai_client.py:168-231`) to stop truncation-driven failures.

**P1:**
5. Close browser at shutdown/run-end; add crash watchdog (`main.py:73-74`, `browser_manager.py:329`).
6. Stop mutating shared singletons (construct per-run agents, `dependencies.py:94-107`).
7. Replace heuristic validator with `tsc --noEmit` + template lint (`code_validator.py`).
8. Fail closed on missing `CREDENTIAL_ENCRYPTION_KEY` / `cryptography`; drop plaintext fallback (`prompt_builder.py:476-512`).
9. Cap test-design stage with a node-level timeout (mirror `:833-838`); reconcile `OPENAI_TIMEOUT` (`.env.example:43` vs `settings.py:73`).

**P2:**
10. Add popup/download/dialog handlers + `storage_state` reuse (`browser_manager.py`).
11. Fix DOM extractor: null-safe dialog title (`dom_extractor.py:192`), fixed-position visibility (`:33`); add iframe/shadow-DOM/text extraction.
12. Implement log rotation (`logging/config.py:154-157`); add LLM latency/token metrics; wire readiness to node/browser/LLM checks.
13. Add real human-review gate + feedback→regeneration loop (remove hardcoded `auto_approve`, `trigger_workflow.py:672,1455` — from prior audit).
14. Remove dead `playwright_project_generator.py`; delete the stub crawler prompt or implement it.

**P3:**
15. CI/CD pipeline enforcing ruff/mypy/pytest; multi-worker-safe architecture (external event bus / browser-per-worker).
16. Crawl concurrency, LLM result caching, per-run browser isolation.

# DELIVERABLE 12 — Permanent recommendations

1. **Never block the event loop** — all subprocess/IO must be async or offloaded. This is the #1 fix and unlocks concurrency.
2. **One graph, one state** — continue the prior recommendation: unify the three LangGraph invocations so state/node_results are continuous (prior orchestration report §14.4).
3. **Structured LLM output everywhere** — JSON-schema `response_format` + `complete_structured`; raise/stream output to kill truncation.
4. **Browser lifecycle as a managed resource** — acquire/release per run; `storage_state` caching; crash recovery; explicit shutdown.
5. **Single source of truth for config** — reconcile `.env.example` with `settings.py` defaults; delete unused env knobs (`LOG_FILE_ROTATION`, `API_WORKERS`, `TELEMETRY_ENABLED`) or implement them.
6. **Real observability over scripted events** — emit telemetry from actual LLM calls; remove fabricated confidence/reasoning events.
7. **Ship a CI gate** — ruff, mypy, pytest as the definition of done; every fix above should land behind an enforced gate.

# DELIVERABLE 13 — Risk assessment

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Server-wide freeze during npm install / playwright install / test run (blocking subprocess) | High (every execution run) | High (all users, all runs) | P0-1 |
| LLM JSON truncation → stage failure (4096 cap, no structured output) | High | Med | P0-4 |
| Unauthenticated API abuse (LLM quota, disk, browser) | Med | High | P0-2 |
| Docker image unusable for crawl/execution | Certain (current image) | High | P0-3 |
| Browser crash kills all subsequent crawls (no recovery, no shutdown) | Med | Med | P1-5 |
| Credentials stored plaintext (cryptography missing / per-process key) | Low (depends on deps/config) | High | P1-8 |
| Concurrent runs corrupt SSE routing (shared singletons) | Med (under concurrency) | Med | P1-6 |
| Silent UI event loss under load (queue full drop) | Med | Low | P2 |
| Session/login flakiness (hardcoded sleeps, no storage_state) | Med | Med | P2-10 |

# DELIVERABLE 14 — Overall engineering maturity score

| Area | Score (0–10) | Basis |
|---|---|---|
| Architecture & separation | 7 | Clean layered layout (infrastructure/services/agents/core/persistence), DI container |
| Browser lifecycle | 3 | Managed but never torn down; shared; no popups/storage-state; TLS off |
| Inventory discovery | 6 | Rich form extraction; misses SPA/iframe/shadow content; 2 extractor bugs |
| Prompt engineering | 5 | Decent content; no schema/structured output; vestigial crawler prompt |
| Performance | 3 | Blocking event loop; 5–30 min LLM stages; no caching |
| Security | 3 | No auth; CORS wildcard; shell=True; TLS off; plaintext credential fallback |
| Playwright quality | 4 | Good locator strategy; hardcoded sleeps; no SPA waits/popups/session reuse |
| Code quality | 5 | Clean overall; dead generator; heuristic validator; singleton races; config drift |
| Observability | 6 | Strong structured logging/SSE; no rotation, shallow readiness, fabricated telemetry |
| Production readiness | 2 | Image can't execute; no CI; no auth; no graceful shutdown |
| **OVERALL MATURITY** | **4.4 / 10** | **Solid prototype/early-stage platform; not production-deployable until P0 items land.** |

---

*Method note: findings marked "(prior audit)" were verified in the earlier read-only sessions of this engagement (`ORCHESTRATION_LLM_REASONING_AUDIT_REPORT.md`, `CRAWLER_EXECUTION_AUDIT_REPORT.md`) and are referenced here for continuity; everything else was re-verified against source in this session.*

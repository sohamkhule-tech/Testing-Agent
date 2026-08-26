# MASTER CRAWLER & EXECUTION ARCHITECTURE AUDIT
## Why the Crawler Repeats Pages, Gets Stuck on "Loading", and Why the Live Preview Lies

**Scope:** Read-only forensic audit (AUDIT 1–11) of the crawler (`crawler_service.py`) and execution engine (`playwright_runner.py`), plus the event-stream pipeline (backend event bus → SSE → frontend Zustand store → live preview). No code was modified.

**Method:** Every conclusion cites `file:line`. Where the code does not prove a claim it is marked **Unable to verify from the current code**. The hash-fragment canonicalization defect was empirically verified by executing `_canonicalize_url` against a sample SPA URL (see §9, RC-3).

---

## 1. Executive Summary

The crawler is a **deterministic, URL-string-based breadth-first walker** — not an agent. It never calls the LLM, never reads the user's intent at runtime, and never waits for the page to actually render before extracting or screenshotting. Almost every observed symptom (repeated screenshots, stuck-on-loading, frozen UI, preview mismatch, ignoring instructions) traces to five concrete, provable defects:

| # | Defect | Evidence | Produces |
|---|---|---|---|
| D1 | **`BROWSER_FRAME` pipeline is dead code** — `_frame()` is defined at `crawler_service.py:581-598` but has **no caller** (grep-confirmed; only definition + enum constant exist). | `crawler_service.py:581`; `event_bus.py:166` | Frozen live preview; UI only updates once per page |
| D2 | **Readiness is DOMContentLoaded, not "rendered"** — `page.goto(wait_until="domcontentloaded")` (`crawler_service.py:606`) followed immediately by `PAGE_LOADED` emit (`:613`) and screenshot (`:756-789`). No `wait_for_load_state`, no stability check, no selector wait. | `crawler_service.py:606,609,613,756-779`; `dom_extractor.py:229` | Screenshots of loading spinners; "stuck on loading" |
| D3 | **`_discover_dynamic_links` grinds silently** — up to **30 button clicks per page** (`:952`), each `click(timeout=1500)` + `wait_for_timeout(300)` + possible `go_back(timeout=5000)` (`:962-975`), with **zero events emitted** during it. Worst case ≈ 200 s/page of silent work. | `crawler_service.py:940-982` | UI frozen while backend continues |
| D4 | **Screenshot dedup is broken** — the `SCREENSHOT_CAPTURED` emit at `crawler_service.py:776` is **outside** the `screenshot_path.exists()` / `_screenshot_page_ids` guards (`:762-774`), and the frontend appends every such event with **no dedup** (`workflow-store.ts:1123-1131`). The login screenshot (`crawler_service.py:1808-1816`, `login_result.png`) duplicates the post-login page screenshot. | `crawler_service.py:762-779`; `workflow-store.ts:1128` | Duplicate screenshots of the same page |
| D5 | **Hash-fragment canonicalization splits one SPA page into many URLs** — `_canonicalize_url` preserves `#/route` fragments (`crawler_service.py:1227-1228`), so `/dashboard` and `/dashboard#/projects` are different keys → same view visited + screenshotted repeatedly. | `crawler_service.py:1209-1230` (verified) | Revisiting completed pages; duplicate screenshots |

Secondary, compounding defects: user-configured scope is silently ignored (`crawler_agent.py:94-95` reads `max_crawl_depth`/`max_pages` from `execution_mode`, but those fields live in `scope` per `schemas/trigger.py:61-83`); the event bus **silently drops events** when a subscriber queue is full (`event_bus.py:262-269`); and there is **no global wall-clock deadline** for the crawl loop (`crawler_service.py:349`).

**The first architectural reason the crawler stops behaving like a human:** at `crawler_service.py:349` it dequeues the next URL and at `:606` declares the page "loaded" at DOMContentLoaded, then at `:756` photographs it — a human waits for content to render, reads what's on screen, and decides what matters; this crawler photographs the loading spinner, enqueues every same-domain href, and blind-clicks nav buttons. The "human" framing is the agent contract, but no LLM is ever invoked (`crawler_agent.py:177-184` defines a system prompt that is never used).

---

## 2. Crawler Architecture (as-built)

```
Frontend (React) ──POST /runs──▶ trigger.py:103 create_run
                                      │ prompt parsed (prompt_builder.PromptParser)
                                      ▼
                          trigger_workflow.py:183 crawler_node
                                      │ builds input_data {:211-250}
                                      │  scope_overrides (include/exclude)
                                      │  auth_context
                                      ▼
                          CrawlerAgent.execute (:44)  ── _execute_lock (:42,46)
                                      │ max_depth/max_pages read from execution_mode (:94-95) ← WRONG DTO
                                      ▼
                          CrawlerService.crawl (:138) ── _crawl_lock (:124,140)
                                      │ _reset_state (:152) → _crawl_impl (:143)
                                      ├─ BrowserManager.create_context (:172)  HAR record, timeout=request.timeout
                                      ├─ _perform_login (:181)  (context.new_page per attempt, :1302)
                                      ├─ seed URLs (:197-216)
                                      ▼
                        ┌─────────────────────────────┐
                        │  _crawl_bfs (:315)          │
                        │  while queue and visited<max│  ← NO global deadline (:349)
                        │    url,depth,parent,pid =   │
                        │      queue.pop(0) (:350)    │
                        │    if url in _visited_urls  │──skip→ _pages_skipped++
                        │    for attempt in retries   │  (:382)  wait_for 32s (:395)
                        │      _visit_page (:529)     │  ── retry backoff 0.25-1.0s (:431)
                        │    if fail → _capture_      │
                        │      timeout_artifacts      │  (:436, :829) re-goto + .timeout.png
                        │    links = _extract_links   │  (:476, :887)
                        │    links += _discover_      │  (:477, :940)  ≤30 clicks/page, silent
                        │    enqueue new (dedup)      │  (:482-503)
                        │    _extract_assets          │  (:504, :984)
                        │    emit PAGE_COMPLETED      │  (:522)
                        │    page.close()             │  (:527)
                        └─────────────────────────────┘
                                      ▼
                          _build_crawl_package (:1080) → crawl-package.json (:262)
```

Key property: **the entire crawl is one serialized, single-context, single-threaded loop.** `_crawl_lock` (`:124`) + agent `_execute_lock` (`:42`) guarantee it. There is no parallelism, no prioritization, and no early-exit path other than queue-empty or `visited_pages >= max_pages` (`:349`).

---

## 3. Page-State Machine (per `_visit_page`, `crawler_service.py:529-827`)

```
 new_page (:558) ──▶ PAGE_NAVIGATION_STARTED (:604)
                         │ BROWSER_ACTION "goto" (:605)
                         ▼
              page.goto(domcontentloaded, 30s) (:606)   ← bounded wait, but returns at DOMContentLoaded
                         │ BROWSER_ACTION "wait_for_load" (:609)   ← label emitted AFTER goto returns (lies)
                         │ DOM_CONTENT_LOADED (:610)
                         │ PAGE_LOADED (:613)           ← immediately, no real wait
                         ▼
              title (:626) → response.body (:633) → HTML_EXTRACTED (:636)
                         ▼
              extract_all(page.evaluate) (:642)         ← runs immediately; SPA may still be empty
                         ▼
              DOM records (forms/buttons/inputs/...) (:648-754)
                         ▼
              SCREENSHOT — full_page=True (:763) ──▶ SCREENSHOT_CAPTURED (:776)   ← only visible UI update
                         │                             (guard bug: emit outside dedup, §9 D4)
                         ▼
              build PageRecord (:790-802) → return (page_record, page)  (keep_page=True, :812)
```

Notes:
- `_frame()` (`:581-598`) — the intended per-action live frame — **is never called**. It would have emitted `BROWSER_FRAME` with a `frame_{page_id}_{ts}.png` screenshot. It exists in source, has zero call sites.
- `page.close()` is deferred to the BFS caller's `finally` (`:526-527`) so link discovery can reuse the same `page` object. Link/asset extraction and dynamic discovery therefore run on the **post-screenshot, possibly re-navigated** page.

---

## 4. Queue Diagram (dedup / revisit semantics)

```
                         enqueue path
 link_url → _canonicalize_url (:483)
   │ if not _should_crawl_url (:484)  → drop  (include/exclude regex, :1232-1252)
   ├─ _queued_urls.add (:501)  ← set, never cleared mid-crawl
   └─ queue.append (url, depth+1, parent, page_id) (:502)

 dequeue path (:349-350)
 url → if url in _visited_urls (:360)  → _pages_skipped++, continue  (never visits)
     → depth > max_depth (:366)        → skip + MAX_DEPTH_REACHED warning
     → _visit_page (:384)              → on success: _visited_urls.add(url) and .add(canonical(page.url)) (:469-470)
```

Weaknesses:
1. **`_visited_urls` and `_queued_urls` are keyed on the *canonicalized* URL** — so any canonicalization inconsistency (D5 hash-fragment) creates distinct keys for the same page.
2. **No "URL normalised without fragment" fallback**: `_extract_links` strips fragments (`:928`) but `_discover_dynamic_links` only splits on `#` for its own discovered URLs (`:969`), and the *recorded* page URL keeps the fragment (`:792`). Mixed-key dedup.
3. `queue.pop(0)` on a `list` (`:350`) is O(n) per pop — minor, but with 50+ pages and per-page link sets it is avoidable churn.
4. **No in-flight reservation that survives failure**: a timed-out URL is *not* re-queued — it is simply dropped after retries (`:433-455`). The crawl then proceeds; the "dead" page is never retried later, which is a coverage loss, not a loop.

---

## 5. Screenshot Lifecycle (what the user actually sees)

```
 per page  (:756-789)
   screenshot_path = screenshots/{page_id}.png        (:759)
   if not exists: full_page screenshot (:762-763)     ← full-page capture of tall SPAs is slow
   if page_id not in _screenshot_page_ids: record     (:764-774)
   emit SCREENSHOT_CAPTURED  ← ALWAYS, even when file existed / already recorded  (:776)  ★ D4

 login     (:1808-1816)
   screenshots/login_result.png  + emit SCREENSHOT_CAPTURED  ← same page as post-login {page_id}.png  ★ D4

 timeout   (:861-863)
   screenshots/{page_id}.timeout.png  + .timeout.html/json   ← NOT emitted as event, not shown live

 frontend  (workflow-store.ts:1123-1131)
   screenshots = [...screenshots, newShot]  ← unconditional append, no filename/page dedup  ★ D4
```

So the gallery can show, for one rendered page: `login_result.png` + `{page_id}.png` + one entry per URL-fragment variant (D5). There is no dedup anywhere in the chain.

---

## 6. Browser Lifecycle (`app/infrastructure/browser_manager.py`)

- `initialize()` launches a single Chromium instance headless (`:91-94`); `--disable-blink-features=AutomationControlled` (`:86`).
- `create_context()` creates one isolated context per crawl with `record_har` (`:166`, `har_path=crawl.har`); sets default timeout + navigation timeout = `request.timeout` (30 000 ms) (`:176-177`).
- `navigate()` — **never called by the crawler** (the crawler calls `page.goto` directly at `crawler_service.py:606`); this wrapper is effectively dead in the crawl path.
- `screenshot()` — `full_page=True` default (`:267`). Full-page screenshots on long SPAs can take many seconds, contributing to the long "capturing" window with no UI feedback.
- `cleanup()` (`:329-361`) — best-effort; closes contexts, browser, Playwright. Called by `CrawlerService.cleanup` (`:132-136`).

**Implication:** browser availability is never the constraint; the serial page-processing path is. There is no pooling, and only one context exists for the whole crawl, so login cookies persist across pages (correct) but any context-level failure aborts everything (`:244-246`).

---

## 7. Event Streaming Pipeline (why the UI freezes while the backend continues)

```
 CrawlerService  ──await emit(run_id, type, data)──▶  WorkflowEventBus.publish (event_bus.py:243-269)
                                                          │ replay buffer (cap 200, :237)
                                                          │ fan-out per subscriber queue (maxsize 512, :230)
                                                          │   if q.full(): DROP event, log warning (:262-269)  ★ no backpressure
                                                          ▼
 SSE endpoint  events.py:41-95  (subscribe with replay=True :82)
                                                          ▼
 EventSource in frontend  use-workflow-sse.ts (knownTypes incl. browser_frame :114)
                                                          ▼
 Zustand store dispatch  workflow-store.ts (seenEventIds dedup :950-957)
     └─ SCREENSHOT_CAPTURED → append (:1123-1131)
     └─ BROWSER_ACTION     → currentAction label+pos (:1143-1150)
     └─ BROWSER_FRAME      → liveFrame (:1152-1168)  ← never fires (D1)
                                                          ▼
 LiveBrowserPreview  browser-activity.tsx:227-465
     displayFrame = liveFrame ?? latestShot (:234)
     isLoading = status launching|navigating || currentAction (:236)
     <img src=/runs/{id}/screenshots/{filename}>  (events.py:102-148)
```

Freeze mechanics (AUDIT 10):
1. **`liveFrame` is never populated** (D1), so the preview shows either a spinner (`isLoading`, `browser-activity.tsx:355-359`) or the *previous* page's screenshot — for the entire (long) duration of the current page visit. This is the "browser preview not matching crawler activity" symptom.
2. **The crawler emits nothing during `_discover_dynamic_links`** (D3) — up to ~200 s of silent button-clicking while `browser.status` stays `'navigating'` (`workflow-store.ts:1163-1167` on last BROWSER_FRAME... which never comes) or whatever earlier event set it.
3. **Events are silently dropped** if the SSE subscriber queue is full (`event_bus.py:262-269`) — the backend never blocks on the UI, so it "continues" while the UI has already missed events. The crawler's inline `await emit(...)` (`crawler_service.py:604-636`) only awaits the (fast, non-blocking) fan-out, never the socket.
4. **PING every 15 s** (`:322-327`) keeps the socket alive; no data loss is reported to the UI.

---

## 8. Execution Engine (AUDIT 1) — `app/execution/playwright_runner.py`

- `run_tests()` shells out to `npx playwright test` via `subprocess.run(..., shell=True)` (`:147-157`) — blocking, in the async event loop.
- Command built in `_build_command` (`:76-110`): `--workers 1` when parallel disabled, `--reporter html,junit`, JSON via env `PLAYWRIGHT_JSON_OUTPUT_NAME` (`:125`).
- **Timeout math is broken**: `timeout = config.timeout_ms // 1000 + 300` (`:36`). If `config.timeout_ms` is 30 000 ms (30 s per `ExecutionConfigInput.timeout=300` *seconds*… see note), this yields `30 + 300 = 330 s`. `config.timeout_ms` is derived from `execution.timeout` (in *seconds*, `schemas/trigger.py:107-109`) somewhere upstream; the `//1000` implies ms. **Unable to verify the conversion without the execution workflow node**, but the `+300` hard floor means a run can never abort sooner than 300 s after timeout logic. Verify in the execution workflow node before trusting runtime estimates.
- Results parsed from `test-results/results.json` (`:181-220`); failed/timedOut/interrupted → `failed` (`:229-234`).
- **No per-test SSE events emitted** — the runner returns a dict; live UI execution progress must come from elsewhere (if it exists at all). **Unable to verify whether any execution node emits `test_started`/`test_passed` events**, because the execution workflow node was outside the primary trace.

---

## 9. Root-Cause Analysis (AUDIT 2–11)

### RC-1 · Repeated screenshots of the same page (D4, D5)
- **Emit-outside-guard**: `crawler_service.py:762` `if not screenshot_path.exists():` then `:764` `if page_id not in self._screenshot_page_ids:` — but the `SCREENSHOT_CAPTURED` emit at `:776` is at the same `try` level, **not inside either guard**. Any successful `_visit_page` re-entry for a page whose screenshot already exists re-emits the event.
- **Frontend blind append**: `workflow-store.ts:1123-1131` appends a new `Screenshot` per event; `id` is the *event id* (`:1125`), so dedup by event_id (`:950-957`) cannot dedup by page/filename.
- **Login duplication**: `login_result.png` emitted at `crawler_service.py:1810-1816` plus the seeded post-login page's `{page_id}.png` (`:759`) are two screenshots of the same dashboard.
- **Hash-fragment split** (D5, verified): `_canonicalize_url` (`:1209-1230`) keeps `#/...` fragments (only strips a leading `/` on the fragment text, `:1227`). Test run:
  ```
  canon('https://app.com/dashboard')            = https://app.com/dashboard
  canon('https://app.com/dashboard#/projects')  = https://app.com/dashboard#/projects
  equal? False   ← same SPA view, two crawl keys
  ```
  A SPA that writes `location.hash` while rendering yields distinct `_visited_urls`/`_queued_urls` entries and `{page_id}.png` per fragment → repeated screenshots of the same rendered page.

### RC-2 · Stuck on loading / screenshots of loading states (D2)
- `page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)` (`:606`). DOMContentLoaded is a *document* event that fires before async JS (data fetch, router render) completes. The code then immediately emits `PAGE_LOADED` (`:613`) and captures the screenshot (`:763`).
- `dom_extractor.extract_all` (`dom_extractor.py:221-230`) is a single `page.evaluate` with **no retry/wait** — a not-yet-rendered SPA yields empty/partial element lists, which then become the inventory.
- The `"wait_for_load"` label is emitted at `:609` **after** goto has already returned — so the UI shows "Waiting for page to load" while the backend is actually extracting/screenshotting. The label never corresponds to an actual wait.

### RC-3 · Indefinite / very long waits (AUDIT 9)
- Per-page bound is `asyncio.wait_for(..., timeout=(page_timeout_ms/1000)+2)` (`:395`) with `page_timeout_ms = request.timeout` (default 30 000, `schemas/crawler.py:357`) → **32 s hard cap per attempt**.
- On total failure, `_capture_timeout_artifacts` (`:829-885`) re-opens the page and calls `page.goto(timeout=timeout_ms)` again (`:856`) → another 30 s.
- `max_retries` default 2 (`schemas/crawler.py:358`) → worst case ≈ 3 × 32 s + 30 s ≈ **126 s per dead URL**.
- `_discover_dynamic_links` adds up to 30 × (click 1.5 s + wait 0.3 s + up to 5 s go_back) ≈ **~200 s per page** with no emitted progress (§7).
- **No global wall-clock deadline** anywhere in `_crawl_bfs` (`:349` loop condition is only queue + page count).

### RC-4 · Revisiting completed pages (D5 + discovery coupling)
- Fragment-keyed dedup (D5) causes genuine re-visits of the same rendered view.
- `_discover_dynamic_links` (`:940-982`) runs on **every** page visit and re-executes navigation (clicks + `go_back`) over nav controls even when those routes were already discovered/visited — wasted "navigation" that looks like revisiting.
- The `page` reused for discovery is the same object whose URL the click cycle mutates; `_extract_assets(page, page_record.url, ...)` (`:504`) runs against a possibly re-navigated page but tags assets with the *original* `page_record.url` — metadata mismatch. **Verified partially; the exact URL-at-asset-extraction time is not logged.**

### RC-5 · Ignoring completed navigation (AUDIT 3)
- There is **no memory of "navigation already performed"** — only URL-keyed dedup. A page that has been fully processed is re-opened via `new_page` for every queued URL including fragment variants (D5); nav buttons are re-clicked every visit (RC-4). Nothing records "we already exercised this nav control / this route's sidebar."

### RC-6 · Not following user instructions (AUDIT 6)
- **Scope DTO mismatch**: `crawler_agent.py:94-95` reads `max_crawl_depth`/`max_pages` from `execution_mode`, but `ExecutionModeInput` (`schemas/trigger.py:33-43`) has only `crawl_strategy`/`test_level`. The real fields are in `scope` (`ScopeInput.max_crawl_depth`, `max_pages`, `schemas/trigger.py:75-80`). Result: user-supplied `scope.max_pages`/`max_crawl_depth` are **silently ignored**; defaults 3/50 always apply.
- API layer hardcodes `scope={"max_pages": 50, "max_depth": 5}` (`trigger.py:129-132`) and `max_depth` is not even a `ScopeInput` field, so it is dropped by Pydantic anyway.
- `timeout`, `max_retries`, `browser`, `headless` are likewise read from `execution_mode` (`crawler_agent.py:117-121`) — all defaulted.
- include/exclude patterns *do* reach the crawler via `scope_overrides` (`trigger_workflow.py:211-225`) → `_include_patterns`/`_exclude_patterns` (`crawler_agent.py:136-137`) → `_should_crawl_url` (`:1232-1252`). These work, but the prior audit (`PROMPT_INTENT_AUDIT_REPORT.md`) showed the parser often produces the **wrong** include patterns (e.g. `"Crawl only Create RRF and ignore Reports"` → include `reports`).

### RC-7 · Live UI frozen while backend continues (D1, D3, event-drop)
- D1: no `BROWSER_FRAME` → `liveFrame` never set → preview shows stale `latestShot` (`browser-activity.tsx:234`).
- D3: no events during dynamic discovery → UI static for seconds-to-minutes.
- `event_bus.py:262-269`: full subscriber queue ⇒ event **dropped**, backend unaffected ⇒ backend "ahead" of UI.
- Screenshots are fetched by `<img>` (`browser-activity.tsx:161,172`) from `events.py:102-148`; a full-page screenshot served for a URL whose `{page_id}.png` never got written yields a broken/empty image.

### RC-8 · Browser preview not matching crawler activity (D1)
- The only images the preview can show are `SCREENSHOT_CAPTURED` filenames (`{page_id}.png`, `login_result.png`). Those fire **once per page at the very end** of page processing. During goto/extract/discovery the preview shows the previous page or a spinner — never the live state the crawler is actually in.

### RC-9 · Event ordering / lost progress (AUDIT 11)
- Crawler emits are `await`ed inline (`:604-636`, `:756-779`) so ordering is deterministic *on the publisher side*.
- But the subscriber queue is capped at 512 (`event_bus.py:230`) and replay at 200 (`:237`). A busy crawler (BROWSER_ACTION per step, per page ×50 pages) can overflow the queue → **intermediate events silently lost**; a late-joining tab sees only the last 200.
- `workflow-store.ts:950-957` caps `seenEventIds` at 2000 then clears — an old replay event re-sent after a reconnect could be re-applied. Minor.

---

## 10. Exact Files / Functions / Lines

| Area | File | Function / Symbol | Lines |
|---|---|---|---|
| BFS loop | `app/services/crawler_service.py` | `_crawl_bfs` | 315-527 |
|  | | loop condition (no deadline) | 349 |
|  | | dequeue + visited check | 350, 360-363 |
|  | | retry + wait_for (32 s) | 382-431 |
|  | | timeout artifact capture | 433-455, 829-885 |
| Page visit | `app/services/crawler_service.py` | `_visit_page` | 529-827 |
|  | | `_frame()` — **no caller** | 581-598 |
|  | | goto(domcontentloaded) | 606 |
|  | | false "wait_for_load" / PAGE_LOADED | 609-613 |
|  | | extract_all (no wait) | 638-645 |
|  | | screenshot + SCREENSHOT_CAPTURED emit-outside-guard | 756-789 |
| Links | `app/services/crawler_service.py` | `_extract_links` | 887-938 |
|  | | `_discover_dynamic_links` (30 clicks, silent) | 940-982 |
|  | | `_extract_assets` | 984-1052 |
| Canonical | `app/services/crawler_service.py` | `_canonicalize_url` (fragment bug) | 1209-1230 |
| Scope filter | `app/services/crawler_service.py` | `_should_crawl_url` | 1232-1252 |
| Login | `app/services/crawler_service.py` | `_perform_login` | 1254-1436 |
|  | | `_check_login_success` | 1656-1804 |
|  | | `_capture_login_screenshot` | 1806-1823 |
| Orchestration | `app/services/crawler_service.py` | `crawl` / `_crawl_impl` / `_build_crawl_package` / `_reset_state` | 138-141, 143-313, 1080-1167, 1169-1207 |
| Agent | `app/agents/crawler_agent.py` | `execute` (DTO mismatch) | 44-47, 94-121 |
|  | | system prompt — never invoked | 177-184 |
| Browser | `app/infrastructure/browser_manager.py` | `create_context` / `screenshot` / `navigate`(dead) | 105-191, 263-295, 219-261 |
| DOM | `app/services/dom_extractor.py` | `extract_all` | 221-230 |
| Event bus | `app/core/event_bus.py` | `publish` (drop on full) | 243-269 |
|  | | subscribe / ping | 303-336 |
| SSE | `app/api/routes/events.py` | stream / screenshot serve | 41-95, 102-148 |
| Workflow | `app/workflows/trigger_workflow.py` | `crawler_node` | 183-301 |
| API | `app/api/routes/trigger.py` | `create_run` (hardcoded scope) | 103-207 |
| Schemas | `app/schemas/trigger.py` | `ExecutionModeInput` vs `ScopeInput` | 33-43, 61-83 |
| Frontend | `frontend/src/store/workflow-store.ts` | dispatch screenshot/browser_frame/action | 1123-1131, 1152-1168, 1143-1150 |
| Frontend | `frontend/src/hooks/use-workflow-sse.ts` | knownTypes (browser_frame) | 106-123 |
| Frontend | `frontend/src/components/run-monitor/browser-activity.tsx` | LiveBrowserPreview | 227-465 |
| Execution | `app/execution/playwright_runner.py` | `run_tests` / `_build_command` / `_execute_command` | 18-74, 76-110, 139-179 |

---

## 11. Missing Components

1. **Real browser-frame capture** — `_frame()` is implemented but un-wired. No caller, so the entire "live browser preview" feature is non-functional.
2. **Rendered-content readiness check** — no `wait_for_load_state("networkidle")` (deliberately avoided, `:611-612`), no `wait_for_selector`, no "content present" stability gate, no `page.wait_for_function` for SPA render.
3. **Screenshot dedup / event dedup** — neither backend (`:764-774`) nor frontend (`workflow-store.ts:1128`) dedups by page/URL.
4. **Fragment-safe canonicalization** — `_canonicalize_url` must strip or normalize `#` fragments.
5. **Scope plumbing** — `crawler_agent` never reads `scope.max_pages`/`max_crawl_depth`/`timeout`; no test proves the values from the request reach the crawl.
6. **Global crawl deadline / progress heartbeats** — no wall-clock cap; no events emitted during discovery.
7. **Queue backpressure that surfaces drops** — `publish` drops silently; UI has no way to know it missed events.
8. **Execution-node SSE events** — `playwright_runner` emits none; live execution progress UI (if any) cannot be driven by it.
9. **Per-URL "navigation already performed" memory** — nothing prevents re-clicking nav controls already exercised.
10. **`BrowserManager.navigate()` dead code** — the wrapper exists but the crawler bypasses it, so any logic added there (retries, waits) silently never runs.

---

## 12. Priorities

### P0 — Correctness / data quality
- **P0-1** Wire `_frame()` into `_visit_page` (emit `BROWSER_FRAME` after real actions) — restores the live preview contract and the only truthful live-state channel. `crawler_service.py:581-598`, call from `:606-636`.
- **P0-2** Fix `_canonicalize_url` to normalize/drop `#fragment` (`:1227-1228`) — kills duplicate-page visits + duplicate screenshots at the root.
- **P0-3** Move the `SCREENSHOT_CAPTURED` emit inside the dedup guards (`:764-779`) and dedup frontend appends by `filename` (`workflow-store.ts:1128`).
- **P0-4** Fix `crawler_agent.py:94-121` to read scope from `scope` (`ScopeInput`), not `execution_mode`; add a test asserting request values reach `CrawlRequest`.

### P1 — Perceived stuckness / UX
- **P1-1** Add a real rendered-content wait before extract/screenshot (e.g. `wait_for_load_state("networkidle")` with fallback, or `wait_for_selector` for a body/root node with content) — eliminates "loading spinner" screenshots and the lying `wait_for_load` label (`:609-613`).
- **P1-2** Emit progress during `_discover_dynamic_links` (`BROWSER_ACTION` per click batch) and cap clicks by URL, not fixed 30 (`:952`).
- **P1-3** Never await screenshot files in the hot path for UI freshness; stream frames as `BROWSER_FRAME` (P0-1) and let `<img>` cache.
- **P1-4** Surface queue-full drops: log client-side or emit `SSE_RECONNECT`/missed-event count (`event_bus.py:262-269`).

### P2 — Robustness
- **P2-1** Add a global crawl wall-clock budget to `_crawl_bfs` (`:349`) so a pathological site cannot run unbounded.
- **P2-2** Raise `_QUEUE_MAX_SIZE`/replay or make publish non-lossy with TTL coalescing (`event_bus.py:230-237`).
- **P2-3** Replace `queue.pop(0)` with `collections.deque` (`:350`).
- **P2-4** Use `BrowserManager.navigate()` or delete it; ensure one code path owns navigation (`browser_manager.py:219-261`).
- **P2-5** Fix `playwright_runner` timeout math (`:36`) and verify the ms/s conversion in the execution workflow node.

### P3 — Scope / polish
- **P3-1** Per-route nav-memory to avoid re-clicking completed nav controls (`_discover_dynamic_links`).
- **P3-2** Emit `test_started`/`test_passed`/`test_failed` from the execution node (runner is event-less today).
- **P3-3** Reconsider full-page screenshots (`full_page=True`, `browser_manager.py:267`) — viewport captures are cheaper and less likely to hang on tall pages.

---

## 13. Permanent Recommendations

1. **Treat the crawler as a perception→decision→action loop, not a URL walker.** Minimal viable change: before screenshot/extract, wait for rendered content (`wait_for_function` or repeated `extract_all` until stable); after extract, let an LLM/nudged heuristic rank discovered links by the user's stated focus instead of blind enqueue.
2. **Make the live preview a first-class contract.** Emit `BROWSER_FRAME` from real action points; frontend should render `liveFrame` only from these and treat `SCREENSHOT_CAPTURED` as gallery entries, never as live state.
3. **Single source of truth for dedup.** Canonicalization must be fragment-safe and applied uniformly (queue key, record URL, `_queued_urls`, `_visited_urls`, `_page_ids_by_url`).
4. **Never block the UI stream on crawl work.** The event bus must either be lossless (unbounded/coalescing queue) or the crawler must bound its emit rate so subscribers never fall behind.
5. **Fix scope plumbing and enforce it with a test** — the `execution_mode` vs `scope` mismatch is a class of bug (silent default fallback) that will recur.
6. **Bound everything with time.** Global deadline + per-action budgets + progress events; the current code has only per-goto bounds.

---

## 14. The FIRST Architectural Reason the Crawler Stops Behaving Like a Human

At `crawler_service.py:606` the crawler calls:

```python
response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
```

and at `:613` immediately declares the page loaded:

```python
await emit(eid, EventType.PAGE_LOADED, {...})
```

then at `:763` photographs it (`full_page=True`) and at `:642` extracts elements — **all before the SPA has rendered anything meaningful**. A human waits for the content, reads the screen, decides what's relevant to the user's request, and acts. This crawler, in its first page decision, photographs the loading spinner, records an empty/partial DOM as the "inventory," and then blindly enqueues every same-domain href (`:476-503`) and blind-clicks up to 30 nav buttons (`:952`) with no goal, no priority, and no rendered-content check. The `"Waiting for page to load"` label it emits (`:609`) is emitted *after* goto has already returned — the UI is told the page is loading at the exact moment the crawler has decided it's done. That single premature-readiness decision (DOMContentLoaded ⇒ "loaded"), repeated on every page, is the first and deepest divergence from human-like behavior; everything else (duplicate screenshots, frozen preview, ignored scope) is a downstream consequence of decisions made against a page that was never actually read.

---

*Report generated during a read-only forensic audit. Findings cite `file:line`; items that could not be proven are marked accordingly. No code was modified.*

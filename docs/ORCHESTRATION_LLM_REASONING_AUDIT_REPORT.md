# Orchestration, LLM Pipeline, Memory & Reasoning Audit

**Read-only audit · FINAL (14 sections) · Date: 2026-08-07**
**Repo:** `project-foundation/` — single project, OneDrive path with spaces.
**Method:** Static code analysis only. Every claim cites `file`, `function`, `line`. Where the code does not prove something, the report says *Unable to verify from the current code.*

Related prior reports (not re-audited here): prompt-intent audit, `CRAWLER_EXECUTION_AUDIT_REPORT.md`.

---

## 1. Workflow Orchestration — what actually runs

The system is **not one continuous graph**. It is **three separate LangGraph `StateGraph`s**, strung together by the HTTP API layer.

| Graph | Function | Nodes | Used by |
|---|---|---|---|
| Pre-review | `create_platform_workflow` `trigger_workflow.py:1174-1187` | START → trigger → crawler → inventory_aggregator → test_design → END | `execute_platform_workflow` `:1362-1409` |
| Post-review | `create_post_review_workflow` `:1190-1251` | START → human_review → code_generation → (conditional) → execution → END | `continue_platform_workflow` `:1412-1517` |
| Unified (resume) | `create_unified_workflow` `:1254-1297` | all 7 nodes wrapped in `_with_checkpoint` | `execute_resume_workflow` `:1300-1359` |

```
POST /runs                        trigger.py:103 create_run
  └─ background task               trigger.py:193 _run_pre_review_workflow
       └─ execute_platform_workflow (graph #1)  trigger_workflow.py:1362
            trigger → crawler → inventory_aggregator → test_design → END
            → status = PAUSED "awaiting_review"    trigger.py:51
POST /runs/{id}/approve           trigger.py:460 approve_run
  └─ background task               trigger.py:484 _run_post_review_workflow
       └─ continue_platform_workflow (graph #2)  trigger_workflow.py:1412
            human_review → code_generation →(cond)→ execution → END
POST /runs/{id}/resume            trigger.py:987 resume_run
  └─ background task               trigger.py:1046 _run_resume_workflow_bg
       └─ execute_resume_workflow (graph #3)     trigger_workflow.py:1300
            all 7 nodes with checkpoint skip  _with_checkpoint :1154-1171
```

**Key facts:**
- Graph #1 ends at `test_design`; the API then flips the run to `PAUSED` (`trigger.py:51`) and waits for a human `POST /approve`.
- Graph #2 is a **fresh** `PlatformWorkflowState` built from the DB, not from graph #1's returned state (`trigger_workflow.py:1443-1462`). Continuity across the two invocations is via **filesystem artifacts** (`contracts/test-plan.json`, `contracts/approved-test-plan.json`), not in-memory graph state.
- Only graph #3 uses LangGraph checkpoints — and those are **hand-rolled** file checkpoints (`_load_checkpoint`/`_save_checkpoint`/`_is_stage_completed` `:1076-1151`), not LangGraph's `MemorySaver`/`SqliteSaver`. LangGraph's own checkpointing is unused.
- Nodes mutate the single Pydantic `state` instance in place and return it. `GraphState.model_config = {"frozen": False, "validate_assignment": True}` `graph/state.py:79`.
- Node-level failure handling: each node catches `Exception`, calls `state.mark_failed()`, records a `NodeResult(status="failed")`, and **returns the state** so LangGraph still advances the graph; the graph only stops via the conditional edge after `code_generation` (`route_after_code_generation` `:1276-1283`).

---

## 2. Shared state evolution (field-by-field)

`PlatformWorkflowState` fields: `trigger_workflow.py:26-106`. Base lifecycle: `graph/state.py:57-107`.

| Node | State writes | Source |
|---|---|---|
| `trigger_node` | `run_id`, `workspace_path`, `trigger_output` | `trigger_workflow.py:143-145` |
| `crawler_node` | `crawler_output`, `crawl_status`, `pages_visited`, `total_links` | (prior crawl audit; `:183-301`) |
| `inventory_aggregator_node` | `inventory_path`, `inventory_summary` | `:343, 346-355` |
| `test_design_node` | `test_plan_path`, `test_plan_md_path`, `test_plan_summary` | `:590-596` |
| `human_review_node` | `review_*`, `approved_test_plan_*`, `approved_scenarios`, `rejected_scenarios`, `total_scenarios` | `:683-692` |
| `code_generation_node` | `generated_project_path`, `generated_tests_path`, `code_generation_metadata_path`, `page_objects_count`, `test_files_count`, `scenarios_implemented`, `code_generation_status`, `code_generation_duration`, `validation_*` | `:864-874` |
| `execution_node` | `execution_*`, `tests_total/passed/failed/skipped/flaky`, `pass_rate`, `metrics`, `reports`, `failure_summary`, `retry_summary`, `artifacts`, `environment_report` | `:1002-1030` |

- Every node appends to `completed_nodes` and stores into `node_results` via `mark_node_completed` (`graph/state.py:86-95`); failures append to `errors` (`:94-95`).
- **Gap:** the post-review graph (#2) rebuilds state fresh, so `completed_nodes`/`node_results` from graph #1 are gone. The execution fail-fast check (`execution_node` `:957-964`) works only because it runs *inside* graph #2 after `code_generation_node` set the result.
- **Gap:** `auth_context` is declared on state (`trigger_workflow.py:39`) but is never populated by any node — credentials never reach the workflow state (they are persisted encrypted to disk at `trigger.py:155-157` and used by the crawler independently).

---

## 3. LLM pipeline — every single call site

There are exactly **3 `llm_client.complete(...)` call sites** in the entire `app/` tree. `complete_structured` and `stream_complete` are defined (`llm/openai_client.py:168,233`) but **never called anywhere**.

| # | Call site | Purpose | Temp | Max tokens | Wrapper | System prompt |
|---|---|---|---|---|---|---|
| 1 | `test_design_agent.py:407` | Generate test plan JSON from inventory | 0.7 | `default_max_tokens`=4096 (`settings.py:72`) | none beyond `@with_retry` on `complete` (`openai_client.py:50`) | Yes — from `PromptBuilder.build()` `test_design_agent.py:210-211` |
| 2 | `ir_generation_agent.py:221` | Generate IR JSON from approved plan | 0.3 | 4096 | `asyncio.wait_for(..., openai_timeout+60 = 960s)` `:212,220-227` | **None** (only `prompt=` passed) |
| 3 | `ir_generation_agent.py:772` | Refine IR after validation (loop, ≤3) | 0.2 | 4096 | `asyncio.wait_for(..., 960s)` `:769-778` | **None** |

Supporting facts:
- `complete()` builds a 2-message chat (`openai_client.py:79-82`), calls `chat.completions.create` with a hard `asyncio.wait_for` on the SDK call (`:108-117`), and classifies errors into `LLMRateLimitError`/`LLMTokenLimitError`/`LLMTimeoutError`/`LLMProviderError` (`:157-166`).
- `complete()` retry: `@with_retry(max_attempts=3, initial_wait=1.0, exceptions=(LLMRateLimitError, LLMTimeoutError, ConnectionError, TimeoutError, asyncio.TimeoutError))` — `openai_client.py:50`. Note the inner retry is bounded by the outer `wait_for` at the call sites (2 and 3), so worst-case per call ≈ 960s.
- `PromptAnalyzer` (`prompt_analyzer.py:219`) and `PromptParser` (`prompt_builder.py`) are **explicitly LLM-free**: "No LLM calls are required — all analysis is deterministic" (`prompt_analyzer.py:11-13`).
- `ExecutionAgent`, `FailureAnalyzer`, `HumanReviewService`, `TemplateEngine`, `IRValidator`, `IRPreValidator`/`IRAutoRepairer` — all deterministic, no LLM.

**Therefore the "AI" surface of the entire product is: 3 raw completions** (test-plan JSON, IR JSON, IR-refinement JSON), each parsed with regex JSON-extraction and (for IR) schema pre-validation + auto-repair.

---

## 4. Test Design Agent — decision logic

`TestDesignAgent._generate_test_plan` `test_design_agent.py:170-544`:

- Input: full `Inventory.model_dump(mode="json")` condensed into `inventory_summary`, `pages_summary`, `forms_summary`, `api_summary`, plus JSON dumps of navigation edges, user flows, inputs, buttons, tables, dialogs (`:216-284`).
- The **entire decision logic is delegated to the LLM** via prompt instructions (`:395-403`):
  - "For EVERY page or module… a MINIMUM of 8 scenarios. For authentication / login pages at least 15."
  - "For EVERY form… at least: 1 happy-path, 1 empty-submit, 1 invalid-data, 1 boundary-value, 1 SQL-injection / XSS."
  - "DO NOT stop early. Generate ALL scenarios."
- There is **no deterministic planner** for scenario count, priority, or coverage; those are prompt promises the LLM may or may not honour.
- Post-processing is deterministic: `renumber_scenario_ids` (`:432-438`), Pydantic `TestPlan` construction (`:507-542`), coverage summary recomputed from parsed JSON (`:478-495`). `estimated_duration_minutes = total_scenarios * 5` (`:494`).
- **Reliability risk:** an "exhaustive" plan is demanded inside a 4096-token output cap → truncated JSON is common → `_extract_json` regex repair (`:66-92`) may still fail → `AgentExecutionError` → node failure. There is **no retry of this call** beyond the transport-level `with_retry`, and no structured-output mode is used even though `response_format={"type":"json_object"}` exists (`openai_client.py:209`, unused).
- **Telemetry bug:** `test_design_node` emits `LLM_CALL_COMPLETED` with `response_tokens = result.get("scenario_count", 0)` (`trigger_workflow.py:485-488`) — scenario count is reported as a *token* count.

---

## 5. Code Generation Agent — why 5–30 minutes

`code_generation_node` `trigger_workflow.py:733-935` caps the whole stage with `asyncio.wait_for(code_gen_agent.execute(...), timeout=1800s)` (`:833-838`, env `CODE_GENERATION_TIMEOUT_SECONDS`). Inside `CodeGenerationAgent.execute` (`code_generation_agent.py:82-472`):

1. **LLM phase — the dominant cost.** `IRGenerationAgent.execute` (`ir_generation_agent.py:58-126`) does:
   - Initial IR completion: up to **960s** (900s SDK timeout + 60s buffer, `:212`).
   - `_validate_and_refine_ir` (`:670-720`): `while refinement_attempts <= self.max_refinement_attempts` (`:689`) → up to **3 more completions, each up to 960s** (`:771-778`). The refinement prompt re-embeds the **entire IR** (`ir.model_dump(mode="json")`, `:738-740`).
   - So worst case **4 LLM round trips ≈ 64 min** before the 1800s node cap fires. The node cap (`:838`) is the real ceiling and will produce a `CODE_GENERATION_FAILED`/`TimeoutError` (`:840-849`) on long generations.
2. **Deterministic phase (fast):** `TemplateEngine.generate_project` in a thread pool (`code_generation_agent.py:329-338`), then `CodeFormatter.format_directory` (`:367`).
3. **Verdict on 5–30 min:** it is sequential LLM latency — large prompts (full approved plan, full IR), a 900s timeout budget per call, up to 3 transport retries, and a ≤3-iteration refinement loop. Not CPU-bound codegen.

**Concurrency hazard (state corruption):** `get_code_generation_agent()` is an `lru_cache` **singleton** (`dependencies.py:104-107`). Each `execute` mutates shared instance fields: `self.ir_agent.run_id = run_id_str` (`code_generation_agent.py:267`) and `self.template_engine._run_id = run_id_str` (`:329`). Two concurrent runs **overwrite each other's run_id** → SSE events for run A are routed to run B. Same class of bug: the `IRGenerationAgent.run_id` field (`ir_generation_agent.py:50`) is set once per call on the shared agent.

---

## 6. Execution graph

`execution_node` `trigger_workflow.py:938-1070`:
- Fail-fast guards: `"code_generation" in state.completed_nodes` and `node_results["code_generation"].status == "completed"` (`:957-964`).
- Calls `ExecutionService.execute_tests` (`execution_service.py:24-92`) → `ExecutionAgent.execute` (`execution_agent.py:35-80`) which is a **deterministic sub-orchestrator**:
  `EnvironmentManager.setup_environment` (incl. `npm install`) → `PlaywrightRunner.run_tests` → `FailureAnalyzer.analyze_failure` (regex classification, `failure_analyzer.py:62-80`) → `RetryManager` (when `config.retries > 0`, `execution_agent.py:66-74`) → `ArtifactCollector` → `MetricsGenerator` → `ReportGenerator`.
- No LLM, no agentic decisions. Retries are configured retry-count based, not evidence-based.
- The only conditional routing in any graph is `route_after_code_generation` (`:1276-1283`): execution runs only if `state.errors` is empty and codegen result is `completed`.

---

## 7. Memory

**There is no memory subsystem.**
- `memory_manager_enabled`, `knowledge_model_enabled`, `learning_enabled`, `knowledge_reuse_enabled` exist only as **feature flags defaulting to `False`** in `app/agent/config.py:71-103`; a repo-wide grep shows they are **never referenced anywhere else**.
- `app/agent/` contains only `config.py`, `__init__.py`, and an empty `artifacts/__init__.py` — **no implementation**.
- The only persistence is: `RunEntity` in a file-based repo (`run_repository.py:24`), per-run filesystem artifacts, `checkpoint.json` (`trigger_workflow.py:1076-1132`), and an SSE replay buffer capped at 200 (`event_bus` prior audit).
- No vector store, no conversation history, no RAG. Nothing is learned across runs.

---

## 8. Tool selection & capabilities

**There is no tool registry and no dynamic tool selection.**
- `capability_registry_enabled`, `tool_selection_enabled` (`agent/config.py:49-56`) are flags only — never read.
- `IAgent` (`core/interfaces.py`) has no tool surface; agents do not expose callable tools to an LLM, and no `function calling`/`tools=` parameter is passed to any completion.
- The "tool mapping" is **hardcoded in graph construction**: each node name → exactly one deterministic service (crawler→`CrawlerService`, inventory→`InventoryAggregatorService`, test design→`TestDesignAgent`, codegen→`CodeGenerationAgent`, execution→`ExecutionService`). See `trigger_workflow.py:1174-1297` and `dependencies.py`.
- `IRGenerationAgent` sub-orchestrates internal components (`PromptComposer`, `IRValidator`, `DependencyGraphBuilder`, `IRPreValidator`, `IRAutoRepairer` — `ir_generation_agent.py:52-56`) but these are fixed collaborators, not discovered tools.

---

## 9. Reasoning

- The only "reasoning" is **single-shot in-context generation** on a non-reasoning model (default `gpt-4`, `settings.py:70`). No chain-of-thought, no ReAct loop, no reflection, no tool-feedback loop.
- The **live "AI reasoning" UI is scripted narration**, not an actual reasoning trace:
  - `test_design_node` emits hardcoded `AI_REASONING_STEP` sequences (`trigger_workflow.py:418-462, 490-495, 528-555, 559-564`) with fixed labels ("Reading Inventory", "Analyzing Application Structure", "Generating Test Scenarios", "Assigning Priority & Risk").
  - `PromptAnalyzer.reasoning_steps` are hardcoded strings (`prompt_analyzer.py:259-298`).
  - `CONFIDENCE_UPDATE` values are hardcoded (e.g. `inventory_confidence=96` `trigger_workflow.py:446`, `scenario_confidence=94`, `automation_coverage`, `risk_coverage=88` `:582-584`).
- `reflection_enabled` (`agent/config.py:79-82`) is a flag only — the only self-correction in the system is the narrow IR pre-validation/auto-repair loop (`ir_generation_agent.py:316-415`) and the LLM refinement loop (`:670-720`).

---

## 10. Human review traceability

- `human_review_node` builds `ReviewRequest(auto_approve=True, general_comments="Auto-approved by system")` — **hardcoded** `trigger_workflow.py:668-674`. `continue_platform_workflow` does the same (`auto_approve=True`, `:1453-1457`).
- `HumanReviewService._determine_review_outcome` short-circuits: `if auto_approve: return APPROVED, APPROVE` (`human_review_service.py:266-267`).
- **Traceable artifacts do exist:** `contracts/approved-test-plan.json`, `approved-test-plan.md`, `review-metadata.json` (`human_review_service.py:178-180, 290-311, 383-401`) record reviewer_name (`requested_by or "system"`), timestamps, counts.
- **But there is no real human gate:** `POST /runs/{id}/approve` (`trigger.py:460`) merely launches the auto-approving post-review graph; `POST /runs/{id}/reject` (`:511`) marks the run failed with feedback but has **no mechanism to feed feedback back into regeneration** (response text even admits "You may re-run with the feedback", `:537` — no such loop exists).
- Verdict: the "Human Review" stage is **simulated approval with durable records**, not human-in-the-loop decisioning.

---

## 11. Token analysis

| Phase | Prompt input size | Output cap | Notes |
|---|---|---|---|
| Prompt analyze | n/a (no LLM) | n/a | deterministic, ~10ms (`prompt_analyzer.py:11`) |
| Test design | full inventory JSON (pages/forms/APIs/nav edges/flows/inputs/buttons/tables/dialogs) + JSON schema (`test_design_agent.py:216-403`) | 4096 | "generate ALL scenarios, ≥8/page" inside 4096 tokens → **truncation likely** |
| IR generation | full approved plan via `ContextBuilder`/`ScenarioBuilder` (`prompt_composer.py:47-85`) | 4096 | **no system prompt** |
| IR refinement (×≤3) | **full IR JSON** + issues list (`ir_generation_agent.py:738-741`) | 4096 | largest prompt; repeated per iteration |

- Token accounting is **word-count estimates**: `len(prompt.split())` (`ir_generation_agent.py:150,230`) — not real tokenization.
- No context compaction/truncation strategy exists in `openai_client.complete`; a large inventory can exceed context or squeeze output.
- No cost tracking (`cost_optimization_enabled` flag only, `agent/config.py:101-104`).

---

## 12. State corruption & consistency findings

1. **Shared-singleton mutation → cross-run event leakage.** `get_code_generation_agent()`/`get_test_design_agent()` are `lru_cache` singletons (`dependencies.py:95-107`); `code_generation_agent.py:267` and `:329` write per-run IDs onto the shared instance. Concurrent runs corrupt `run_id` used for SSE emission. (See §5.)
2. **Three disconnected state spaces.** Graphs #1/#2/#3 each build independent `PlatformWorkflowState`; only the filesystem/DB bridge them (`trigger_workflow.py:1328-1336, 1443-1462`). `completed_nodes`/`node_results` are not preserved across invocations.
3. **Checkpoint skip relies on artifact existence** (`_is_stage_completed` `:1135-1151`). A truncated/partial artifact (e.g. a failed `test-plan.json`) is treated as "completed" and skipped, silently propagating bad data downstream.
4. **`_mark_stage_failed` inconsistency:** `code_generation_node` deliberately does NOT call `_mark_stage_failed` (`trigger_workflow.py:923` comment) because the `_with_checkpoint` wrapper does it (`:1165-1168`) — but in graphs #1/#2 (no wrapper) a codegen failure leaves `checkpoint.json` without a `failed_stage`/`last_error` entry, unlike every other node.
5. **Misleading telemetry:** `LLM_CALL_COMPLETED.response_tokens` is actually `scenario_count` (`trigger_workflow.py:487`); hardcoded confidence values (§9).
6. **`state.run_id` reassignment:** `trigger_node` overwrites `state.run_id` with the agent's result (`:143`); in the skip-run path it is the same value, but any drift would break event routing keyed on the original run id.
7. **Dead/hardcoded metadata:** IR `metadata.model_used` is hardcoded to `"deepseek-v4-flash-free"` (`ir_generation_agent.py:620`) regardless of the configured model.

---

## 13. Capability scoring (0–10)

| Capability | Score | Evidence |
|---|---|---|
| Autonomous goal decomposition | **0** | No planner; linear stage sequence. `execution_planner_enabled`/`task_hierarchy_enabled` flags only (`agent/config.py:41-48`). |
| Dynamic tool selection | **0** | No capability registry, no function calling; hardcoded node→service map. |
| Memory | **0** | No memory manager, no cross-run learning (flags only, `agent/config.py:71-103`). |
| Reasoning | **2** | Single-shot non-reasoning LLM; scripted "AI reasoning" UI events (§9). |
| Reflection / self-correction | **2** | Only narrow IR pre-validation + auto-repair + ≤3 LLM refinement iterations (`ir_generation_agent.py:316-720`). `reflection_enabled` unused. |
| Human-in-the-loop | **3** | Review stage + approve/reject/resume endpoints exist, but review is hardcoded auto-approve (§10). |
| State management | **5** | LangGraph state + hand-rolled checkpointing + resume works, but 3 disconnected graphs and singleton races. |
| LLM reliability | **3** | Retries, hard timeouts, JSON repair; but no structured output, truncation-prone 4096-token caps, no context management. |
| Learning | **0** | No cross-run learning (`learning_enabled`/`knowledge_reuse_enabled` flags only). |
| Error recovery | **4** | `RetryManager`, resume-from-checkpoint, deterministic `FailureAnalyzer`; no evidence-based auto-fix of generated code. |
| Observability | **5** | Rich SSE event stream, per-stage logs, checkpoint, but includes fabricated/scripted events (§9, §12.5). |
| **Overall autonomous-agent score** | **≈2/10** | A deterministic orchestrator with 3 LLM call sites, not an autonomous agent. |

---

## 14. Verdict & architectural gaps

**Verdict: this is a sequential, deterministic workflow (a "pipeline with LLM features"), NOT an autonomous AI agent.** The roadmap to become one already exists as a flag catalog in `app/agent/config.py` — but every flag defaults to `False` and none are referenced by any code, so the entire agentic layer is unimplemented.

**Top architectural gaps (prioritised):**

1. **P0 – Structured LLM output.** Route all 3 completions through `response_format={"type":"json_object"}` + `complete_structured` (already implemented but unused, `openai_client.py:168-231`) and raise output caps / enable context compaction to stop truncation-driven failures.
2. **P0 – Real human review gate.** Remove hardcoded `auto_approve=True` (`trigger_workflow.py:672, 1455`); persist genuine reviewer decisions; implement a feedback→regeneration loop (reject currently dead-ends, `trigger.py:511-537`).
3. **P0 – Concurrency isolation.** Stop mutating shared singletons (`code_generation_agent.py:267,329`); construct agents per run or thread run_id through call args.
4. **P0 – Single continuous graph.** Unify graphs #1/#2 via `create_unified_workflow` (`:1254`) for the normal path (not just resume), so state/node_results are continuous.
5. **P1 – Intent engine + clarification loop.** Implement `intent_engine_enabled`/`clarification_loop_enabled` (`agent/config.py:33-40`) — replace regex `PromptParser` with an LLM intent parser gated behind the existing flags.
6. **P1 – Execution planner.** Implement `execution_planner_enabled`/`task_hierarchy_enabled` (`:41-48`) as a dynamic DAG that replaces the hardcoded stage list.
7. **P2 – Capability registry + tool selection.** Implement `capability_registry_enabled`/`tool_selection_enabled` (`:49-56`) so stages/tools are chosen from discovered capabilities.
8. **P2 – Memory manager.** Implement `memory_manager_enabled` (`:75-78`) — the minimal first step is persistence of run knowledge for retrieval in later runs.
9. **P2 – Reflection gates.** Implement `reflection_enabled` (`:79-82`) — evidence-based post-stage checks instead of hardcoded confidence values.
10. **P3 – Learning, knowledge reuse, cost optimisation.** Implement `learning_enabled`/`knowledge_reuse_enabled`/`cost_optimization_enabled` (`:93-104`).

**Ground rule for the next phase:** any new "agentic" behaviour should land behind the flags that already exist in `agent/config.py`, so the product can graduate from *workflow* → *autonomous agent* without rewrites, and so that "AI reasoning" UI events become genuine traces of actual LLM calls rather than scripted narration.

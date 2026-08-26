# Phase 1: Agent State & Intent Preservation — Implementation Summary

## Goal

Make the platform **provably intent-preserving** end-to-end: the user's original
prompt, the parsed intent, the execution plan, the app inventory, and the agent
context must be threaded through the workflow, captured in a canonical
`AgentState`, and surfaced to every downstream stage (planning, code
generation, reporting). This enables post-run reconstruction, richer
`RunResponse` payloads, and future resume/continuation.

## Files Created

| File | Purpose |
| --- | --- |
| `app/context/agent_state.py` | `AgentState` model — canonical intent-preservation state (original prompt, parsed intent, execution goal, scope, plan/inventory/test-plan refs, credentials). CamelCase aliases (`originalUserPrompt`) for wire compatibility. `to_serializable()` / `from_serializable()` round-trip, `redacted()` deep-copy for safe logging. |
| `app/context/execution_planner.py` | `ExecutionPlan` model + `ExecutionPlanner` — ordered stage plan (intent → scope → crawl → design → review → codegen → execute → report) with `to_serializable()`. |
| `app/context/intent_parser.py` | `HybridIntentParser` — regex-first (URL/browser/environment/credentials via the battle-tested `PromptParser` rules) with optional LLM enrichment behind the `intent_engine_enabled` flag. `ParsedIntent.safe_dict()` never leaks credentials. |
| `app/context/context_manager.py` | `ContextManager.build_initial()` — single place to assemble `AgentState` + `ExecutionPlan` for every workflow entrypoint. |
| `app/context/__init__.py` | Public exports (`AgentState`, `ExecutionPlan`, `ContextManager`, `HybridIntentParser`, `get_hybrid_intent_parser`, …). |
| `app/agent/state.py` | Re-export stub so the `app.agent` package surfaces the canonical `AgentState` without duplication. |

## Files Modified

| File | Change |
| --- | --- |
| `app/workflows/trigger_workflow.py` | Added `agent_state` / `execution_plan` fields to `PlatformWorkflowState`; every node captures its outcome into `AgentState` (scope → inventory → test plan → execution results → artifacts); entrypoints seed state via `_build_agent_context()`; serializable `AgentState` + `ExecutionPlan` flow into `RunResponse`. |
| `app/api/routes/trigger.py` | `create_run` now runs the Hybrid Intent Parser behind `intent_engine_enabled`; richer intent (goal, priorities, environment, browser, success criteria) is persisted into `parsed_intent` so post-review/resume can rebuild `AgentState`. |
| `app/agents/code_generation_agent.py` | Receives and records a `context_snapshot` (original prompt, execution plan, inventory path, agent context) into generation metadata for traceability. |

## Key Decisions

1. **Credentials never persist.** `AgentState.credentials` is in-memory only;
   `redacted()` and `safe_dict()` strip it before any logging/emission.
2. **Backward compatibility.** The hybrid parser reuses `PromptParser`'s shared
   credential regexes (existing behavior unchanged) and supplements them with
   inline `username x password y` patterns and login-URL detection.
3. **Flag-gated LLM.** LLM intent extraction only runs when
   `intent_engine_enabled` is on; otherwise the deterministic regex path is the
   sole source.
4. **Regex-only parser never raises.** Any malformed/empty prompt degrades to an
   empty `ParsedIntent` (0 confidence) instead of failing the run.

## Tests

New: 43 tests across 5 files — all pass.

| File | Count | Covers |
| --- | --- | --- |
| `tests/test_agent_state.py` | 7 | aliases, serialisation round-trip, redaction, credential handling |
| `tests/test_intent_parser.py` | 11 | URL/browser/environment/credentials extraction, redaction safety, LLM fallback, empty input |
| `tests/test_execution_planner.py` | 10 | plan construction, ordering, serialisation |
| `tests/test_context_manager.py` | 11 | `build_initial` assembly, redaction, backward-compat |
| `tests/test_workflow_agent_state.py` | 4 | state propagation through workflow nodes + entrypoints |

## Validation

- `pytest` (relevant subset incl. `test_api_workflow`, `test_code_generation`, `test_api`): **74 passed**
- `ruff check` on `app/context` + new tests: **clean** (5 issues auto-fixed)
- Pre-existing failures in `tests/persistence/*` and crawler tests are unrelated
  to this change (require DB/external services).

## Next Steps

- Wire `AgentState` reconstruction on resume/continue endpoints.
- Surface `agent_state` summary in UI progress payloads.
- Add `ExecutionPlan` progress tracking per stage.

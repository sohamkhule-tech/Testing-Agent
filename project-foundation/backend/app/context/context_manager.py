"""
ContextManager — propagates AgentState between workflow stages

A thin, non-invasive bridge between the LangGraph workflow state and the
typed :class:`AgentState`. It is responsible for:

- Creating the initial AgentState at run start (from the raw prompt, parsed
  intent, and credentials).
- Guaranteeing an AgentState exists on the workflow state at every stage
  (``ensure``) — even when the run was started before Phase 1 or resumed from
  a checkpoint, it reconstructs a faithful AgentState from the existing
  workflow fields.
- Capturing each stage's output back into AgentState (inventory, test plan,
  approved plan, IR, generated tests, execution results, artifacts).
- Producing log/emit/persist-safe serialisations (credentials stripped).

It never changes existing stage wiring; it only adds context on top.
"""

from __future__ import annotations

from typing import Any

from app.context.agent_state import AgentState
from app.context.execution_planner import ExecutionPlan, ExecutionPlanner, get_execution_planner
from app.context.intent_parser import ParsedIntent
from app.logging import LoggerMixin
from app.reasoning.models import ReasoningResult


class ContextManager(LoggerMixin):
    """
    Wraps AgentState creation, reconstruction, and per-stage capture.
    """

    def __init__(self, planner: ExecutionPlanner | None = None) -> None:
        super().__init__()
        self.planner = planner or get_execution_planner()

    # ------------------------------------------------------------------
    # Creation & reconstruction
    # ------------------------------------------------------------------

    def build_initial(
        self,
        *,
        run_id: str,
        request_data: dict[str, Any] | None = None,
        requested_by: str | None = None,
        user_prompt: str | None = None,
        prompt_context: dict[str, Any] | None = None,
        parsed_intent: ParsedIntent | None = None,
        credentials: dict[str, Any] | None = None,
    ) -> AgentState:
        """
        Build the initial AgentState from the raw prompt and its interpretation.

        Args:
            run_id: Workflow run id (stored for traceability in artifacts).
            request_data: Run request data (target URL/environment).
            requested_by: Run owner.
            user_prompt: Verbatim (already redacted) user prompt.
            prompt_context: ParsedPromptIntent.to_dict() compatible dict.
            parsed_intent: Rich ParsedIntent from the Hybrid Intent Parser.
            credentials: In-memory credentials (never logged/emitted).

        Returns:
            A fully-populated AgentState.
        """
        included_modules = list((parsed_intent.included_modules if parsed_intent else []) or (prompt_context or {}).get("focus_areas") or [])
        excluded_modules = list((parsed_intent.excluded_modules if parsed_intent else []) or (prompt_context or {}).get("excluded_modules") or [])

        pc = parsed_intent.prompt_context if parsed_intent else (dict(prompt_context or {}))
        creds = (
            dict(credentials or {})
            or (parsed_intent.credentials if parsed_intent else {})
            or {}
        )

        ta = (request_data or {}).get("target_application") or {}
        environment = (
            (parsed_intent.environment if parsed_intent else None)
            or ta.get("environment")
            or "staging"
        )

        return AgentState(
            original_user_prompt=user_prompt,
            parsed_intent=pc,
            execution_goal=(parsed_intent.goal if parsed_intent else None),
            workflow_scope={
                "target_url": ta.get("base_url") or ta.get("url") or "",
                "environment": environment,
                "included_modules": list(included_modules),
                "excluded_modules": list(excluded_modules),
                "included_pages": list(pc.get("included_pages") or []),
                "excluded_pages": list(pc.get("excluded_pages") or []),
            },
            included_modules=included_modules,
            excluded_modules=excluded_modules,
            credentials=creds,
            priorities=list(parsed_intent.priorities if parsed_intent else []),
            business_objective=(parsed_intent.business_objective if parsed_intent else None),
            artifacts={"run_id": run_id, "requested_by": requested_by, "workspace_path": None},
        )

    def ensure(self, state: Any) -> AgentState:
        """
        Guarantee ``state.agent_state`` exists.

        If it is already set it is returned unchanged. Otherwise it is
        reconstructed from the existing workflow fields so Phase 1 never breaks
        older runs or resume flows.
        """
        if getattr(state, "agent_state", None) is not None:
            return state.agent_state

        agent_state = AgentState(
            original_user_prompt=getattr(state, "user_prompt", None),
            parsed_intent=dict(getattr(state, "prompt_context", None) or {}),
            inventory=self._inventory_from_state(state),
            test_plan=self._test_plan_from_state(state),
            approved_plan=self._approved_plan_from_state(state),
            generated_ir=self._generated_ir_from_state(state),
            generated_tests=self._generated_tests_from_state(state),
            execution_results=self._execution_results_from_state(state),
            artifacts={
                "run_id": getattr(state, "run_id", None),
                "workspace_path": getattr(state, "workspace_path", None),
            },
        )
        state.agent_state = agent_state
        return agent_state

    def build_plan(
        self,
        *,
        state: Any | None = None,
        user_prompt: str | None = None,
        request_data: dict[str, Any] | None = None,
        agent_state: AgentState | None = None,
    ) -> ExecutionPlan:
        """Build the execution plan for the current AgentState/intent."""
        as_ = agent_state or (self.ensure(state) if state is not None else None)
        plan = self.planner.build(
            user_prompt=user_prompt or (as_.original_user_prompt if as_ else None),
            parsed_intent=as_.parsed_intent if as_ else None,
            request_data=request_data,
            agent_state=as_,
        )
        return plan

    async def reason_then_plan(
        self,
        *,
        user_prompt: str,
        run_id: str,
        request_data: dict[str, Any] | None = None,
        requested_by: str | None = None,
        prompt_context: dict[str, Any] | None = None,
        llm_client: Any | None = None,
        inventory: Any | None = None,
        app_metadata: dict[str, Any] | None = None,
    ) -> tuple[AgentState, ExecutionPlan, ReasoningResult]:
        """
        Phase 4.5: reasoning-first execution.

        ReasoningEngine.reason() → enrich AgentState → ExecutionPlanner.build()
        → ExecutionPlan.enrich_from_reasoning(). Never builds a plan before reasoning.
        """
        from app.reasoning.constraints import ConstraintResolver
        from app.reasoning.engine import ReasoningEngine

        # 1. Build base AgentState from parsed intent
        agent_state = self.build_initial(
            run_id=run_id,
            request_data=request_data,
            requested_by=requested_by,
            user_prompt=user_prompt,
            prompt_context=prompt_context,
        )

        # 2. REASON first — never build plan without reasoning
        engine = ReasoningEngine(llm_client=llm_client)
        reasoning = await engine.reason(
            user_prompt,
            agent_state=agent_state,
            inventory=inventory,
            application_metadata=app_metadata,
        )

        # 3. Apply reasoning constraints to AgentState
        resolver = ConstraintResolver()
        resolver.apply_to_agent_state(agent_state, reasoning)

        # 4. Build ExecutionPlan from reasoned state
        plan = self.planner.build(
            user_prompt=user_prompt,
            parsed_intent=agent_state.parsed_intent,
            request_data=request_data,
            agent_state=agent_state,
        )

        # 5. Enrich plan with reasoning
        plan.enrich_from_reasoning(reasoning)
        resolver.apply_to_plan(plan, reasoning)

        # 6. Record reasoning trace
        trace = engine.generate_trace(reasoning, run_id, user_prompt)
        plan.reasoning_trace = trace.trace_summary()
        agent_state.merge(
            business_objective=reasoning.business_intent.goal,
            priorities=list(dict.fromkeys(reasoning.testing_intent.strategies + agent_state.priorities)),
        )

        self.logger.info("reasoning_first_plan_built", run_id=run_id, detected=reasoning.detected_intent)
        return agent_state, plan, reasoning

    # ------------------------------------------------------------------
    # Read/write helpers
    # ------------------------------------------------------------------

    def get(self, state: Any, key: str, default: Any = None) -> Any:
        """Read a field from the state's AgentState (None-safe)."""
        agent_state = self.ensure(state)
        return getattr(agent_state, key, default)

    def set(self, state: Any, key: str, value: Any) -> None:
        """Write a field to the state's AgentState."""
        agent_state = self.ensure(state)
        setattr(agent_state, key, value)

    # ------------------------------------------------------------------
    # Per-stage capture
    # ------------------------------------------------------------------

    def capture_inventory(self, state: Any, *, inventory_path: str | None, summary: dict[str, Any] | None) -> None:
        agent_state = self.ensure(state)
        agent_state.inventory = {"path": inventory_path, "summary": summary or {}}
        agent_state.artifacts["inventory_path"] = inventory_path

    def capture_test_plan(self, state: Any, *, path: str | None, summary: dict[str, Any] | None) -> None:
        agent_state = self.ensure(state)
        agent_state.test_plan = {"path": path, "summary": summary or {}}
        agent_state.artifacts["test_plan_path"] = path

    def capture_review(
        self,
        state: Any,
        *,
        review_result: dict[str, Any],
    ) -> None:
        """
        Record the human-review outcome while preserving the original prompt,
        parsed intent, and execution plan.
        """
        agent_state = self.ensure(state)
        agent_state.approved_plan = {
            "approved_test_plan_path": review_result.get("approved_test_plan_path"),
            "approved_test_plan_md_path": review_result.get("approved_test_plan_md_path"),
            "review_status": review_result.get("review_status"),
            "review_decision": review_result.get("review_decision"),
            "review_version": review_result.get("review_version"),
            "reviewer_name": review_result.get("reviewer_name"),
            "approved_scenarios": review_result.get("approved_scenarios", 0),
            "rejected_scenarios": review_result.get("rejected_scenarios", 0),
            "total_scenarios": review_result.get("total_scenarios", 0),
            "original_prompt": agent_state.original_user_prompt,
            "parsed_intent": agent_state.parsed_intent,
            "execution_plan": (
                getattr(state, "execution_plan", None).to_serializable()
                if getattr(state, "execution_plan", None) is not None
                else None
            ),
        }
        agent_state.artifacts["approved_test_plan_path"] = review_result.get("approved_test_plan_path")

    def capture_code_generation(self, state: Any, *, result: dict[str, Any]) -> None:
        agent_state = self.ensure(state)
        agent_state.generated_ir = {
            "ir_path": result.get("ir_path"),
            "dependency_graph_path": result.get("dependency_graph_path"),
        }
        agent_state.generated_tests = {
            "project_path": result.get("project_path"),
            "metadata_path": result.get("metadata_path"),
            "status": result.get("status"),
            "files_generated": result.get("files_generated", 0),
            "scenarios_implemented": result.get("scenarios_implemented", 0),
        }
        agent_state.artifacts["generated_project_path"] = result.get("project_path")
        agent_state.artifacts["generated_tests_path"] = result.get("project_path")

    def capture_execution(self, state: Any, *, result: dict[str, Any]) -> None:
        agent_state = self.ensure(state)
        agent_state.execution_results = {
            "status": result.get("status"),
            "duration_seconds": result.get("duration_seconds", 0.0),
            "metrics": result.get("metrics", {}),
            "reports": result.get("report_files", {}),
            "artifacts_path": result.get("artifacts_path"),
            "reports_path": result.get("reports_path"),
        }
        agent_state.artifacts["execution_artifacts_path"] = result.get("artifacts_path")

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_serializable(self, state: Any, *, redact_credentials: bool = True) -> dict[str, Any]:
        """Serialize the state's AgentState (credentials stripped by default)."""
        agent_state = self.ensure(state)
        return agent_state.to_serializable(redact_credentials=redact_credentials)

    # ------------------------------------------------------------------
    # Reconstruction helpers (backward compatibility)
    # ------------------------------------------------------------------

    @staticmethod
    def _inventory_from_state(state: Any) -> dict[str, Any]:
        if getattr(state, "inventory_path", None) or getattr(state, "inventory_summary", None):
            return {
                "path": getattr(state, "inventory_path", None),
                "summary": getattr(state, "inventory_summary", None) or {},
            }
        return {}

    @staticmethod
    def _test_plan_from_state(state: Any) -> dict[str, Any]:
        if getattr(state, "test_plan_path", None) or getattr(state, "test_plan_summary", None):
            return {
                "path": getattr(state, "test_plan_path", None),
                "summary": getattr(state, "test_plan_summary", None) or {},
            }
        return {}

    @staticmethod
    def _approved_plan_from_state(state: Any) -> dict[str, Any]:
        if getattr(state, "approved_test_plan_path", None):
            return {
                "approved_test_plan_path": getattr(state, "approved_test_plan_path", None),
                "review_status": getattr(state, "review_status", None),
                "review_decision": getattr(state, "review_decision", None),
                "reviewer_name": getattr(state, "reviewer_name", None),
                "original_prompt": getattr(state, "user_prompt", None),
                "parsed_intent": dict(getattr(state, "prompt_context", None) or {}),
            }
        return {}

    @staticmethod
    def _generated_ir_from_state(state: Any) -> dict[str, Any]:
        ws = getattr(state, "workspace_path", None)
        if ws:
            return {"ir_path": f"{ws}/artifacts/ir/code-generation-ir.json"}
        return {}

    @staticmethod
    def _generated_tests_from_state(state: Any) -> dict[str, Any]:
        if getattr(state, "generated_project_path", None):
            return {
                "project_path": getattr(state, "generated_project_path", None),
                "metadata_path": getattr(state, "code_generation_metadata_path", None),
                "status": getattr(state, "code_generation_status", None),
            }
        return {}

    @staticmethod
    def _execution_results_from_state(state: Any) -> dict[str, Any]:
        if getattr(state, "execution_status", None):
            return {
                "status": getattr(state, "execution_status", None),
                "metrics": {
                    "total": getattr(state, "tests_total", 0),
                    "passed": getattr(state, "tests_passed", 0),
                    "failed": getattr(state, "tests_failed", 0),
                    "pass_rate": getattr(state, "pass_rate", 0.0),
                },
                "artifacts_path": getattr(state, "execution_artifacts_path", None),
            }
        return {}


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_context_manager_singleton: ContextManager | None = None


def get_context_manager() -> ContextManager:
    """Return the process-wide ContextManager singleton."""
    global _context_manager_singleton
    if _context_manager_singleton is None:
        _context_manager_singleton = ContextManager()
    return _context_manager_singleton

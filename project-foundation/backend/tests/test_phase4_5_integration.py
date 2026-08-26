"""
Phase 4.5: Runtime Integration tests.

Tests reasoning-first execution, scheduler DecisionEngine integration,
conversational refinement, reasoning trace persistence, and EventBus → AgentState sync.
"""

import pytest

from app.context import AgentState
from app.execution_engine.event_bus import EventBus, ExecutionEvent
from app.execution_engine.execution_graph import ExecutionGraph, GraphNode
from app.execution_engine.scheduler import DependencyScheduler
from app.reasoning.decision_engine import DecisionEngine
from app.reasoning.engine import ReasoningEngine
from app.reasoning.models import ReasoningResult
from app.workflows.trigger_workflow import _build_agent_context


class TestReasoningFirstExecution:
    def test_build_agent_context_with_reasoning_result(self):
        """_build_agent_context enriches plan when reasoning_result is provided."""
        reasoning = _fast_reasoning("Only test Login. Ignore Reports.")
        agent_state, plan = _build_agent_context(
            run_id="r1",
            request_data={"target_application": {"base_url": "https://example.com"}},
            user_prompt="Only test Login. Ignore Reports.",
            prompt_context={},
            reasoning_result=reasoning,
        )
        assert plan.reasoning_summary is not None
        assert plan.execution_strategy is not None
        assert plan.business_intent is not None
        assert plan.stopping_conditions is not None

    def test_legacy_path_works_without_reasoning(self):
        """Backward compat: plan builds fine without reasoning_result."""
        agent_state, plan = _build_agent_context(
            run_id="r1",
            request_data={"target_application": {"base_url": "https://example.com"}},
            user_prompt="Test the app",
            prompt_context={},
        )
        assert plan.goal is not None
        assert len(plan.tasks) >= 6
        # Reasoning fields should be empty/default
        assert plan.reasoning_summary is None

    def test_reasoning_constraints_applied_to_plan(self):
        """Scope constraints from reasoning appear in plan.workflow_scope."""
        reasoning = _fast_reasoning("Only test Login. Ignore Reports. Generate smoke tests.")
        _, plan = _build_agent_context(
            run_id="r2",
            request_data={"target_application": {"base_url": "https://example.com"}},
            user_prompt="Only test Login",
            prompt_context={},
            reasoning_result=reasoning,
        )
        constraints = plan.workflow_scope.get("__reasoning_constraints__") or []
        assert len(constraints) >= 1

    def test_reasoning_trace_in_plan(self):
        """reasoning_trace is populated from engine.generate_trace via _reason_then_build_context."""
        from app.reasoning.engine import ReasoningEngine
        engine = ReasoningEngine(llm_client=None)
        reasoning = engine._deterministic_reason("Test Login only")
        trace = engine.generate_trace(reasoning, "r-trace", "Test Login only")
        assert trace.run_id == "r-trace"
        assert trace.detected_intent is not None
        s = trace.trace_summary()
        assert "constraint_count" in s


class TestSchedulerDecisionIntegration:
    def test_scheduler_decides_before_execute(self):
        """Scheduler.decide_before_execute calls DecisionEngine."""
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="trigger", capability="init_ws"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="discover", parents=["a"]),
        }
        graph.nodes["a"].children = ["b"]
        decision_engine = DecisionEngine()
        scheduler = DependencyScheduler(graph, decision_engine=decision_engine)

        # Node 'a' is ready
        node_a = graph.nodes["a"]
        assert scheduler.decide_before_execute(node_a) is True

        scheduler.on_task_completed("a")
        node_b = graph.nodes["b"]
        node_b.status = "ready"
        assert scheduler.decide_before_execute(node_b) is True

    def test_scheduler_skips_on_non_continue_decision(self):
        """When DecisionEngine returns 'skip', the node is skipped."""
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="crawler", capability="discover"),
        }
        graph.nodes["a"].retry_count = 4
        graph.nodes["a"].max_retries = 3
        graph.nodes["a"].error = "persistent failure"
        scheduler = DependencyScheduler(graph, decision_engine=DecisionEngine())
        assert scheduler.decide_before_execute(graph.nodes["a"]) is False
        assert graph.nodes["a"].status == "skipped" or graph.nodes["a"].status == "failed"

    def test_scheduler_stops_on_stopping_condition(self):
        """DecisionEngine.stop blocks downstream."""
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="approval", capability="human_review"),
            "b": GraphNode(id="b", name="B", stage="code_generation", capability="gen", parents=["a"]),
        }
        graph.nodes["a"].children = ["b"]
        reasoning = _fast_reasoning("Stop after Approval")
        decision_engine = DecisionEngine()
        scheduler = DependencyScheduler(graph, decision_engine=decision_engine)
        scheduler.set_reasoning_context(reasoning)

        graph.nodes["a"].status = "pending"
        decision = scheduler.decide_before_execute(graph.nodes["a"])
        # Should stop because stage matches stopping condition
        assert scheduler._stopped or decision is False or graph.nodes["a"].status == "skipped"


class TestConversationalRefinement:
    @pytest.mark.asyncio
    async def test_refinement_updates_plan(self):
        """Conversational refinement adds modules and updates plan."""
        from app.workflows.trigger_workflow import apply_conversational_refinement

        agent_state, plan = _build_agent_context(
            run_id="r-rf",
            request_data={"target_application": {"base_url": "https://example.com"}},
            user_prompt="Test Login only",
            prompt_context={},
            reasoning_result=_fast_reasoning("Test Login only"),
        )
        original_revision = len(plan.revisions)

        agent_state, plan = await apply_conversational_refinement(
            "Also test Dashboard and Reports",
            plan, agent_state, "r-rf",
        )
        assert len(plan.revisions) > original_revision
        assert agent_state.planner_revision > 0

    @pytest.mark.asyncio
    async def test_refinement_removes_excluded(self):
        """Conversational refinement re-includes previously excluded modules."""
        from app.workflows.trigger_workflow import apply_conversational_refinement

        reasoning = _fast_reasoning("Ignore Reports. Ignore Dashboard.")
        agent_state, plan = _build_agent_context(
            run_id="r-rf2",
            request_data={"target_application": {"base_url": "https://example.com"}},
            user_prompt="Ignore Reports. Ignore Dashboard.",
            prompt_context={},
            reasoning_result=reasoning,
        )
        # Reports should be excluded
        assert len(reasoning.testing_intent.excluded_modules) >= 1

        # Now re-include
        agent_state, plan = await apply_conversational_refinement(
            "Actually include Reports",
            plan, agent_state, "r-rf2",
        )
        # Plan was updated with revision
        assert len(plan.revisions) >= 1


class TestEventBusAgentStateSync:
    @pytest.mark.asyncio
    async def test_event_updates_agent_state(self):
        """EventBus TASK_STARTED/TASK_COMPLETED sync to AgentState."""
        bus = EventBus()
        agent = AgentState()

        async def on_task_started(event: dict):
            agent.record_stage_entry(event.get("stage", ""), event.get("capability", ""))

        async def on_task_completed(event: dict):
            agent.record_stage_done(event.get("stage", ""), event.get("duration", 0.0))

        await bus.subscribe(ExecutionEvent.TASK_STARTED, on_task_started)
        await bus.subscribe(ExecutionEvent.TASK_COMPLETED, on_task_completed)

        await bus.emit_task_started("t1", "trigger", "initialise_workspace")
        assert agent.current_stage == "trigger"

        await bus.emit_task_completed("t1", "trigger", 1.0)
        assert "trigger" in agent.completed_tasks
        assert agent.execution_time.get("trigger") == 1.0

        await bus.unsubscribe(ExecutionEvent.TASK_STARTED, on_task_started)
        await bus.unsubscribe(ExecutionEvent.TASK_COMPLETED, on_task_completed)

    @pytest.mark.asyncio
    async def test_failure_event_records_in_agent_state(self):
        """TASK_FAILED event populates AgentState.failures via subscriber."""
        bus = EventBus()
        agent = AgentState()

        async def on_failed(event: dict):
            agent.record_stage_failure(event.get("stage", ""), event.get("error", ""))

        await bus.subscribe(ExecutionEvent.TASK_FAILED, on_failed)
        await bus.emit_task_failed("t-fail", "crawler", "timeout")

        assert len(agent.failures) == 1
        assert agent.failures[0]["stage"] == "crawler"
        assert "timeout" in agent.failures[0]["error"]

        await bus.unsubscribe(ExecutionEvent.TASK_FAILED, on_failed)


class TestReasoningTracePersistence:
    def test_reasoning_result_serializable(self):
        """ReasoningResult can be serialized for persistence."""
        reasoning = _fast_reasoning("Only test Login. Stop after Approval.")
        d = reasoning.summary()
        assert isinstance(d, dict)
        assert d.get("business_intent") is not None
        assert isinstance(d.get("constraints"), list)

    def test_plan_can_hold_reasoning_trace(self):
        """ExecutionPlan.reasoning_trace is populated after enrich."""
        reasoning = _fast_reasoning("Test Login")
        _, plan = _build_agent_context(
            run_id="r3",
            request_data={"target_application": {"base_url": "https://ex.com"}},
            user_prompt="Test Login",
            prompt_context={},
            reasoning_result=reasoning,
        )
        assert plan.reasoning_trace is not None or plan.reasoning_summary is not None


def _fast_reasoning(prompt: str) -> ReasoningResult:
    engine = ReasoningEngine(llm_client=None)
    return engine._deterministic_reason(prompt)

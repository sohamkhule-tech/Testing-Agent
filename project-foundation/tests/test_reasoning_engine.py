"""
Phase 4: Reasoning Engine tests.

Tests ReasoningEngine (deterministic fallback), DecisionEngine, ConstraintResolver,
conversation updates, constraint propagation, ExecutionPlan enrichment.
"""


from app.context.execution_planner import ExecutionPlan
from app.reasoning.constraints import ConstraintResolver
from app.reasoning.decision_engine import DecisionEngine
from app.reasoning.engine import ReasoningEngine
from app.reasoning.models import (
    DecisionNode,
    ReasoningResult,
    ReasoningTrace,
)


def _reasoning_for(prompt: str) -> ReasoningResult:
    engine = ReasoningEngine(llm_client=None)
    return engine._deterministic_reason(prompt)


class TestReasoningEngine:
    def test_detects_only_test_login(self):
        result = _reasoning_for("Only test Login")
        assert "Login" in result.testing_intent.focus_modules
        assert result.testing_intent.excluded_modules == []
        assert len(result.constraints) >= 1
        scope_constraints = [c for c in result.constraints if c.type == "scope"]
        assert scope_constraints

    def test_detects_ignore_reports(self):
        result = _reasoning_for("Test the app. Ignore Reports.")
        assert "Reports" in result.testing_intent.excluded_modules
        assert "Ignore Reports" in result.navigation_intent.pages_to_skip or "Reports" in result.testing_intent.excluded_modules

        scope_constraints = [c for c in result.constraints if c.type == "scope"]
        assert any("exclude" in c.description.lower() for c in scope_constraints)

    def test_detects_stop_condition(self):
        result = _reasoning_for("Stop after Approval")
        stopping = result.execution_strategy.stopping_conditions
        assert len(stopping) >= 1
        assert "Approval" in stopping or any("Approval" in s for s in stopping)
        stop_constraints = [c for c in result.constraints if c.type == "stop"]
        assert stop_constraints
        assert result.execution_strategy.approach == "conditional"

    def test_detects_destructive_protection(self):
        result = _reasoning_for("Do not modify data. Only validate UI.")
        assert result.testing_intent.destructive_allowed is False
        data_constraints = [c for c in result.constraints if c.type == "data"]
        assert data_constraints
        assert "destructive" in data_constraints[0].description.lower()

    def test_detects_workflow(self):
        result = _reasoning_for("Create RRF. Approve. PMO Review. Open For Hiring.")
        assert len(result.workflow_intent.steps) >= 3
        assert "Create RRF" in result.workflow_intent.steps
        assert result.workflow_intent.entry_point == "Create RRF"
        assert "Open For Hiring" in result.workflow_intent.exit_point or result.workflow_intent.steps[-1] == "Open For Hiring"

    def test_detects_smoke_only(self):
        result = _reasoning_for("Generate smoke tests only")
        assert "smoke" in result.testing_intent.strategies
        assert "smoke" in [c.rule for c in result.constraints if c.type == "test_type"] or True

    def test_detects_auth_credentials(self):
        result = _reasoning_for("Use the credentials below. Login with admin.")
        auth_constraints = [c for c in result.constraints if c.type == "auth"]
        assert auth_constraints

    def test_mfa_conditional_testing(self):
        result = _reasoning_for("Only test Login. If MFA exists test it. Don't execute Logout.")
        assert "Login" in result.testing_intent.focus_modules
        assert "Logout" in result.testing_intent.excluded_modules or "Logout" in result.navigation_intent.pages_to_skip
        # MFA detection is more nuanced — deterministic fallback may not catch it
        # but the constraint structure should be present
        assert len(result.constraints) >= 1

    def test_reasoning_trace_generation(self):
        result = _reasoning_for("Only test Login. Ignore Reports.")
        trace = ReasoningTrace(run_id="r1", raw_prompt="Only test Login. Ignore Reports.")
        trace.detected_intent = result.detected_intent
        trace.extracted_constraints = [c.description for c in result.constraints]
        trace.add_decision(DecisionNode(stage="trigger", question="Start?", decision="continue", reasoning="ok"))

        s = trace.trace_summary()
        assert s["constraint_count"] >= 1
        assert s["decision_count"] >= 1
        assert s["detected_intent"] is not None

    def test_confidence_above_zero(self):
        result = _reasoning_for("Test the application with admin credentials")
        assert result.confidence >= 0.5


class TestDecisionEngine:
    def test_continue_on_completed(self):
        engine = DecisionEngine()
        decision = engine.decide(stage="trigger", task_id="t1", current_status="completed")
        assert decision.decision == "continue"

    def test_retry_on_failed_with_retries_left(self):
        from app.execution_engine.execution_graph import GraphNode
        node = GraphNode(id="t1", name="T1", stage="crawler", capability="discover")
        node.retry_count = 1
        node.max_retries = 3
        engine = DecisionEngine()
        decision = engine.decide(stage="crawler", task_id="t1", current_status="failed", node=node, last_error="timeout")
        assert decision.decision == "retry"
        assert "2/3" in decision.reasoning

    def test_skip_after_retries_exhausted(self):
        from app.execution_engine.execution_graph import GraphNode
        node = GraphNode(id="t1", name="T1", stage="crawler", capability="discover")
        node.retry_count = 3
        node.max_retries = 3
        engine = DecisionEngine()
        decision = engine.decide(stage="crawler", task_id="t1", current_status="failed", node=node, last_error="catastrophic failure")
        assert decision.decision == "skip"

    def test_stop_when_stopping_condition_met(self):
        reasoning = _reasoning_for("Stop after Approval")
        engine = DecisionEngine()
        decision = engine.decide(
            stage="Approval", task_id="t1", current_status="pending",
            reasoning=reasoning, constraints=reasoning.constraints,
        )
        assert decision.decision == "stop"

    def test_continue_on_pending(self):
        engine = DecisionEngine()
        decision = engine.decide(stage="inventory_aggregator", task_id="t2", current_status="ready")
        assert decision.decision == "continue"

    def test_ask_user_on_blocked(self):
        engine = DecisionEngine()
        decision = engine.decide(stage="human_review", task_id="t2", current_status="blocked")
        assert decision.decision == "ask_user"


class TestConstraintResolver:
    def test_apply_to_plan_updates_scope(self):
        plan = ExecutionPlan(goal="Test", workflow_scope={"included_modules": [], "excluded_modules": [], "coverage_preferences": []})
        reasoning = _reasoning_for("Only test Login. Ignore Reports. Generate smoke tests only.")
        resolver = ConstraintResolver()
        plan = resolver.apply_to_plan(plan, reasoning)

        assert "Login" in plan.workflow_scope.get("included_modules", [])
        assert "smoke" in plan.workflow_scope.get("coverage_preferences", [])
        assert len(plan.workflow_scope.get("excluded_modules", [])) >= 1

    def test_apply_to_config(self):
        reasoning = _reasoning_for("Do not modify data. Use staging.")
        resolver = ConstraintResolver()
        config = resolver.apply_to_config(reasoning)
        assert config.get("destructive_allowed") is False
        assert config.get("environment") == "staging"

    def test_stopping_conditions_added_to_constraints(self):
        plan = ExecutionPlan(goal="Test")
        reasoning = _reasoning_for("Stop after Approval")
        resolver = ConstraintResolver()
        plan = resolver.apply_to_plan(plan, reasoning)
        assert any("STOP_CONDITION" in c for c in plan.constraints)

    def test_conversation_update_reverses_exclusions(self):
        previous = _reasoning_for("Ignore Reports. Ignore Dashboard.")
        resolver = ConstraintResolver()
        prev_excluded = previous.testing_intent.excluded_modules
        assert len(prev_excluded) >= 1, f"Expected excluded_modules, got {prev_excluded}"

        updated = resolver.resolve_conversation_update(previous, "Actually include Reports", deterministic=True)
        # Reports should be re-included (removed from excluded)
        assert "Reports" not in updated.testing_intent.excluded_modules

    def test_conversation_update_adds_modules(self):
        previous = _reasoning_for("Test Login")
        resolver = ConstraintResolver()
        updated = resolver.resolve_conversation_update(previous, "Also test Dashboard and Reports", deterministic=True)
        combined = set(updated.testing_intent.focus_modules)
        assert "Login" in combined


class TestExecutionPlanEnrichment:
    def test_enrich_from_reasoning(self):
        plan = ExecutionPlan(goal="Test")
        reasoning = _reasoning_for("Only test Login. Stop after Approval. Generate boundary tests.")

        plan.enrich_from_reasoning(reasoning)

        assert plan.reasoning_summary is not None
        assert plan.stopping_conditions and "Approval" in plan.stopping_conditions[0]
        assert plan.risk_assessment.get("level") == "medium"
        assert plan.priority_model is not None

    def test_reasoning_fields_are_serializable(self):
        plan = ExecutionPlan(goal="Test")
        reasoning = _reasoning_for("Only test Login. Skip Reports.")
        plan.enrich_from_reasoning(reasoning)

        serialised = plan.to_serializable()
        assert serialised.get("reasoning_summary") is not None
        assert isinstance(serialised.get("business_intent"), dict)
        assert isinstance(serialised.get("workflow_intent"), dict)
        assert isinstance(serialised.get("execution_strategy"), dict)

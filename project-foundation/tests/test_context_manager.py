"""
ContextManager tests.

Verifies AgentState creation, backward-compatible reconstruction, per-stage
capture, and credential redaction when serialising.
"""

from types import SimpleNamespace

import pytest

from app.context import AgentState, ExecutionPlan
from app.context.context_manager import get_context_manager


def _make_legacy_state() -> SimpleNamespace:
    """A fake workflow state carrying only the pre-Phase-1 fields."""
    return SimpleNamespace(
        agent_state=None,
        user_prompt="Test the dashboard",
        prompt_context={"focus_areas": ["Dashboard"], "excluded_modules": ["Settings"], "raw_text": "Test the dashboard"},
        workspace_path="/tmp/run-1",
        run_id="run-1",
        inventory_path="/tmp/run-1/contracts/inventory.json",
        inventory_summary={"page_count": 5},
        test_plan_path="/tmp/run-1/contracts/test-plan.json",
        test_plan_summary={"scenario_count": 12},
        approved_test_plan_path="/tmp/run-1/contracts/approved-test-plan.json",
        review_status="approved",
        review_decision="approve",
        reviewer_name="qa",
        generated_project_path="/tmp/run-1/artifacts/generated-tests/playwright",
        code_generation_metadata_path="/tmp/run-1/artifacts/generated-tests/playwright/code-generation-metadata.json",
        code_generation_status="completed",
        execution_status="completed",
        tests_total=12,
        tests_passed=10,
        tests_failed=2,
        pass_rate=83.3,
        execution_artifacts_path="/tmp/run-1/artifacts",
        execution_plan=None,
    )


@pytest.mark.unit
class TestContextManagerBuildInitial:
    def test_builds_initial_from_prompt_context(self):
        cm = get_context_manager()
        state = cm.build_initial(
            run_id="run-1",
            request_data={"target_application": {"base_url": "https://example.com", "environment": "qa"}},
            requested_by="tester",
            user_prompt="Focus on Dashboard. Exclude Settings.",
            prompt_context={
                "raw_text": "Focus on Dashboard. Exclude Settings.",
                "focus_areas": ["Dashboard"],
                "excluded_modules": ["Settings"],
                "included_pages": [],
                "excluded_pages": [],
                "coverage_preferences": [],
                "output_preferences": [],
                "custom_instructions": "",
                "has_credentials": False,
            },
        )

        assert state.original_user_prompt == "Focus on Dashboard. Exclude Settings."
        assert state.included_modules == ["Dashboard"]
        assert state.excluded_modules == ["Settings"]
        assert state.workflow_scope["environment"] == "qa"
        assert state.workflow_scope["target_url"] == "https://example.com"
        assert state.artifacts["run_id"] == "run-1"

    def test_builds_initial_from_parsed_intent(self):
        from app.context import ParsedIntent

        parsed = ParsedIntent(
            goal="Verify billing",
            included_modules=["Billing"],
            excluded_modules=["Admin"],
            priorities=["critical"],
            business_objective="Protect revenue",
            success_criteria=["No payment failures"],
            environment="staging",
            prompt_context={"focus_areas": ["Billing"], "excluded_modules": ["Admin"], "raw_text": "x"},
        )
        cm = get_context_manager()
        state = cm.build_initial(run_id="r", user_prompt="Test billing", parsed_intent=parsed)

        assert state.execution_goal == "Verify billing"
        assert state.business_objective == "Protect revenue"
        assert state.priorities == ["critical"]
        assert state.workflow_scope["environment"] == "staging"

    def test_credentials_carried_into_agent_state(self):
        cm = get_context_manager()
        state = cm.build_initial(
            run_id="r",
            user_prompt="test",
            prompt_context={},
            credentials={"username": "u", "password": "p", "auth_strategy": "form"},
        )
        assert state.credentials == {"username": "u", "password": "p", "auth_strategy": "form"}
        # redacted serialisation strips them
        assert cm.to_serializable(SimpleNamespace(agent_state=state))["credentials"] == {}


@pytest.mark.unit
class TestContextManagerEnsure:
    def test_returns_existing_agent_state(self):
        cm = get_context_manager()
        state = _make_legacy_state()
        existing = AgentState(original_user_prompt="kept")
        state.agent_state = existing
        assert cm.ensure(state) is existing

    def test_reconstructs_from_legacy_fields(self):
        cm = get_context_manager()
        state = _make_legacy_state()
        agent_state = cm.ensure(state)

        assert state.agent_state is agent_state
        assert agent_state.original_user_prompt == "Test the dashboard"
        assert agent_state.parsed_intent["focus_areas"] == ["Dashboard"]
        assert agent_state.inventory["path"] == "/tmp/run-1/contracts/inventory.json"
        assert agent_state.test_plan["path"] == "/tmp/run-1/contracts/test-plan.json"
        assert agent_state.approved_plan["approved_test_plan_path"] == "/tmp/run-1/contracts/approved-test-plan.json"
        assert agent_state.generated_tests["project_path"].endswith("playwright")
        assert agent_state.execution_results["metrics"]["passed"] == 10
        assert agent_state.artifacts["run_id"] == "run-1"


@pytest.mark.unit
class TestContextManagerCapture:
    def test_capture_inventory(self):
        cm = get_context_manager()
        state = SimpleNamespace(agent_state=AgentState())
        cm.capture_inventory(state, inventory_path="/x/inventory.json", summary={"page_count": 5})
        assert state.agent_state.inventory["path"] == "/x/inventory.json"
        assert state.agent_state.artifacts["inventory_path"] == "/x/inventory.json"

    def test_capture_test_plan(self):
        cm = get_context_manager()
        state = SimpleNamespace(agent_state=AgentState())
        cm.capture_test_plan(state, path="/x/test-plan.json", summary={"scenario_count": 8})
        assert state.agent_state.test_plan["summary"]["scenario_count"] == 8

    def test_capture_review_preserves_intent_and_plan(self):
        cm = get_context_manager()
        state = SimpleNamespace(
            agent_state=AgentState(
                original_user_prompt="Original prompt",
                parsed_intent={"focus_areas": ["Dashboard"]},
            ),
            execution_plan=ExecutionPlan(goal="g", execution_order=["trigger"]),
        )
        cm.capture_review(state, review_result={
            "approved_test_plan_path": "/x/approved.json",
            "review_status": "approved",
            "review_decision": "approve",
            "reviewer_name": "qa",
            "approved_scenarios": 10,
            "rejected_scenarios": 2,
            "total_scenarios": 12,
        })

        approved = state.agent_state.approved_plan
        assert approved["approved_test_plan_path"] == "/x/approved.json"
        # Human Review must preserve original prompt / parsed intent / execution plan
        assert approved["original_prompt"] == "Original prompt"
        assert approved["parsed_intent"]["focus_areas"] == ["Dashboard"]
        assert approved["execution_plan"]["goal"] == "g"

    def test_capture_code_generation(self):
        cm = get_context_manager()
        state = SimpleNamespace(agent_state=AgentState())
        cm.capture_code_generation(state, result={
            "project_path": "/x/playwright",
            "metadata_path": "/x/playwright/code-generation-metadata.json",
            "status": "completed",
            "files_generated": 24,
            "scenarios_implemented": 10,
            "ir_path": "/x/ir/ir.json",
        })
        assert state.agent_state.generated_tests["project_path"] == "/x/playwright"
        assert state.agent_state.generated_ir["ir_path"] == "/x/ir/ir.json"
        assert state.agent_state.artifacts["generated_project_path"] == "/x/playwright"

    def test_capture_execution(self):
        cm = get_context_manager()
        state = SimpleNamespace(agent_state=AgentState())
        cm.capture_execution(state, result={
            "status": "completed",
            "duration_seconds": 42.0,
            "metrics": {"total_tests": 12, "tests_passed": 10},
            "report_files": {"dashboard.html": "/x/dashboard.html"},
            "artifacts_path": "/x/artifacts",
        })
        assert state.agent_state.execution_results["metrics"]["tests_passed"] == 10
        assert state.agent_state.execution_results["reports"]["dashboard.html"] == "/x/dashboard.html"

    def test_build_plan_via_context_manager(self):
        cm = get_context_manager()
        state = SimpleNamespace(
            agent_state=AgentState(
                original_user_prompt="Test dashboard",
                parsed_intent={"focus_areas": ["Dashboard"], "excluded_modules": ["Settings"]},
            ),
            execution_plan=None,
        )
        plan = cm.build_plan(state=state)
        assert plan.goal == "Generate and execute automated tests for: Dashboard"
        assert plan.execution_order

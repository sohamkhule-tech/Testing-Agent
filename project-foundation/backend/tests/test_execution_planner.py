"""
Execution Planner tests.

Verifies the user prompt → execution plan mapping: goal, tasks, execution
order, workflow scope, constraints, and success criteria.
"""

import pytest

from app.context.execution_planner import (
    STAGE_ORDER,
    ExecutionPlan,
    ExecutionPlanner,
    get_execution_planner,
)


def _sample_prompt_context() -> dict:
    return {
        "raw_text": "Focus on the dashboard and reports. Exclude settings.",
        "focus_areas": ["Dashboard", "Reports"],
        "excluded_modules": ["Settings"],
        "included_pages": [],
        "excluded_pages": [],
        "coverage_preferences": ["negative", "security"],
        "output_preferences": ["playwright"],
        "custom_instructions": "",
        "has_credentials": False,
    }


@pytest.mark.unit
class TestExecutionPlanner:
    def test_builds_linear_execution_order(self):
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test the dashboard",
            parsed_intent=_sample_prompt_context(),
            request_data={"target_application": {"base_url": "https://example.com"}},
        )

        assert plan.execution_order == STAGE_ORDER
        # tasks follow the same order
        assert [t.stage for t in plan.tasks] == STAGE_ORDER
        # task order numbers are 1-based sequential
        assert [t.order for t in plan.tasks] == list(range(1, len(STAGE_ORDER) + 1))

    def test_login_task_inserted_when_credentials_present(self):
        pc = _sample_prompt_context()
        pc["has_credentials"] = True
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test login",
            parsed_intent=pc,
            request_data={},
        )
        stages = [t.stage for t in plan.tasks]
        assert "login" in stages
        assert stages[0] == "login"

    def test_goal_from_focus_areas(self):
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Focus on Dashboard and Reports",
            parsed_intent=_sample_prompt_context(),
            request_data={"target_application": {"base_url": "https://example.com"}},
        )
        assert "Dashboard" in plan.goal
        assert "Reports" in plan.goal

    def test_goal_from_agent_state_when_provided(self):
        class FakeAgentState:
            execution_goal = "Verify billing flows"
            original_user_prompt = "Original prompt"
            parsed_intent = _sample_prompt_context()
            success_criteria = ["No payment failures"]

        planner = ExecutionPlanner()
        plan = planner.build(
            parsed_intent=_sample_prompt_context(),
            agent_state=FakeAgentState(),
        )
        assert plan.goal == "Verify billing flows"
        assert "No payment failures" in plan.success_criteria
        assert plan.source_prompt == "Original prompt"

    def test_constraints_include_scope_and_environment(self):
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test reports, exclude settings",
            parsed_intent=_sample_prompt_context(),
            request_data={
                "target_application": {"base_url": "https://example.com", "environment": "qa"}
            },
        )
        joined = "\n".join(plan.constraints)
        assert "Settings" in joined
        assert "negative" in joined
        assert "security" in joined
        assert "qa" in joined
        assert "https://example.com" in joined

    def test_success_criteria_present(self):
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test dashboard",
            parsed_intent=_sample_prompt_context(),
        )
        assert len(plan.success_criteria) >= 3
        assert any("test plan" in c.lower() for c in plan.success_criteria)

    def test_source_prompt_preserved(self):
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test the dashboard only",
            parsed_intent=_sample_prompt_context(),
        )
        assert plan.source_prompt == "Test the dashboard only"

    def test_serializable_round_trip(self):
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test dashboard",
            parsed_intent=_sample_prompt_context(),
        )
        data = plan.to_serializable()
        restored = ExecutionPlan(**data)
        assert restored == plan

    def test_empty_intent_produces_default_plan(self):
        planner = ExecutionPlanner()
        plan = planner.build(user_prompt="", parsed_intent=None, request_data=None)
        assert plan.execution_order == STAGE_ORDER
        assert plan.workflow_scope["environment"] == "staging"


@pytest.mark.unit
class TestExecutionPlannerSingleton:
    def test_singleton(self):
        assert get_execution_planner() is get_execution_planner()
        assert isinstance(get_execution_planner(), ExecutionPlanner)

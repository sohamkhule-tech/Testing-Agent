"""
AgentState schema tests.

Verifies the Phase 1 canonical state model: camelCase aliases, the full field
set, credential redaction, and serialisation round-trips.
"""

import pytest

from app.context.agent_state import AGENT_STATE_FIELDS, AgentState


@pytest.mark.unit
class TestAgentState:
    def test_camel_case_alias_and_snake_case_populate(self):
        """Both originalUserPrompt (alias) and original_user_prompt (name) populate the same field."""
        via_alias = AgentState(originalUserPrompt="Test login flow")
        assert via_alias.original_user_prompt == "Test login flow"

        via_name = AgentState(original_user_prompt="Test login flow")
        # Aliases are honoured in construction and camelCase serialisation
        assert via_name.original_user_prompt == "Test login flow"
        assert via_name.model_dump(by_alias=True)["originalUserPrompt"] == "Test login flow"

    def test_all_phase1_fields_present(self):
        """The 16 requirement fields must exist on the model."""
        state = AgentState(
            originalUserPrompt="prompt",
            parsedIntent={"focus_areas": ["Dashboard"]},
            executionGoal="Test dashboard",
            workflowScope={"environment": "staging"},
            includedModules=["Dashboard"],
            excludedModules=["Settings"],
            credentials={"username": "u", "password": "p"},
            priorities=["critical"],
            businessObjective="Protect revenue flows",
            inventory={"path": "contracts/inventory.json"},
            testPlan={"path": "contracts/test-plan.json"},
            approvedPlan={"review_decision": "approve"},
            generatedIR={"ir_path": "artifacts/ir/ir.json"},
            generatedTests={"project_path": "artifacts/generated-tests"},
            executionResults={"status": "completed"},
            artifacts={"run_id": "run-1"},
        )
        serialized = state.to_serializable(redact_credentials=False)
        for field in AGENT_STATE_FIELDS:
            assert field in serialized, f"missing field: {field}"

    def test_to_serializable_redacts_credentials_by_default(self):
        state = AgentState(credentials={"username": "u", "password": "p"})
        serialized = state.to_serializable()
        assert serialized["credentials"] == {}

        keep = state.to_serializable(redact_credentials=False)
        assert keep["credentials"] == {"username": "u", "password": "p"}

    def test_redacted_returns_deep_copy_without_credentials(self):
        state = AgentState(credentials={"username": "u", "password": "p"})
        redacted = state.redacted()
        assert redacted.credentials == {}
        # original untouched
        assert state.credentials == {"username": "u", "password": "p"}
        # no shared references to mutable nested data
        assert redacted.included_modules is not state.included_modules

    def test_round_trip_from_serializable(self):
        state = AgentState(
            originalUserPrompt="Original prompt",
            parsedIntent={"focus_areas": ["Dashboard"]},
            excludedModules=["Settings"],
        )
        data = state.to_serializable(redact_credentials=False)
        restored = AgentState.from_serializable(data)
        assert restored == state

    def test_unknown_extra_keys_ignored(self):
        state = AgentState(originalUserPrompt="x", totally_unknown=42)
        assert not hasattr(state, "totally_unknown")

    def test_defaults_are_empty(self):
        state = AgentState()
        assert state.included_modules == []
        assert state.excluded_modules == []
        assert state.parsed_intent == {}
        assert state.workflow_scope == {}
        assert state.artifacts == {}

"""
Regression tests for IR generation reliability.

Covers the failure modes observed in production (invalid enum values, null
required fields, malformed JSON) plus the schema-derived prompt, structured
output with fallback, deterministic retries, schema-safe repair, and semantic
refinement.
"""

import json
from uuid import uuid4

import pytest

from app.agents.ir_generation_agent import IRGenerationAgent
from app.config import get_settings
from app.core.ir.schema_renderer import SchemaRenderer
from app.core.ir.schema_repairer import SchemaAwareRepairer
from app.core.ir.validation_feedback import (
    ValidationFeedbackBuilder,
    pydantic_errors_to_feedback,
    render_validation_feedback,
)
from app.exceptions import AgentExecutionError, LLMProviderError
from app.schemas.ir import CodeGenerationIR
from app.schemas.review import ApprovedTestPlan, ReviewStatus
from tests.utils import MockLLMClient


def _valid_ir_dict() -> dict:
    """Return a schema-valid IR dict."""
    return {
        "metadata": {
            "generator": "IRGenerationAgent",
            "generated_at": "2024-01-01T00:00:00Z",
            "ir_version": "1.0.0",
            "validation_status": "pending",
            "total_pages": 1,
            "total_elements": 1,
            "total_flows": 1,
            "total_modules": 1,
        },
        "environment": {
            "base_url": "http://localhost:3000",
            "auth_required": False,
            "variables": {},
            "timeouts": {},
            "browsers": ["chromium"],
        },
        "pages": [
            {
                "page_id": "login-page",
                "name": "Login Page",
                "description": "User login page",
                "url_pattern": "/login",
                "elements": [
                    {
                        "id": "login-button",
                        "name": "Login Button",
                        "locator_strategy": "role",
                        "locator_value": "button:Login",
                        "description": "Submit button",
                        "fallback_locators": [],
                        "wait_for_visible": True,
                        "timeout": None,
                    }
                ],
                "page_load_selector": None,
                "requires_auth": False,
            }
        ],
        "modules": [
            {
                "module_id": "auth",
                "name": "Authentication",
                "description": "Authentication flows",
                "pages": ["login-page"],
                "flows": [
                    {
                        "flow_id": "login-success",
                        "name": "Successful Login",
                        "description": "User can log in",
                        "tags": [],
                        "steps": [
                            {
                                "step_order": 1,
                                "description": "Click login",
                                "navigation": None,
                                "actions": [
                                    {
                                        "action_type": "click",
                                        "element_id": "login-button",
                                        "value": None,
                                        "description": "Click login",
                                        "wait_before": None,
                                        "wait_after": None,
                                    }
                                ],
                                "assertions": [],
                                "wait_for_condition": None,
                            }
                        ],
                        "preconditions": [],
                        "postconditions": [],
                        "depends_on": [],
                        "timeout": None,
                        "priority": "high",
                    }
                ],
                "tags": [],
                "priority": "high",
                "requires_auth": False,
            }
        ],
        "dependencies": [],
        "common_elements": [],
        "common_flows": [],
        "retry_config": {},
        "parallel_config": {},
    }


def _approved_plan() -> ApprovedTestPlan:
    """Return a minimal approved test plan."""
    return ApprovedTestPlan(
        run_id=uuid4(),
        request_id=uuid4(),
        generated_at="2024-01-01T00:00:00Z",
        approved_at="2024-01-01T00:00:00Z",
        review_status=ReviewStatus.APPROVED,
        reviewer_name="tester",
        test_plan_data={"test_scenarios": [], "application_summary": {}},
    )


class TestSchemaRenderer:
    """Schema-derived representation tests."""

    def test_documents_all_enum_values(self):
        renderer = SchemaRenderer()
        doc = renderer.render_schema_documentation(CodeGenerationIR)

        assert "allowed: \"role\", \"label\", \"placeholder\", \"text\", \"testId\", \"css\", \"xpath\"" in doc
        assert "allowed: \"click\", \"fill\", \"select\", \"check\", \"uncheck\"" in doc
        assert "allowed: \"toBeVisible\", \"toBeHidden\", \"toBeEnabled\"" in doc
        assert '"title"' not in doc

    def test_json_example_is_schema_valid(self):
        renderer = SchemaRenderer()
        example = json.loads(renderer.render_json_example(CodeGenerationIR))

        ir = CodeGenerationIR.model_validate(example)

        assert isinstance(ir, CodeGenerationIR)
        assert len(ir.pages) >= 1
        assert len(ir.modules) >= 1

    def test_json_example_marks_required_fields(self):
        renderer = SchemaRenderer()
        example = json.loads(renderer.render_json_example(CodeGenerationIR))

        assert example["metadata"]["generator"].startswith("<")
        assert example["environment"]["base_url"].startswith("<")
        assert example["pages"][0]["elements"][0]["locator_strategy"] in {
            "role", "label", "placeholder", "text", "testId", "css", "xpath"
        }

    def test_system_prompt_bans_invented_enum_values(self):
        from app.core.ir.instruction_builder import InstructionBuilder

        system_prompt = InstructionBuilder().build_ir_system_prompt()

        assert "locator_strategy" in system_prompt
        assert "NEVER invent" in system_prompt
        assert "null" in system_prompt


class TestValidationFeedback:
    """Structured validation feedback tests."""

    def test_pydantic_null_required_feedback(self):
        bad = _valid_ir_dict()
        bad["modules"][0]["flows"][0]["steps"][0]["navigation"] = {
            "target": None,
            "wait_for_load": True,
            "wait_for_selector": None,
            "description": "go",
        }

        with pytest.raises(Exception) as exc_info:
            CodeGenerationIR.model_validate(bad)
        feedback = pydantic_errors_to_feedback(exc_info.value)

        paths = {item["path"] for item in feedback}
        assert any("navigation.target" in path for path in paths)
        assert any(item["error_type"] in ("string_type", "none_required") for item in feedback)
        assert any(item["received"] == "null" for item in feedback)
        assert all("received" in item for item in feedback)

    def test_pydantic_enum_feedback(self):
        bad = _valid_ir_dict()
        bad["pages"][0]["elements"][0]["locator_strategy"] = "title"

        with pytest.raises(Exception) as exc_info:
            CodeGenerationIR.model_validate(bad)
        feedback = pydantic_errors_to_feedback(exc_info.value)

        assert feedback
        assert feedback[0]["error_type"] == "enum"
        assert "role" in feedback[0]["expected"]

    def test_render_feedback_is_compact(self):
        feedback = [
            {
                "path": "modules[0].flows[0].steps[0].navigation.target",
                "error_type": "none_required",
                "expected": "non-null value",
                "received": "null",
                "message": "Input should be a valid string",
            }
        ]
        rendered = render_validation_feedback(feedback)

        assert "navigation.target" in rendered
        assert "expected non-null value" in rendered
        assert "received null" in rendered

    def test_builder_formats_non_pydantic_error(self):
        builder = ValidationFeedbackBuilder()
        feedback = builder.from_pydantic(ValueError("boom"))

        assert feedback[0]["error_type"] == "ValueError"


class TestSchemaAwareRepairer:
    """Schema-safe repair tests."""

    def test_fills_missing_optional_keys_from_schema(self):
        data = _valid_ir_dict()
        del data["common_elements"]
        del data["environment"]["variables"]
        del data["environment"]["timeouts"]

        SchemaAwareRepairer().repair(data)

        assert data["common_elements"] == []
        assert data["environment"]["variables"] == {}
        assert data["environment"]["timeouts"] == {}

    def test_never_fabricates_required_values(self):
        data = _valid_ir_dict()
        del data["metadata"]["generator"]

        repairer = SchemaAwareRepairer()
        repairer.repair(data)

        assert "generator" not in data["metadata"]

    def test_nested_defaults_are_filled(self):
        data = _valid_ir_dict()
        del data["pages"][0]["elements"]

        SchemaAwareRepairer().repair(data)

        assert data["pages"][0]["elements"] == []


class TestStructuredOutput:
    """Structured output mode and fallback tests."""

    @pytest.mark.asyncio
    async def test_requests_json_object_when_enabled(self):
        mock = MockLLMClient([json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)
        agent.run_id = None

        await agent._complete_and_parse_ir("generate", 5)

        assert mock.calls
        assert mock.calls[0].get("response_format") == {"type": "json_object"}

    @pytest.mark.asyncio
    async def test_raw_mode_when_disabled(self, monkeypatch):
        settings = get_settings()
        monkeypatch.setattr(settings.llm, "llm_structured_output_enabled", False)

        mock = MockLLMClient([json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)

        await agent._complete_and_parse_ir("generate", 5)

        assert mock.calls
        assert "response_format" not in mock.calls[0]

    @pytest.mark.asyncio
    async def test_falls_back_to_raw_on_provider_rejection(self):
        mock = MockLLMClient([json.dumps(_valid_ir_dict())])

        async def flaky_complete(prompt, system_prompt=None, **kwargs):
            mock.calls.append({"prompt": prompt, "system_prompt": system_prompt, **kwargs})
            mock.call_count += 1
            if mock.call_count == 1:
                raise LLMProviderError("The response_format parameter is not supported")
            return json.dumps(_valid_ir_dict())

        mock.complete = flaky_complete
        agent = IRGenerationAgent(mock)

        ir = await agent._complete_and_parse_ir("generate", 5)

        assert isinstance(ir, CodeGenerationIR)
        assert mock.call_count == 2
        assert "response_format" in mock.calls[0]
        assert "response_format" not in mock.calls[1]


class TestRetryDeterminism:
    """Deterministic retry behavior tests."""

    @pytest.mark.asyncio
    async def test_retries_include_validation_feedback(self):
        bad = _valid_ir_dict()
        bad["pages"][0]["elements"][0]["locator_strategy"] = "title"

        mock = MockLLMClient([json.dumps(bad), json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)

        ir = await agent._complete_and_parse_ir("generate", 5)

        assert isinstance(ir, CodeGenerationIR)
        assert mock.call_count == 2
        assert "locator_strategy" in mock.calls[1]["prompt"]
        assert "Previous attempt was rejected" in mock.calls[1]["prompt"]

    @pytest.mark.asyncio
    async def test_null_required_field_feedback_retry(self):
        bad = _valid_ir_dict()
        bad["modules"][0]["flows"][0]["steps"][0]["navigation"] = {
            "target": None,
            "wait_for_load": True,
            "wait_for_selector": None,
            "description": "go",
        }

        mock = MockLLMClient([json.dumps(bad), json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)

        ir = await agent._complete_and_parse_ir("generate", 5)

        assert isinstance(ir, CodeGenerationIR)
        assert mock.call_count == 2
        assert "navigation.target" in mock.calls[1]["prompt"]

    @pytest.mark.asyncio
    async def test_temperature_is_stable_across_retries(self):
        bad = _valid_ir_dict()
        bad["pages"][0]["elements"][0]["locator_strategy"] = "title"

        mock = MockLLMClient([json.dumps(bad), json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)

        await agent._complete_and_parse_ir("generate", 5)

        temps = {call.get("temperature") for call in mock.calls}
        assert temps == {0.3}

    @pytest.mark.asyncio
    async def test_system_prompt_sent_on_generation(self):
        mock = MockLLMClient([json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)

        await agent._complete_and_parse_ir("generate", 5)

        assert mock.calls[0]["system_prompt"]
        assert "locator_strategy" in mock.calls[0]["system_prompt"]

    @pytest.mark.asyncio
    async def test_exhausts_retries_and_raises(self):
        bad = _valid_ir_dict()
        bad["pages"][0]["elements"][0]["locator_strategy"] = "title"

        mock = MockLLMClient([json.dumps(bad)])
        agent = IRGenerationAgent(mock)

        with pytest.raises(AgentExecutionError):
            await agent._complete_and_parse_ir("generate", 5)

        assert mock.call_count == 3

    @pytest.mark.asyncio
    async def test_recovers_from_malformed_json(self):
        mock = MockLLMClient(["not valid json", json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock)

        ir = await agent._complete_and_parse_ir("generate", 5)

        assert isinstance(ir, CodeGenerationIR)
        assert mock.call_count == 2


class TestExecuteLoop:
    """Execute-level semantic refinement tests."""

    @pytest.mark.asyncio
    async def test_semantic_refinement_reaches_valid_ir(self):
        semantically_bad = _valid_ir_dict()
        semantically_bad["modules"][0]["flows"][0]["steps"][0]["actions"][0]["element_id"] = "does-not-exist"

        mock = MockLLMClient([json.dumps(semantically_bad), json.dumps(_valid_ir_dict())])
        agent = IRGenerationAgent(mock, max_refinement_attempts=3)

        result = await agent.execute({
            "approved_test_plan": _approved_plan(),
            "base_url": "http://localhost:3000",
        })

        assert result["success"] is True
        assert result["refinement_attempts"] >= 1
        assert result["ir"].modules[0].flows[0].steps[0].actions[0].element_id == "login-button"

    @pytest.mark.asyncio
    async def test_semantic_refinement_exhaustion_raises(self):
        semantically_bad = _valid_ir_dict()
        semantically_bad["modules"][0]["flows"][0]["steps"][0]["actions"][0]["element_id"] = "does-not-exist"

        mock = MockLLMClient([json.dumps(semantically_bad)])
        agent = IRGenerationAgent(mock, max_refinement_attempts=2)

        with pytest.raises(AgentExecutionError):
            await agent.execute({
                "approved_test_plan": _approved_plan(),
                "base_url": "http://localhost:3000",
            })

        assert mock.call_count >= 1

    @pytest.mark.asyncio
    async def test_parse_failure_propagates_to_execute(self):
        bad = _valid_ir_dict()
        bad["pages"][0]["elements"][0]["locator_strategy"] = "title"

        mock = MockLLMClient([json.dumps(bad)])
        agent = IRGenerationAgent(mock)

        with pytest.raises(AgentExecutionError):
            await agent.execute({
                "approved_test_plan": _approved_plan(),
                "base_url": "http://localhost:3000",
            })


pytestmark = pytest.mark.unit

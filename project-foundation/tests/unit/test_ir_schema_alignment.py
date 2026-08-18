"""
Tests for IR Generation Schema Alignment

Verifies that:
1. The IR generation prompt includes all required fields
2. Pre-validation catches missing fields before Pydantic
3. Auto-repair fixes common issues
4. LLM-based repair works for validation failures
5. Various LLM responses are handled correctly
"""

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.agents.ir_generation_agent import IRGenerationAgent
from app.core.ir.ir_pre_validator import IRAutoRepairer, IRPreValidator
from app.core.ir.instruction_builder import InstructionBuilder
from app.schemas.ir import CodeGenerationIR


class TestPromptCompleteness:
    """Test that the IR generation prompt includes all required schema fields."""

    def test_prompt_includes_metadata_schema(self):
        """Prompt must include complete metadata schema."""
        builder = InstructionBuilder()
        prompt = builder.build_ir_generation_instructions()
        
        # Check metadata fields are documented
        assert "metadata" in prompt.lower()
        assert "generator" in prompt
        assert "IRGenerationAgent" in prompt
        assert "ir_version" in prompt
        assert "generated_at" in prompt
        assert "validation_status" in prompt

    def test_prompt_includes_environment_schema(self):
        """Prompt must include complete environment schema."""
        builder = InstructionBuilder()
        prompt = builder.build_ir_generation_instructions()
        
        assert "environment" in prompt.lower()
        assert "base_url" in prompt
        assert "auth_required" in prompt
        assert "browsers" in prompt

    def test_prompt_includes_dependency_schema(self):
        """Prompt must include complete dependency schema with all required fields."""
        builder = InstructionBuilder()
        prompt = builder.build_ir_generation_instructions()
        
        assert "dependencies" in prompt.lower()
        assert "source_id" in prompt
        assert "target_id" in prompt
        assert "dependency_type" in prompt

    def test_prompt_includes_complete_example(self):
        """Prompt must include a complete example with all sections."""
        builder = InstructionBuilder()
        prompt = builder.build_ir_generation_instructions()
        
        # Extract JSON from prompt
        import re
        json_blocks = re.findall(r'```json\n(.*?)\n```', prompt, re.DOTALL)
        
        # Should have at least one complete example
        assert len(json_blocks) > 0
        
        # Find the complete example (longest one)
        complete_example = max(json_blocks, key=len)
        
        # Parse it
        example_data = json.loads(complete_example)
        
        # Verify all required top-level keys
        assert "metadata" in example_data
        assert "environment" in example_data
        assert "pages" in example_data
        assert "modules" in example_data
        assert "dependencies" in example_data
        
        # Verify metadata structure
        assert "generator" in example_data["metadata"]
        assert example_data["metadata"]["generator"] == "IRGenerationAgent"
        
        # Verify dependency structure
        if len(example_data["dependencies"]) > 0:
            dep = example_data["dependencies"][0]
            assert "source_id" in dep
            assert "target_id" in dep
            assert "dependency_type" in dep


class TestPreValidation:
    """Test pre-validation catches issues before Pydantic."""

    def test_prevalidator_catches_missing_metadata(self):
        """Pre-validator must catch missing metadata fields."""
        validator = IRPreValidator()
        
        ir_data = {
            "metadata": {},  # Missing required fields
            "environment": {"base_url": "http://test.com", "auth_required": False},
            "pages": [],
            "modules": [],
            "dependencies": []
        }
        
        is_valid, errors, _ = validator.validate(ir_data)
        
        assert not is_valid
        assert any("metadata.generator" in e for e in errors)
        assert any("metadata.ir_version" in e for e in errors)

    def test_prevalidator_catches_missing_dependency_fields(self):
        """Pre-validator must catch missing dependency fields."""
        validator = IRPreValidator()
        
        ir_data = {
            "metadata": {"generator": "IRGenerationAgent", "ir_version": "1.0.0"},
            "environment": {"base_url": "http://test.com", "auth_required": False},
            "pages": [],
            "modules": [],
            "dependencies": [
                {"source_id": "flow1"}  # Missing target_id and dependency_type
            ]
        }
        
        is_valid, errors, _ = validator.validate(ir_data)
        
        assert not is_valid
        assert any("dependencies[0].target_id" in e for e in errors)
        assert any("dependencies[0].dependency_type" in e for e in errors)

    def test_prevalidator_catches_null_required_fields(self):
        """Pre-validator must catch null values in required fields."""
        validator = IRPreValidator()
        
        ir_data = {
            "metadata": {"generator": None, "ir_version": "1.0.0"},  # Null generator
            "environment": {"base_url": "http://test.com", "auth_required": False},
            "pages": [],
            "modules": [],
            "dependencies": []
        }
        
        is_valid, errors, _ = validator.validate(ir_data)
        
        assert not is_valid
        assert any("metadata.generator is null" in e for e in errors)


class TestAutoRepair:
    """Test auto-repair fixes common issues."""

    def test_autorepair_adds_missing_metadata(self):
        """Auto-repairer must add missing metadata fields."""
        repairer = IRAutoRepairer()
        
        ir_data = {
            "metadata": {},
            "environment": {"base_url": "http://test.com"},
            "pages": [],
            "modules": [],
            "dependencies": []
        }
        
        repaired = repairer.repair(ir_data)
        
        assert repaired["metadata"]["generator"] == "IRGenerationAgent"
        assert repaired["metadata"]["ir_version"] == "1.0.0"
        assert "generated_at" in repaired["metadata"]
        assert "validation_status" in repaired["metadata"]

    def test_autorepair_creates_missing_arrays(self):
        """Auto-repairer must create missing arrays."""
        repairer = IRAutoRepairer()
        
        ir_data = {
            "metadata": {"generator": "IRGenerationAgent", "ir_version": "1.0.0"},
            "environment": {"base_url": "http://test.com"}
            # Missing pages, modules, dependencies, etc.
        }
        
        repaired = repairer.repair(ir_data)
        
        assert isinstance(repaired.get("pages"), list)
        assert isinstance(repaired.get("modules"), list)
        assert isinstance(repaired.get("dependencies"), list)
        assert isinstance(repaired.get("common_elements"), list)
        assert isinstance(repaired.get("common_flows"), list)

    def test_autorepair_removes_invalid_dependencies(self):
        """Auto-repairer must remove incomplete dependencies."""
        repairer = IRAutoRepairer()
        
        ir_data = {
            "metadata": {"generator": "IRGenerationAgent", "ir_version": "1.0.0"},
            "environment": {"base_url": "http://test.com", "auth_required": False},
            "pages": [],
            "modules": [],
            "dependencies": [
                {"source_id": "flow1", "target_id": "flow2", "dependency_type": "prerequisite"},  # Valid
                {"source_id": "flow3"},  # Invalid - missing required fields
                "not_an_object",  # Invalid - not even an object
            ]
        }
        
        repaired = repairer.repair(ir_data)
        
        # Should only keep the valid dependency
        assert len(repaired["dependencies"]) == 1
        assert repaired["dependencies"][0]["source_id"] == "flow1"


class TestIRGenerationAgentParsing:
    """Test IR generation agent parsing with various responses."""

    @pytest.mark.asyncio
    async def test_agent_parses_valid_ir(self):
        """Agent should successfully parse valid IR."""
        mock_llm = AsyncMock()
        agent = IRGenerationAgent(mock_llm)
        
        valid_ir_json = json.dumps({
            "metadata": {
                "generator": "IRGenerationAgent",
                "generated_at": "2024-01-01T00:00:00Z",
                "ir_version": "1.0.0",
                "validation_status": "pending",
                "total_pages": 0,
                "total_elements": 0,
                "total_flows": 0,
                "total_modules": 0
            },
            "environment": {
                "base_url": "http://localhost:3000",
                "auth_required": False,
                "variables": {},
                "timeouts": {},
                "browsers": ["chromium"]
            },
            "pages": [],
            "modules": [],
            "dependencies": [],
            "common_elements": [],
            "common_flows": [],
            "retry_config": {},
            "parallel_config": {}
        })
        
        ir = await agent._parse_ir_response(valid_ir_json)
        
        assert isinstance(ir, CodeGenerationIR)
        assert ir.metadata.generator == "IRGenerationAgent"

    @pytest.mark.asyncio
    async def test_agent_recovers_from_transient_bad_json(self):
        """Regression: one malformed JSON response must not fail IR generation.

        Mirrors the observed run where mistral-medium-3-5 emitted invalid JSON
        ("Expecting ',' delimiter") on a large IR generation. The agent must
        regenerate instead of hard-failing.
        """
        mock_llm = AsyncMock()
        mock_llm.model = "test-model"
        mock_llm.default_max_tokens = 4096
        valid_ir_json = json.dumps({
            "metadata": {
                "generator": "IRGenerationAgent",
                "generated_at": "2024-01-01T00:00:00Z",
                "ir_version": "1.0.0",
                "validation_status": "pending",
                "total_pages": 0,
                "total_elements": 0,
                "total_flows": 0,
                "total_modules": 0,
            },
            "environment": {
                "base_url": "http://localhost:3000",
                "auth_required": False,
                "variables": {},
                "timeouts": {},
                "browsers": ["chromium"],
            },
            "pages": [],
            "modules": [],
            "dependencies": [],
            "common_elements": [],
            "common_flows": [],
            "retry_config": {},
            "parallel_config": {},
        })
        mock_llm.complete = AsyncMock(side_effect=[
            "not valid json at all",
            valid_ir_json,
        ])
        agent = IRGenerationAgent(mock_llm)

        ir = await agent._complete_and_parse_ir("generate ir", 10)

        assert isinstance(ir, CodeGenerationIR)
        assert mock_llm.complete.call_count == 2

    @pytest.mark.asyncio
    async def test_agent_repairs_missing_metadata(self):
        """Agent should auto-repair missing metadata fields."""
        mock_llm = AsyncMock()
        agent = IRGenerationAgent(mock_llm)
        
        # IR missing metadata.generator
        incomplete_ir_json = json.dumps({
            "metadata": {
                "ir_version": "1.0.0"
                # Missing generator!
            },
            "environment": {
                "base_url": "http://localhost:3000",
                "auth_required": False,
                "browsers": ["chromium"]
            },
            "pages": [],
            "modules": [],
            "dependencies": []
        })
        
        ir = await agent._parse_ir_response(incomplete_ir_json)
        
        # Should be repaired
        assert ir.metadata.generator == "IRGenerationAgent"

    @pytest.mark.asyncio
    async def test_agent_handles_markdown_wrapped_json(self):
        """Agent should extract JSON from markdown code fences."""
        mock_llm = AsyncMock()
        agent = IRGenerationAgent(mock_llm)
        
        response_with_markdown = """Here is the IR:

```json
{
  "metadata": {
    "generator": "IRGenerationAgent",
    "ir_version": "1.0.0"
  },
  "environment": {
    "base_url": "http://localhost:3000",
    "auth_required": false,
    "browsers": ["chromium"]
  },
  "pages": [],
  "modules": [],
  "dependencies": []
}
```

This IR includes all required fields."""
        
        ir = await agent._parse_ir_response(response_with_markdown)
        
        assert isinstance(ir, CodeGenerationIR)


class TestSchemaEvolution:
    """Test that schema changes are caught early."""

    def test_schema_documentation_matches_code(self):
        """
        Verify that any new required field in CodeGenerationIR is documented in prompts.
        
        This test will fail if someone adds a required field to the schema
        without updating the prompt template.
        """
        from app.schemas.ir import MetadataIR, EnvironmentIR, DependencyIR
        import inspect
        
        # Get required fields from Pydantic models
        metadata_fields = {
            field: info for field, info in MetadataIR.__fields__.items()
            if info.is_required()
        }
        
        env_fields = {
            field: info for field, info in EnvironmentIR.__fields__.items()
            if info.is_required()
        }
        
        dep_fields = {
            field: info for field, info in DependencyIR.__fields__.items()
            if info.is_required()
        }
        
        # Get prompt
        builder = InstructionBuilder()
        prompt = builder.build_ir_generation_instructions()
        
        # Check all required fields are documented
        for field in metadata_fields.keys():
            assert field in prompt, f"Required field 'metadata.{field}' not documented in prompt"
        
        for field in env_fields.keys():
            assert field in prompt, f"Required field 'environment.{field}' not documented in prompt"
        
        for field in dep_fields.keys():
            assert field in prompt, f"Required field 'dependencies[].{field}' not documented in prompt"


class TestErrorReporting:
    """Test that validation errors are clearly reported."""

    @pytest.mark.asyncio
    async def test_pydantic_validation_error_formatted_clearly(self):
        """Validation errors should be formatted in a readable way."""
        from app.exceptions import AgentExecutionError
        
        mock_llm = AsyncMock()
        agent = IRGenerationAgent(mock_llm)
        
        # IR with structure that can't be auto-repaired (wrong types that break Pydantic)
        invalid_ir_json = json.dumps({
            "metadata": {
                "generator": "IRGenerationAgent",
                "ir_version": "1.0.0",
                "total_pages": "not_a_number"  # Wrong type - string instead of int
            },
            "environment": {
                "base_url": "http://test.com",
                "auth_required": "yes"  # Wrong type - string instead of bool
            },
            "pages": [],
            "modules": [],
            "dependencies": []
        })
        
        try:
            await agent._parse_ir_response(invalid_ir_json)
            pytest.fail("Should have raised AgentExecutionError")
        except AgentExecutionError as e:
            error_msg = str(e)
            
            # Error message should be helpful
            assert "validation" in error_msg.lower() or "pydantic" in error_msg.lower()


# Mark all tests as unit tests
pytestmark = pytest.mark.unit

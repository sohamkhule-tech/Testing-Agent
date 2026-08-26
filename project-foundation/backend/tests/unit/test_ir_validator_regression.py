"""
Regression Tests for IR Validator AttributeError Fix

Tests to ensure the generation_id AttributeError bug never returns.

Bug History:
- Code Generation was failing with: AttributeError: 'MetadataIR' object has no attribute 'generation_id'
- Root cause: IRValidator.validate() tried to access ir.metadata.generation_id
- Fix: Removed reference to non-existent field, added defensive validation
"""

import pytest
from datetime import datetime

from app.core.ir.ir_validator import IRValidator
from app.schemas.ir import (
    CodeGenerationIR,
    MetadataIR,
    EnvironmentIR,
    PageIR,
    ModuleIR,
    ElementIR,
    TestFlowIR,
    FlowStepIR,
    DependencyIR,
)


class TestIRValidatorMetadataAccess:
    """Test that IRValidator correctly accesses metadata fields."""

    def test_validator_does_not_access_generation_id(self):
        """
        REGRESSION TEST: Ensure validator never tries to access generation_id.
        
        This was the original bug - validator tried to access a field that
        doesn't exist in MetadataIR schema.
        """
        # Create minimal valid IR
        ir = CodeGenerationIR(
            metadata=MetadataIR(
                generator="IRGenerationAgent",
                ir_version="1.0.0",
            ),
            environment=EnvironmentIR(
                base_url="http://localhost:3000",
                auth_required=False,
            ),
            pages=[],
            modules=[],
            dependencies=[],
        )

        # This should NOT raise AttributeError
        validator = IRValidator()
        result = validator.validate(ir)

        # Validation should complete without errors
        assert result is not None

    def test_validator_with_complete_metadata(self):
        """Test validator with all metadata fields populated."""
        ir = CodeGenerationIR(
            metadata=MetadataIR(
                generator="IRGenerationAgent",
                generated_at=datetime.utcnow(),
                ir_version="1.0.0",
                source_test_plan="/path/to/plan.json",
                model_used="deepseek-v4-flash",
                total_pages=2,
                total_elements=5,
                total_flows=3,
                total_modules=1,
                validation_status="pending",
            ),
            environment=EnvironmentIR(
                base_url="http://localhost:3000",
                auth_required=False,
            ),
            pages=[],
            modules=[],
            dependencies=[],
        )

        validator = IRValidator()
        
        # Should NOT raise AttributeError
        result = validator.validate(ir)

        # Validator should complete successfully (even if it finds issues in empty IR)
        assert result is not None

    def test_metadata_fields_exist(self):
        """Verify MetadataIR has expected fields and NOT generation_id."""
        metadata = MetadataIR(
            generator="test",
            ir_version="1.0.0",
        )

        # These should exist
        assert hasattr(metadata, "generator")
        assert hasattr(metadata, "ir_version")
        assert hasattr(metadata, "generated_at")
        assert hasattr(metadata, "source_test_plan")
        assert hasattr(metadata, "model_used")
        assert hasattr(metadata, "total_pages")
        assert hasattr(metadata, "total_elements")
        assert hasattr(metadata, "total_flows")
        assert hasattr(metadata, "total_modules")
        assert hasattr(metadata, "validation_status")

        # This should NOT exist (was the bug)
        assert not hasattr(metadata, "generation_id")


class TestIRValidatorDefensiveValidation:
    """Test defensive validation prevents crashes."""

    def test_validator_rejects_none_ir(self):
        """Validator should reject None IR with clear error."""
        validator = IRValidator()

        with pytest.raises(ValueError, match="IR object is None or empty"):
            validator.validate(None)

    def test_validator_rejects_missing_metadata(self):
        """Validator should reject IR without metadata."""
        # Create IR with None metadata (bypassing Pydantic)
        ir = CodeGenerationIR(
            metadata=MetadataIR(generator="test", ir_version="1.0.0"),
            environment=EnvironmentIR(base_url="http://test.com", auth_required=False),
            pages=[],
            modules=[],
            dependencies=[],
        )
        # Force None metadata
        ir.metadata = None

        validator = IRValidator()

        with pytest.raises(ValueError, match="IR metadata is missing"):
            validator.validate(ir)

    def test_validator_checks_required_fields(self):
        """Validator should check required metadata fields exist."""
        # Create metadata without required fields
        class FakeMetadata:
            pass

        ir = CodeGenerationIR(
            metadata=MetadataIR(generator="test", ir_version="1.0.0"),
            environment=EnvironmentIR(base_url="http://test.com", auth_required=False),
            pages=[],
            modules=[],
            dependencies=[],
        )
        # Replace with fake metadata missing required fields
        ir.metadata = FakeMetadata()

        validator = IRValidator()

        with pytest.raises(ValueError, match="missing required fields"):
            validator.validate(ir)


class TestIRValidatorWithRealWorkflow:
    """Test validator with realistic IR structures."""

    def test_validator_with_complete_ir(self):
        """Test validator with complete IR including pages, modules, flows."""
        ir = CodeGenerationIR(
            metadata=MetadataIR(
                generator="IRGenerationAgent",
                ir_version="1.0.0",
                total_pages=1,
                total_modules=1,
                total_flows=1,
            ),
            environment=EnvironmentIR(
                base_url="http://localhost:3000",
                auth_required=False,
                browsers=["chromium"],
            ),
            pages=[
                PageIR(
                    page_id="login-page",
                    name="Login Page",
                    description="User login page",
                    elements=[
                        ElementIR(
                            id="username-input",
                            name="Username Input",
                            locator_strategy="label",
                            locator_value="Username",
                        ),
                        ElementIR(
                            id="password-input",
                            name="Password Input",
                            locator_strategy="label",
                            locator_value="Password",
                        ),
                        ElementIR(
                            id="login-button",
                            name="Login Button",
                            locator_strategy="role",
                            locator_value="button:Login",
                        ),
                    ],
                ),
            ],
            modules=[
                ModuleIR(
                    module_id="auth",
                    name="Authentication",
                    description="Auth tests",
                    pages=["login-page"],
                    flows=[
                        TestFlowIR(
                            flow_id="login-success",
                            name="Successful Login",
                            description="User logs in",
                            steps=[
                                FlowStepIR(
                                    step_order=1,
                                    description="Navigate to login",
                                ),
                            ],
                        ),
                    ],
                ),
            ],
            dependencies=[],
        )

        validator = IRValidator()
        
        # Should NOT raise AttributeError
        result = validator.validate(ir)

        # Validator should complete successfully
        assert result is not None

    def test_validator_after_llm_generation(self):
        """
        Simulate the exact scenario where the bug occurred:
        IR generated by LLM, pre-validated, auto-repaired, then validated.
        """
        # This is the IR structure after LLM generation and pre-validation
        ir = CodeGenerationIR(
            metadata=MetadataIR(
                generator="IRGenerationAgent",  # Added by auto-repair
                generated_at=datetime.utcnow(),  # Added by auto-repair
                ir_version="1.0.0",  # Added by auto-repair
                validation_status="pending",  # Added by auto-repair
                total_pages=0,
                total_elements=0,
                total_flows=0,
                total_modules=0,
            ),
            environment=EnvironmentIR(
                base_url="http://localhost:3000",
                auth_required=False,
                browsers=["chromium"],
            ),
            pages=[],
            modules=[],
            dependencies=[],
            common_elements=[],
            common_flows=[],
            retry_config={},
            parallel_config={},
        )

        # This is where the bug occurred - validator.validate()
        validator = IRValidator()

        # Should NOT raise AttributeError about generation_id
        try:
            result = validator.validate(ir)
            assert result is not None
        except AttributeError as e:
            if "generation_id" in str(e):
                pytest.fail(f"REGRESSION: generation_id AttributeError returned: {e}")
            raise


class TestMetadataIRSchemaStability:
    """Test to detect if MetadataIR schema changes break things."""

    def test_metadata_ir_field_list(self):
        """
        Document expected MetadataIR fields.
        
        If this test fails, someone changed MetadataIR schema.
        Review all code that accesses metadata fields.
        """
        expected_fields = {
            "generator",
            "generated_at",
            "ir_version",
            "source_test_plan",
            "model_used",
            "total_pages",
            "total_elements",
            "total_flows",
            "total_modules",
            "validation_status",
        }

        metadata = MetadataIR(generator="test", ir_version="1.0.0")
        actual_fields = set(metadata.model_fields.keys())

        assert actual_fields == expected_fields, (
            f"MetadataIR schema changed!\n"
            f"Expected: {expected_fields}\n"
            f"Actual: {actual_fields}\n"
            f"Diff: {actual_fields.symmetric_difference(expected_fields)}\n"
            f"Review all code accessing metadata fields!"
        )

    def test_no_generation_id_field(self):
        """Ensure generation_id was never added back to schema."""
        metadata = MetadataIR(generator="test", ir_version="1.0.0")

        # This field should NEVER exist
        assert "generation_id" not in metadata.model_fields
        assert not hasattr(metadata, "generation_id")


# Mark all tests as unit tests
pytestmark = pytest.mark.unit

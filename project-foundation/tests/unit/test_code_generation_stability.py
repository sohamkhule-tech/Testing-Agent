"""
Tests for Code Generation Workflow Stability

These tests verify that:
1. All required imports are present
2. Code generation can execute successfully
3. Execution never runs after code generation failure
4. Missing dependencies are caught at startup, not runtime
"""

import asyncio
import importlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.constants import RunStatus
from app.graph import NodeResult
from app.validation.startup_checks import (
    StartupValidationError,
    run_all_startup_checks,
    validate_critical_imports_in_workflows,
    validate_required_imports,
)
from app.workflows.trigger_workflow import (
    PlatformWorkflowState,
    code_generation_node,
    execution_node,
)


class TestRequiredImports:
    """Test that all required imports are present and detected."""

    def test_asyncio_imported_in_trigger_workflow(self):
        """Verify asyncio is imported in trigger_workflow.py."""
        from app.workflows import trigger_workflow
        
        assert hasattr(trigger_workflow, "asyncio"), (
            "trigger_workflow.py must import asyncio for timeout handling"
        )

    def test_asyncio_imported_in_trigger_routes(self):
        """Verify asyncio is imported in trigger.py routes."""
        from app.api.routes import trigger
        
        assert hasattr(trigger, "asyncio"), (
            "trigger.py must import asyncio for background task creation"
        )

    def test_all_required_imports_available(self):
        """Verify all critical dependencies can be imported."""
        # This should not raise
        validate_required_imports()

    def test_critical_workflow_imports_validated(self):
        """Verify critical workflow imports are detected."""
        # This should not raise if imports are correct
        validate_critical_imports_in_workflows()


class TestStartupValidation:
    """Test startup validation catches missing imports."""

    def test_startup_checks_pass_with_valid_env(self):
        """Startup checks should pass in a properly configured environment."""
        # This should not raise
        run_all_startup_checks()

    def test_missing_import_detected_at_startup(self):
        """Test that missing imports would be caught at startup."""
        # Temporarily hide a module to simulate missing import
        import sys
        
        original_asyncio = sys.modules.get("asyncio")
        
        try:
            # Remove asyncio from sys.modules
            if "asyncio" in sys.modules:
                del sys.modules["asyncio"]
            
            # This should raise because asyncio is "missing"
            with pytest.raises(StartupValidationError, match="asyncio"):
                validate_required_imports()
        finally:
            # Restore asyncio
            if original_asyncio:
                sys.modules["asyncio"] = original_asyncio


class TestCodeGenerationNode:
    """Test code generation node behavior."""

    @pytest.mark.asyncio
    async def test_code_generation_timeout_uses_asyncio(self):
        """Verify code generation node uses asyncio.wait_for for timeout."""
        from app.workflows import trigger_workflow
        
        # Read the source code and verify asyncio.wait_for is used
        import inspect
        source = inspect.getsource(trigger_workflow.code_generation_node)
        
        assert "asyncio.wait_for" in source, (
            "code_generation_node must use asyncio.wait_for for global timeout"
        )
        assert "asyncio.TimeoutError" in source, (
            "code_generation_node must handle asyncio.TimeoutError"
        )

    @pytest.mark.asyncio
    async def test_code_generation_node_marks_failure_on_error(self):
        """Verify code generation node marks state as failed on error."""
        # Create a minimal state
        state = PlatformWorkflowState(
            run_id=str(uuid4()),
            status=RunStatus.RUNNING,
            workspace_path="/tmp/test",
            metadata={"code_generation_agent": None},  # Will cause error
        )
        
        # Execute node (should fail due to None agent)
        result_state = await code_generation_node(state)
        
        # Verify failure was recorded
        assert result_state.status == RunStatus.FAILED or len(result_state.errors) > 0
        assert "code_generation" in result_state.node_results
        node_result = result_state.node_results["code_generation"]
        assert node_result.status == "failed"


class TestExecutionNodeFailFast:
    """Test that execution node fails fast if code generation failed."""

    @pytest.mark.asyncio
    async def test_execution_fails_if_code_generation_incomplete(self):
        """Execution must fail if code_generation stage did not complete."""
        state = PlatformWorkflowState(
            run_id=str(uuid4()),
            status=RunStatus.RUNNING,
            workspace_path="/tmp/test",
            # code_generation NOT in completed_nodes
            completed_nodes=["trigger", "crawler", "inventory_aggregator", "test_design"],
        )
        
        # Execute execution node
        result_state = await execution_node(state)
        
        # Must fail with clear error
        assert result_state.status == RunStatus.FAILED or len(result_state.errors) > 0
        error_msg = result_state.errors[-1] if result_state.errors else ""
        assert "code generation" in error_msg.lower()
        assert "did not complete" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_execution_fails_if_code_generation_failed(self):
        """Execution must fail if code_generation completed with failure status."""
        state = PlatformWorkflowState(
            run_id=str(uuid4()),
            status=RunStatus.RUNNING,
            workspace_path="/tmp/test",
            completed_nodes=["trigger", "crawler", "inventory_aggregator", "test_design", "code_generation"],
        )
        
        # Mark code generation as failed
        state.node_results["code_generation"] = NodeResult(
            node_name="code_generation",
            status="failed",
            data={},
            error="Code generation failed",
        )
        
        # Execute execution node
        result_state = await execution_node(state)
        
        # Must fail with clear error
        assert result_state.status == RunStatus.FAILED or len(result_state.errors) > 0
        error_msg = result_state.errors[-1] if result_state.errors else ""
        assert "code generation failed" in error_msg.lower()

    @pytest.mark.asyncio
    async def test_execution_fails_if_no_project_path(self):
        """Execution must fail if generated_project_path is missing."""
        state = PlatformWorkflowState(
            run_id=str(uuid4()),
            status=RunStatus.RUNNING,
            workspace_path="/tmp/test",
            completed_nodes=["trigger", "crawler", "inventory_aggregator", "test_design", "code_generation"],
            generated_project_path=None,  # Missing!
        )
        
        # Mark code generation as completed successfully
        state.node_results["code_generation"] = NodeResult(
            node_name="code_generation",
            status="completed",
            data={"status": "completed"},
        )
        
        # Execute execution node
        result_state = await execution_node(state)
        
        # Must fail
        assert result_state.status == RunStatus.FAILED or len(result_state.errors) > 0


class TestWorkflowStageOrdering:
    """Test that workflow stages execute in correct order with proper dependencies."""

    @pytest.mark.asyncio
    async def test_execution_requires_code_generation_success(self):
        """Integration test: Execution cannot proceed without successful code generation."""
        # This is tested by the fail-fast checks above, but worth documenting
        # as a critical architectural requirement
        
        # Create state with failed code generation
        state = PlatformWorkflowState(
            run_id=str(uuid4()),
            status=RunStatus.RUNNING,
            workspace_path="/tmp/test",
            completed_nodes=["code_generation"],  # Marked complete
        )
        
        # But with failure status
        state.node_results["code_generation"] = NodeResult(
            node_name="code_generation",
            status="failed",
            data={},
            error="Test error",
        )
        
        # Execution must refuse to proceed
        result = await execution_node(state)
        assert result.status == RunStatus.FAILED or len(result.errors) > 0


class TestAsyncioUsage:
    """Test proper asyncio usage patterns."""

    def test_asyncio_wait_for_in_code_generation(self):
        """Verify asyncio.wait_for is used for timeout enforcement."""
        from app.workflows import trigger_workflow
        import inspect
        
        source = inspect.getsource(trigger_workflow.code_generation_node)
        
        # Must use asyncio.wait_for
        assert "asyncio.wait_for" in source
        
        # Must have timeout parameter
        assert "timeout=" in source

    def test_asyncio_create_task_in_trigger_routes(self):
        """Verify asyncio.create_task is used for background workflows."""
        from app.api.routes import trigger
        import inspect
        
        source = inspect.getsource(trigger)
        
        # Must use asyncio.create_task for background tasks
        assert "asyncio.create_task" in source
        
        # Should have done callbacks for error handling
        assert "add_done_callback" in source or "done_callback" in source


class TestRuntimeErrorPrevention:
    """Test that runtime NameErrors are prevented."""

    def test_no_undefined_asyncio_references(self):
        """Verify no code references asyncio without importing it."""
        # Check key files
        files_to_check = [
            "app/workflows/trigger_workflow.py",
            "app/api/routes/trigger.py",
        ]
        
        project_root = Path(__file__).parent.parent
        
        for file_path in files_to_check:
            full_path = project_root / file_path
            if not full_path.exists():
                continue
                
            content = full_path.read_text(encoding="utf-8")
            
            # If file uses asyncio, it must import it
            if "asyncio." in content or "asyncio(" in content:
                assert "import asyncio" in content, (
                    f"{file_path} uses asyncio but does not import it"
                )


# Integration marker for slow tests
pytestmark = pytest.mark.unit

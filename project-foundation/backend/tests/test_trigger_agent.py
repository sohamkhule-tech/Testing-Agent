"""
Unit Tests for Trigger Agent

Tests for trigger agent execution logic.
"""

import pytest
from uuid import UUID

from app.agents import TriggerAgent
from app.constants import RunStatus
from app.exceptions import AgentExecutionError
from app.infrastructure import WorkspaceManager
from app.repositories import RunRepository
from app.schemas import CreateRunRequest, TargetApplicationInput
from app.services import TriggerService


@pytest.fixture
async def trigger_service(tmp_path):
    """Create trigger service for testing."""
    repository = RunRepository(storage_dir=tmp_path / "metadata")
    workspace_manager = WorkspaceManager()
    service = TriggerService(
        repository=repository,
        workspace_manager=workspace_manager,
    )
    await service.initialize()
    return service


@pytest.fixture
def trigger_agent(trigger_service):
    """Create trigger agent for testing."""
    return TriggerAgent(service=trigger_service)


@pytest.fixture
def sample_request():
    """Create sample run request."""
    return {
        "target_application": {
            "base_url": "https://example.com",
            "environment": "staging",
        },
        "execution_mode": {
            "crawl_strategy": "full",
            "test_level": "regression",
        },
    }


class TestTriggerAgent:
    """Test trigger agent functionality."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_agent_initialization(self, trigger_agent):
        """Test trigger agent can be initialized."""
        assert trigger_agent is not None
        assert trigger_agent.service is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_agent_execute_success(self, trigger_agent, sample_request):
        """Test trigger agent executes successfully."""
        input_data = {
            "request": sample_request,
            "requested_by": "test@example.com",
        }

        result = await trigger_agent.execute(input_data)

        assert result["success"] is True
        assert "run_id" in result
        assert "workspace_path" in result
        assert result["status"] == "running"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_agent_execute_missing_request(self, trigger_agent):
        """Test trigger agent fails with missing request."""
        input_data = {}

        with pytest.raises(AgentExecutionError, match="Missing 'request'"):
            await trigger_agent.execute(input_data)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_trigger_agent_get_system_prompt(self, trigger_agent):
        """Test trigger agent returns system prompt."""
        prompt = trigger_agent.get_system_prompt()

        assert prompt is not None
        assert len(prompt) > 0
        assert "Trigger Agent" in prompt
        assert "validation" in prompt.lower()

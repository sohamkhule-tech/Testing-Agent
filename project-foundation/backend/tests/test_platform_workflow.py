"""
Platform Workflow Tests

Integration tests for complete workflow orchestration.
"""

from uuid import uuid4

import pytest

from app.agents import CrawlerAgent, TriggerAgent
from app.dependencies import (
    get_crawler_agent,
    get_crawler_service,
    get_trigger_agent,
    get_trigger_service,
)
from app.workflows import execute_platform_workflow


@pytest.mark.integration
class TestPlatformWorkflow:
    """Test suite for complete platform workflow."""

    @pytest.fixture
    def trigger_agent(self):
        """Get trigger agent."""
        return get_trigger_agent()

    @pytest.fixture
    def crawler_agent(self):
        """Get crawler agent."""
        return get_crawler_agent()

    @pytest.fixture
    def sample_request_data(self):
        """Create sample request data."""
        return {
            "target_application": {
                "base_url": "https://example.com",
                "environment": "staging",
            },
            "execution_mode": {
                "crawl_strategy": "full",
                "test_level": "regression",
            },
            "scope": {
                "max_crawl_depth": 2,
                "max_pages": 5,
            },
            "requested_by": "test@example.com",
        }

    @pytest.mark.asyncio
    async def test_platform_workflow_complete_execution(
        self, trigger_agent, crawler_agent, sample_request_data
    ):
        """Test complete workflow execution."""
        # Arrange
        await get_crawler_service().initialize()

        # Act
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=sample_request_data,
            requested_by="test@example.com",
        )

        # Assert
        assert result["success"] is True
        assert "run_id" in result
        assert "workspace_path" in result
        assert "trigger" in result
        assert "crawler" in result
        assert "inventory" in result
        assert result["pages_visited"] > 0
        assert len(result["errors"]) == 0

        # Cleanup
        await get_crawler_service().cleanup()

    @pytest.mark.asyncio
    async def test_platform_workflow_trigger_node(
        self, trigger_agent, crawler_agent, sample_request_data
    ):
        """Test trigger node execution."""
        # Arrange
        await get_crawler_service().initialize()

        # Act
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=sample_request_data,
            requested_by="test@example.com",
        )

        # Assert
        trigger_result = result["trigger"]
        assert trigger_result["success"] is True
        assert "run_id" in trigger_result
        assert "workspace_path" in trigger_result
        assert "request_id" in trigger_result

        # Cleanup
        await get_crawler_service().cleanup()

    @pytest.mark.asyncio
    async def test_platform_workflow_crawler_node(
        self, trigger_agent, crawler_agent, sample_request_data
    ):
        """Test crawler node execution."""
        # Arrange
        await get_crawler_service().initialize()

        # Act
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=sample_request_data,
            requested_by="test@example.com",
        )

        # Assert
        crawler_result = result["crawler"]
        assert crawler_result["success"] is True
        assert "crawl_status" in crawler_result
        assert "pages_visited" in crawler_result
        assert "total_links" in crawler_result
        assert crawler_result["crawl_status"] in ("completed", "partial")

        # Cleanup
        await get_crawler_service().cleanup()

    @pytest.mark.asyncio
    async def test_platform_workflow_with_invalid_url(
        self, trigger_agent, crawler_agent, sample_request_data
    ):
        """Test workflow with invalid target URL."""
        # Arrange
        await get_crawler_service().initialize()
        sample_request_data["target_application"][
            "base_url"
        ] = "https://this-domain-does-not-exist-123456789.com"

        # Act
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=sample_request_data,
            requested_by="test@example.com",
        )

        # Assert
        assert result["success"] is False
        assert len(result["errors"]) > 0

        # Cleanup
        await get_crawler_service().cleanup()

    @pytest.mark.asyncio
    async def test_platform_workflow_creates_artifacts(
        self, trigger_agent, crawler_agent, sample_request_data, tmp_path
    ):
        """Test that workflow creates expected artifacts."""
        # Arrange
        await get_crawler_service().initialize()

        # Act
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=sample_request_data,
            requested_by="test@example.com",
        )

        # Assert
        from pathlib import Path

        workspace = Path(result["workspace_path"])
        assert workspace.exists()
        assert (workspace / "contracts" / "test-run-request.json").exists()
        assert (workspace / "contracts" / "crawl-package.json").exists()
        assert (workspace / "artifacts").exists()
        assert (workspace / "screenshots").exists()
        if result["success"]:
            assert (workspace / "contracts" / "inventory.json").exists()
            assert (workspace / "contracts" / "test-plan.json").exists()
            assert (workspace / "contracts" / "test-plan.md").exists()

        # Cleanup
        await get_crawler_service().cleanup()

    @pytest.mark.asyncio
    async def test_platform_workflow_state_transitions(
        self, trigger_agent, crawler_agent, sample_request_data
    ):
        """Test workflow state transitions."""
        # Arrange
        await get_crawler_service().initialize()

        # Act
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=sample_request_data,
            requested_by="test@example.com",
        )

        # Assert
        assert result["status"] == "completed"
        # All nodes should have executed
        assert "trigger" in result
        assert "crawler" in result
        assert "inventory" in result

        # Cleanup
        await get_crawler_service().cleanup()

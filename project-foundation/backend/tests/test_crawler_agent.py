"""
Crawler Agent Tests

Unit tests for CrawlerAgent.
"""

from uuid import uuid4

import pytest

from app.agents import CrawlerAgent
from app.exceptions import AgentExecutionError
from app.schemas import CrawlPackage, CrawlRequest, CrawlSummary
from app.services import CrawlerService


@pytest.mark.unit
class TestCrawlerAgent:
    """Test suite for CrawlerAgent."""

    @pytest.fixture
    def mock_crawler_service(self, mocker):
        """Create mock crawler service."""
        service = mocker.Mock(spec=CrawlerService)
        return service

    @pytest.fixture
    def crawler_agent(self, mock_crawler_service):
        """Create crawler agent instance."""
        return CrawlerAgent(service=mock_crawler_service)

    def test_crawler_agent_initialization(self, crawler_agent, mock_crawler_service):
        """Test agent initialization."""
        assert crawler_agent.service == mock_crawler_service

    @pytest.mark.asyncio
    async def test_crawler_agent_execute_success(
        self, crawler_agent, mock_crawler_service, tmp_path
    ):
        """Test successful crawler execution."""
        # Arrange
        run_id = uuid4()
        request_id = uuid4()
        workspace_path = str(tmp_path / "test_workspace")

        input_data = {
            "run_id": str(run_id),
            "request_id": str(request_id),
            "workspace_path": workspace_path,
            "trigger_output": {},
            "request_data": {
                "targetApplication": {
                    "url": "https://example.com",
                },
                "executionMode": {
                    "maxCrawlDepth": 2,
                    "maxPages": 10,
                    "timeout": 30000,
                    "browser": "chromium",
                    "headless": True,
                },
            },
        }

        # Mock crawl package
        mock_package = CrawlPackage(
            run_id=run_id,
            request_id=request_id,
            crawl_summary=CrawlSummary(
                start_time="2026-07-23T10:00:00Z",
                end_time="2026-07-23T10:00:05Z",
                duration=5000,
                status="completed",
                pages_visited=5,
                total_links=15,
            ),
            visited_pages=[],
            navigation_graph={"edges": [], "root_page_id": None},
        )
        mock_crawler_service.crawl.return_value = mock_package

        # Act
        result = await crawler_agent.execute(input_data)

        # Assert
        assert result["success"] is True
        assert result["run_id"] == str(run_id)
        assert result["pages_visited"] == 5
        assert result["total_links"] == 15
        assert result["crawl_status"] == "completed"
        mock_crawler_service.crawl.assert_called_once()

    @pytest.mark.asyncio
    async def test_crawler_agent_execute_missing_run_id(self, crawler_agent):
        """Test execution with missing run_id."""
        # Arrange
        input_data = {
            "workspace_path": "/test/path",
            "request_data": {},
        }

        # Act & Assert
        with pytest.raises(AgentExecutionError, match="Missing 'run_id'"):
            await crawler_agent.execute(input_data)

    @pytest.mark.asyncio
    async def test_crawler_agent_execute_missing_workspace(self, crawler_agent):
        """Test execution with missing workspace path."""
        # Arrange
        input_data = {
            "run_id": str(uuid4()),
            "request_data": {},
        }

        # Act & Assert
        with pytest.raises(AgentExecutionError, match="Missing 'workspace_path'"):
            await crawler_agent.execute(input_data)

    @pytest.mark.asyncio
    async def test_crawler_agent_execute_missing_target_url(self, crawler_agent):
        """Test execution with missing target URL."""
        # Arrange
        input_data = {
            "run_id": str(uuid4()),
            "workspace_path": "/test/path",
            "request_data": {
                "targetApplication": {},
            },
        }

        # Act & Assert
        with pytest.raises(AgentExecutionError, match="Missing target URL"):
            await crawler_agent.execute(input_data)

    @pytest.mark.asyncio
    async def test_crawler_agent_execute_invalid_uuid(self, crawler_agent):
        """Test execution with invalid UUID."""
        # Arrange
        input_data = {
            "run_id": "invalid-uuid",
            "workspace_path": "/test/path",
            "request_data": {},
        }

        # Act & Assert
        with pytest.raises(AgentExecutionError, match="Invalid UUID format"):
            await crawler_agent.execute(input_data)

    @pytest.mark.asyncio
    async def test_crawler_agent_execute_service_failure(
        self, crawler_agent, mock_crawler_service
    ):
        """Test execution with service failure."""
        # Arrange
        run_id = uuid4()
        input_data = {
            "run_id": str(run_id),
            "request_id": str(run_id),
            "workspace_path": "/test/path",
            "request_data": {
                "targetApplication": {"url": "https://example.com"},
                "executionMode": {},
            },
        }

        mock_crawler_service.crawl.side_effect = Exception("Crawl failed")

        # Act & Assert
        with pytest.raises(AgentExecutionError, match="Crawler agent execution failed"):
            await crawler_agent.execute(input_data)

    def test_crawler_agent_get_system_prompt(self, crawler_agent):
        """Test get system prompt."""
        # Act
        prompt = crawler_agent.get_system_prompt()

        # Assert
        assert isinstance(prompt, str)
        assert len(prompt) > 0

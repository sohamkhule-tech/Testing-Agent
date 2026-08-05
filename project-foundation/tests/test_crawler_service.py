"""
Crawler Service Tests

Unit tests for CrawlerService.
"""

from pathlib import Path
from uuid import uuid4

import pytest

from app.exceptions import ServiceError
from app.infrastructure import BrowserManager
from app.schemas import CrawlRequest
from app.services import CrawlerService


@pytest.mark.unit
class TestCrawlerService:
    """Test suite for CrawlerService."""

    @pytest.fixture
    def mock_browser_manager(self, mocker):
        """Create mock browser manager."""
        manager = mocker.Mock(spec=BrowserManager)
        manager.is_initialized = True
        return manager

    @pytest.fixture
    def crawler_service(self, mock_browser_manager):
        """Create crawler service instance."""
        return CrawlerService(browser_manager=mock_browser_manager)

    def test_crawler_service_initialization(
        self, crawler_service, mock_browser_manager
    ):
        """Test service initialization."""
        assert crawler_service.browser_manager == mock_browser_manager

    @pytest.mark.asyncio
    async def test_crawler_service_initialize(
        self, crawler_service, mock_browser_manager
    ):
        """Test service initialize method."""
        # Act
        await crawler_service.initialize()

        # Assert
        mock_browser_manager.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_crawler_service_cleanup(self, crawler_service, mock_browser_manager):
        """Test service cleanup method."""
        # Act
        await crawler_service.cleanup()

        # Assert
        mock_browser_manager.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_crawler_service_reset_state(self, crawler_service, mocker):
        """Test state reset."""
        # Arrange
        crawler_service._visited_urls.add("https://example.com")
        crawler_service._visited_pages.append(mocker.Mock())

        # Act
        crawler_service._reset_state()

        # Assert
        assert len(crawler_service._visited_urls) == 0
        assert len(crawler_service._visited_pages) == 0

    @pytest.mark.asyncio
    async def test_crawler_service_extract_links(self, crawler_service, mocker):
        """Test link extraction."""
        # Arrange
        mock_page = mocker.AsyncMock()
        mock_page.eval_on_selector_all = mocker.AsyncMock(return_value=[
            {"href": "/about", "text": "About Us"},
            {"href": "https://example.com/contact", "text": "Contact"},
            {"href": "https://external.com/page", "text": "External"},
        ])

        # Act
        links = await crawler_service._extract_links(
            mock_page, "https://example.com/home"
        )

        # Assert
        assert len(links) == 2  # Only same-domain links
        assert ("https://example.com/about", "About Us") in links
        assert ("https://example.com/contact", "Contact") in links

    @pytest.mark.asyncio
    async def test_crawler_service_build_crawl_package(self, crawler_service):
        """Test crawl package building."""
        # Arrange
        from datetime import datetime, timezone

        run_id = uuid4()
        request_id = uuid4()
        start_time = datetime.now(timezone.utc)
        end_time = datetime.now(timezone.utc)

        request = CrawlRequest(
            run_id=run_id,
            request_id=request_id,
            workspace_path="/test/workspace",
            target_url="https://example.com",
        )

        # Act
        package = crawler_service._build_crawl_package(
            request=request,
            start_time=start_time,
            end_time=end_time,
            duration_ms=1000,
            status="completed",
        )

        # Assert
        assert package.run_id == run_id
        assert package.request_id == request_id
        assert package.crawl_summary.status == "completed"
        assert package.crawl_summary.duration == 1000


@pytest.mark.integration
class TestCrawlerServiceIntegration:
    """Integration tests for CrawlerService with real browser."""

    @pytest.fixture
    def browser_manager(self):
        """Create real browser manager."""
        return BrowserManager(browser_type="chromium", headless=True, timeout=10000)

    @pytest.fixture
    def crawler_service(self, browser_manager):
        """Create crawler service with real browser."""
        return CrawlerService(browser_manager=browser_manager)

    @pytest.mark.asyncio
    async def test_crawler_service_crawl_example_com(
        self, crawler_service, tmp_path
    ):
        """Test crawling example.com."""
        # Arrange
        await crawler_service.initialize()

        workspace = tmp_path / "test_run"
        workspace.mkdir()
        (workspace / "artifacts").mkdir()
        (workspace / "screenshots").mkdir()
        (workspace / "contracts").mkdir()

        request = CrawlRequest(
            run_id=uuid4(),
            request_id=uuid4(),
            workspace_path=str(workspace),
            target_url="https://example.com",
            max_depth=1,
            max_pages=3,
            timeout=30000,
            browser="chromium",
            headless=True,
            screenshot=True,
        )

        # Act
        package = await crawler_service.crawl(request)

        # Assert
        assert package.crawl_summary.status in ("completed", "partial")
        assert package.crawl_summary.pages_visited > 0
        assert len(package.visited_pages) > 0
        assert (workspace / "contracts" / "crawl-package.json").exists()

        # Cleanup
        await crawler_service.cleanup()

    @pytest.mark.asyncio
    async def test_crawler_service_crawl_with_invalid_url(
        self, crawler_service, tmp_path
    ):
        """Test crawling with invalid URL."""
        # Arrange
        await crawler_service.initialize()

        workspace = tmp_path / "test_run"
        workspace.mkdir()
        (workspace / "artifacts").mkdir()
        (workspace / "screenshots").mkdir()
        (workspace / "contracts").mkdir()

        request = CrawlRequest(
            run_id=uuid4(),
            request_id=uuid4(),
            workspace_path=str(workspace),
            target_url="https://this-domain-does-not-exist-123456789.com",
            max_depth=1,
            max_pages=3,
        )

        # Act & Assert
        with pytest.raises(ServiceError):
            await crawler_service.crawl(request)

        # Cleanup
        await crawler_service.cleanup()

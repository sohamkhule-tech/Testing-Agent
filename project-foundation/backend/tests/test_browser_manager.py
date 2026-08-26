"""
Browser Manager Tests

Unit tests for BrowserManager using Playwright.
"""

from pathlib import Path

import pytest

from app.exceptions import BrowserError
from app.infrastructure import BrowserManager


@pytest.mark.unit
class TestBrowserManager:
    """Test suite for BrowserManager."""

    @pytest.fixture
    def browser_manager(self):
        """Create browser manager instance."""
        return BrowserManager(
            browser_type="chromium",
            headless=True,
            timeout=10000,
        )

    def test_browser_manager_initialization(self, browser_manager):
        """Test manager initialization."""
        assert browser_manager.browser_type == "chromium"
        assert browser_manager.headless is True
        assert browser_manager.timeout == 10000
        assert not browser_manager.is_initialized

    @pytest.mark.asyncio
    async def test_browser_manager_initialize_success(self, browser_manager):
        """Test successful browser initialization."""
        # Act
        await browser_manager.initialize()

        # Assert
        assert browser_manager.is_initialized
        assert browser_manager.active_contexts_count == 0

        # Cleanup
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_create_context(self, browser_manager, tmp_path):
        """Test context creation."""
        # Arrange
        await browser_manager.initialize()

        # Act
        context = await browser_manager.create_context()

        # Assert
        assert context is not None
        assert browser_manager.active_contexts_count == 1

        # Cleanup
        await browser_manager.close_context(context)
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_create_context_with_har(
        self, browser_manager, tmp_path
    ):
        """Test context creation with HAR recording."""
        # Arrange
        await browser_manager.initialize()
        har_path = tmp_path / "test.har"

        # Act
        context = await browser_manager.create_context(
            record_har=True, har_path=har_path
        )

        # Assert
        assert context is not None
        assert browser_manager.active_contexts_count == 1

        # Cleanup
        await browser_manager.close_context(context)
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_new_page(self, browser_manager):
        """Test page creation."""
        # Arrange
        await browser_manager.initialize()
        context = await browser_manager.create_context()

        # Act
        page = await browser_manager.new_page(context)

        # Assert
        assert page is not None
        assert page.url == "about:blank"

        # Cleanup
        await page.close()
        await browser_manager.close_context(context)
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_navigate_success(self, browser_manager):
        """Test successful navigation."""
        # Arrange
        await browser_manager.initialize()
        context = await browser_manager.create_context()
        page = await browser_manager.new_page(context)

        # Act
        await browser_manager.navigate(page, "https://example.com")

        # Assert
        assert "example.com" in page.url

        # Cleanup
        await page.close()
        await browser_manager.close_context(context)
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_screenshot(self, browser_manager, tmp_path):
        """Test screenshot capture."""
        # Arrange
        await browser_manager.initialize()
        context = await browser_manager.create_context()
        page = await browser_manager.new_page(context)
        await browser_manager.navigate(page, "https://example.com")
        screenshot_path = tmp_path / "screenshot.png"

        # Act
        await browser_manager.screenshot(page, screenshot_path, full_page=True)

        # Assert
        assert screenshot_path.exists()
        assert screenshot_path.stat().st_size > 0

        # Cleanup
        await page.close()
        await browser_manager.close_context(context)
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_close_context(self, browser_manager):
        """Test context closure."""
        # Arrange
        await browser_manager.initialize()
        context = await browser_manager.create_context()

        # Act
        await browser_manager.close_context(context)

        # Assert
        assert browser_manager.active_contexts_count == 0

        # Cleanup
        await browser_manager.cleanup()

    @pytest.mark.asyncio
    async def test_browser_manager_cleanup(self, browser_manager):
        """Test cleanup."""
        # Arrange
        await browser_manager.initialize()
        context = await browser_manager.create_context()

        # Act
        await browser_manager.cleanup()

        # Assert
        assert not browser_manager.is_initialized
        assert browser_manager.active_contexts_count == 0

    @pytest.mark.asyncio
    async def test_browser_manager_create_context_before_init(self, browser_manager):
        """Test context creation auto-initializes browser."""
        # Act - create_context should auto-initialize
        context = await browser_manager.create_context()

        # Assert
        assert browser_manager.is_initialized
        assert context is not None
        await browser_manager.close_context(context)

    @pytest.mark.asyncio
    async def test_browser_manager_unsupported_browser(self):
        """Test unsupported browser type."""
        # Arrange
        manager = BrowserManager(browser_type="safari")

        # Act & Assert
        with pytest.raises(BrowserError, match="Unsupported browser type"):
            await manager.initialize()

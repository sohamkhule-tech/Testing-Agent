"""
Browser Manager

Manages Playwright browser lifecycle and context creation.
"""

from pathlib import Path
from typing import Any, Literal

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.config import get_settings
from app.exceptions import BrowserError
from app.logging import LoggerMixin


class BrowserManager(LoggerMixin):
    """
    Manages browser lifecycle using Playwright.
    
    Responsibilities:
    - Browser initialization and shutdown
    - Browser context creation with isolation
    - Screenshot capture
    - HAR and trace collection
    - Resource cleanup
    """

    def __init__(
        self,
        browser_type: Literal["chromium", "firefox", "webkit"] = "chromium",
        headless: bool = True,
        timeout: int = 30000,
    ) -> None:
        """
        Initialize browser manager.

        Args:
            browser_type: Browser engine to use
            headless: Run in headless mode
            timeout: Default navigation timeout in milliseconds
        """
        super().__init__()
        self.browser_type = browser_type
        self.headless = headless
        self.timeout = timeout
        
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._contexts: list[BrowserContext] = []
        
        settings = get_settings()
        self.viewport_width = settings.playwright.playwright_viewport_width
        self.viewport_height = settings.playwright.playwright_viewport_height

    async def initialize(self) -> None:
        """
        Initialize Playwright and launch browser.
        
        Raises:
            BrowserError: If browser launch fails
        """
        try:
            self.logger.info(
                "browser_initializing",
                browser_type=self.browser_type,
                headless=self.headless,
            )

            # Start Playwright
            self._playwright = await async_playwright().start()

            # Get browser type
            if self.browser_type == "chromium":
                browser_launcher = self._playwright.chromium
            elif self.browser_type == "firefox":
                browser_launcher = self._playwright.firefox
            elif self.browser_type == "webkit":
                browser_launcher = self._playwright.webkit
            else:
                raise BrowserError(f"Unsupported browser type: {self.browser_type}")

            # Launch browser
            launch_args: list[str] = []
            if self.browser_type == "chromium":
                launch_args.append("--disable-blink-features=AutomationControlled")
                if not self.headless:
                    launch_args.append("--start-maximized")
                    launch_args.append(f"--window-size={self.viewport_width},{self.viewport_height}")
                    launch_args.append("--window-position=0,0")
            self._browser = await browser_launcher.launch(
                headless=self.headless,
                args=launch_args if launch_args else None,
            )

            self.logger.info(
                "browser_initialized",
                browser_type=self.browser_type,
            )

        except Exception as e:
            self.logger.error("browser_initialization_failed", error=str(e))
            raise BrowserError(f"Failed to initialize browser: {str(e)}") from e

    async def create_context(
        self,
        *,
        record_har: bool = False,
        record_video: bool = False,
        har_path: Path | None = None,
        video_path: Path | None = None,
        timeout: int | None = None,
    ) -> BrowserContext:
        """
        Create isolated browser context.

        Args:
            record_har: Enable HAR recording
            record_video: Enable video recording
            har_path: HAR file output path
            video_path: Video output directory

        Returns:
            New browser context

        Raises:
            BrowserError: If context creation fails
        """
        if not self._browser:
            await self.initialize()

        try:
            self.logger.info("creating_browser_context")

            context_options: dict[str, Any] = {
                "ignore_https_errors": True,
                "java_script_enabled": True,
                "bypass_csp": False,
            }

            if self.headless:
                context_options["viewport"] = {
                    "width": self.viewport_width,
                    "height": self.viewport_height,
                }
            else:
                context_options["no_viewport"] = True

            # Add HAR recording if requested
            if record_har and har_path:
                har_path.parent.mkdir(parents=True, exist_ok=True)
                context_options["record_har_path"] = str(har_path)
                context_options["record_har_mode"] = "minimal"

            # Add video recording if requested
            if record_video and video_path:
                video_path.mkdir(parents=True, exist_ok=True)
                context_options["record_video_dir"] = str(video_path)
                if self.headless:
                    context_options["record_video_size"] = {
                        "width": self.viewport_width,
                        "height": self.viewport_height,
                    }

            try:
                context = await self._browser.new_context(**context_options)
            except Exception:
                # Browser connection may be stale, reinitialize and retry
                self.logger.warning("context_creation_retry", error="Browser connection lost, reinitializing")
                await self.cleanup()
                await self.initialize()
                context = await self._browser.new_context(**context_options)
            
            # Set default timeout
            context_timeout = timeout or self.timeout
            context.set_default_timeout(context_timeout)
            context.set_default_navigation_timeout(context_timeout)

            # Track context
            self._contexts.append(context)

            self.logger.info(
                "browser_context_created",
                contexts_count=len(self._contexts),
            )

            return context

        except Exception as e:
            self.logger.error("context_creation_failed", error=str(e))
            raise BrowserError(f"Failed to create browser context: {str(e)}") from e

    async def new_page(self, context: BrowserContext) -> Page:
        """
        Create new page in context.

        Args:
            context: Browser context

        Returns:
            New page

        Raises:
            BrowserError: If page creation fails
        """
        try:
            self.logger.info("creating_new_page")
            
            page = await context.new_page()
            
            self.logger.info("page_created")
            
            return page

        except Exception as e:
            self.logger.error("page_creation_failed", error=str(e))
            raise BrowserError(f"Failed to create page: {str(e)}") from e

    async def navigate(
        self,
        page: Page,
        url: str,
        wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load",
    ) -> None:
        """
        Navigate to URL with retry logic.

        Args:
            page: Page to navigate
            url: Target URL
            wait_until: When to consider navigation complete

        Raises:
            BrowserError: If navigation fails
        """
        try:
            self.logger.info("navigating_to_url", url=url)

            response = await page.goto(url, wait_until=wait_until, timeout=self.timeout)

            if not response:
                raise BrowserError(f"No response from {url}")

            status = response.status

            self.logger.info(
                "navigation_completed",
                url=url,
                status=status,
            )

            if status >= 400:
                self.logger.warning(
                    "navigation_returned_error_status",
                    url=url,
                    status=status,
                )

        except Exception as e:
            self.logger.error("navigation_failed", url=url, error=str(e))
            raise BrowserError(f"Failed to navigate to {url}: {str(e)}") from e

    async def screenshot(
        self,
        page: Page,
        path: Path,
        full_page: bool = True,
    ) -> None:
        """
        Capture page screenshot.

        Args:
            page: Page to screenshot
            path: Output file path
            full_page: Capture full scrollable page

        Raises:
            BrowserError: If screenshot fails
        """
        try:
            self.logger.info("capturing_screenshot", path=str(path))

            path.parent.mkdir(parents=True, exist_ok=True)

            await page.screenshot(
                path=str(path),
                full_page=full_page,
                type="png",
            )

            self.logger.info("screenshot_captured", path=str(path))

        except Exception as e:
            self.logger.error("screenshot_failed", error=str(e))
            raise BrowserError(f"Failed to capture screenshot: {str(e)}") from e

    async def close_context(self, context: BrowserContext) -> None:
        """
        Close browser context and finalize recordings.

        Args:
            context: Context to close

        Raises:
            BrowserError: If context closure fails
        """
        try:
            self.logger.info("closing_context")

            # Close HAR if recording
            try:
                await context.close()
            except Exception as e:
                self.logger.warning("context_close_error", error=str(e))

            # Remove from tracking
            if context in self._contexts:
                self._contexts.remove(context)

            self.logger.info(
                "context_closed",
                remaining_contexts=len(self._contexts),
            )

        except Exception as e:
            self.logger.error("context_closure_failed", error=str(e))
            raise BrowserError(f"Failed to close context: {str(e)}") from e

    async def cleanup(self) -> None:
        """
        Cleanup all browser resources.
        
        Closes all contexts and browser, stops Playwright.
        """
        try:
            self.logger.info("browser_cleanup_started")

            # Close all contexts
            for context in list(self._contexts):
                try:
                    await context.close()
                except Exception as e:
                    self.logger.warning("context_cleanup_error", error=str(e))

            self._contexts.clear()

            # Close browser
            if self._browser:
                await self._browser.close()
                self._browser = None

            # Stop Playwright
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None

            self.logger.info("browser_cleanup_completed")

        except Exception as e:
            self.logger.error("browser_cleanup_failed", error=str(e))
            # Don't raise - best effort cleanup

    @property
    def is_initialized(self) -> bool:
        """Check if browser is initialized."""
        return self._browser is not None

    @property
    def active_contexts_count(self) -> int:
        """Get count of active contexts."""
        return len(self._contexts)

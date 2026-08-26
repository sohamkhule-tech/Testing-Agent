"""
Browser Manager

Manages Playwright browser lifecycle and context creation.
Supports automatic ProactorEventLoop bridging on Windows when running under a SelectorEventLoop.
"""

import asyncio
import sys
import threading
from pathlib import Path
from typing import Any, Literal

from playwright.async_api import Browser, BrowserContext, Page, Playwright, async_playwright

from app.config import get_settings
from app.exceptions import BrowserError
from app.logging import LoggerMixin


class ProactorBridge:
    """
    Bridge for executing Playwright coroutines on a dedicated ProactorEventLoop thread on Windows.

    Required when the main application event loop is a SelectorEventLoop (e.g. Uvicorn default on Windows),
    which does not support asyncio subprocess execution required by Playwright driver.
    """

    def __init__(self) -> None:
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def ensure_started(self) -> None:
        if self._thread is None or not self._thread.is_alive():
            self._loop = asyncio.WindowsProactorEventLoopPolicy().new_event_loop()
            def _target() -> None:
                assert self._loop is not None
                asyncio.set_event_loop(self._loop)
                self._loop.run_forever()
            self._thread = threading.Thread(target=_target, daemon=True, name="ProactorPlaywrightBridge")
            self._thread.start()

    async def execute(self, coro: Any) -> Any:
        self.ensure_started()
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return await asyncio.wrap_future(fut)


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
        self._bridge = ProactorBridge()

        settings = get_settings()
        self.viewport_width = settings.playwright.playwright_viewport_width
        self.viewport_height = settings.playwright.playwright_viewport_height

    def _needs_bridge(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            loop = asyncio.get_running_loop()
            return not isinstance(loop, asyncio.ProactorEventLoop)
        except Exception:
            return False

    async def initialize(self) -> None:
        """Initialize Playwright and launch browser."""
        if self._needs_bridge():
            return await self._bridge.execute(self._initialize_impl())
        return await self._initialize_impl()

    async def _initialize_impl(self) -> None:
        try:
            self.logger.info(
                "browser_initializing",
                browser_type=self.browser_type,
                headless=self.headless,
            )

            # Defensive cleanup: if a stale Playwright or browser exists from a
            # previous run that did not cleanly shut down, reset them first.
            if self._browser:
                try:
                    await self._browser.close()
                except Exception:
                    pass
                self._browser = None
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
                self._playwright = None

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
            err_msg = str(e) or repr(e) or type(e).__name__
            self.logger.error("browser_initialization_failed", error=err_msg)
            raise BrowserError(f"Failed to initialize browser: {err_msg}") from e

    async def create_context(
        self,
        *,
        record_har: bool = False,
        record_video: bool = False,
        har_path: Path | None = None,
        video_path: Path | None = None,
        timeout: int | None = None,
    ) -> BrowserContext:
        """Create isolated browser context."""
        if self._needs_bridge():
            return await self._bridge.execute(
                self._create_context_impl(
                    record_har=record_har,
                    record_video=record_video,
                    har_path=har_path,
                    video_path=video_path,
                    timeout=timeout,
                )
            )
        return await self._create_context_impl(
            record_har=record_har,
            record_video=record_video,
            har_path=har_path,
            video_path=video_path,
            timeout=timeout,
        )

    async def _create_context_impl(
        self,
        *,
        record_har: bool = False,
        record_video: bool = False,
        har_path: Path | None = None,
        video_path: Path | None = None,
        timeout: int | None = None,
    ) -> BrowserContext:
        if not self._browser:
            await self._initialize_impl()

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
                await self._cleanup_impl()
                await self._initialize_impl()
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
        """Create new page in context."""
        if self._needs_bridge():
            return await self._bridge.execute(self._new_page_impl(context))
        return await self._new_page_impl(context)

    async def _new_page_impl(self, context: BrowserContext) -> Page:
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
        """Navigate to URL with retry logic."""
        if self._needs_bridge():
            return await self._bridge.execute(self._navigate_impl(page, url, wait_until))
        return await self._navigate_impl(page, url, wait_until)

    async def _navigate_impl(
        self,
        page: Page,
        url: str,
        wait_until: Literal["load", "domcontentloaded", "networkidle", "commit"] = "load",
    ) -> None:
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
        """Capture page screenshot."""
        if self._needs_bridge():
            return await self._bridge.execute(self._screenshot_impl(page, path, full_page))
        return await self._screenshot_impl(page, path, full_page)

    async def _screenshot_impl(
        self,
        page: Page,
        path: Path,
        full_page: bool = True,
    ) -> None:
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
        """Close browser context and finalize recordings."""
        if self._needs_bridge():
            return await self._bridge.execute(self._close_context_impl(context))
        return await self._close_context_impl(context)

    async def _close_context_impl(self, context: BrowserContext) -> None:
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
        """Cleanup all browser resources."""
        if self._needs_bridge():
            return await self._bridge.execute(self._cleanup_impl())
        return await self._cleanup_impl()

    async def _cleanup_impl(self) -> None:
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

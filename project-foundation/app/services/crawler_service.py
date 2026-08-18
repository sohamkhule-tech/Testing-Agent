"""
Crawler Service

Business logic for web crawling and discovery.
"""

import asyncio
import re
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, parse_qsl, urlencode, urljoin, urlparse, urlsplit, urlunsplit
from uuid import UUID, uuid4

from playwright.async_api import BrowserContext, Locator, Page

from app.core.event_bus import EventType, emit
from app.core.interfaces import IService
from app.exceptions import BrowserError, ServiceError
from app.execution_scope.resolver import ExecutionScopeResolver
from app.infrastructure import BrowserManager
from app.logging import LoggerMixin
from app.schemas import (
    AssetRecord,
    AssetsCollection,
    ButtonRecord,
    CheckboxRecord,
    CookieRecord,
    CrawlEvent,
    CrawlPackage,
    CrawlRequest,
    CrawlStatistics,
    CrawlSummary,
    DialogRecord,
    DropdownRecord,
    FormRecord,
    InputRecord,
    NavigationEdge,
    NavigationGraph,
    PageRecord,
    RadioRecord,
    RedirectRecord,
    ResponseTimeStats,
    ScreenshotRecord,
    SessionInfo,
    TableRecord,
    UploadRecord,
)
from app.services.dom_extractor import extract_all
from app.utils import save_file


class AuthFailureReason(StrEnum):
    """Structured authentication failure reasons (Phase 4.5 audit fixes)."""
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    LOGIN_TIMEOUT = "LOGIN_TIMEOUT"
    MFA_REQUIRED = "MFA_REQUIRED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    OAUTH_REDIRECT_TIMEOUT = "OAUTH_REDIRECT_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    LOGIN_SUCCESS_BUT_VALIDATION_FAILED = "LOGIN_SUCCESS_BUT_VALIDATION_FAILED"
    UNKNOWN_AUTH_ERROR = "UNKNOWN_AUTH_ERROR"


# Phase 4.5: auth error text patterns — only EXACT text matches, no class selectors
_AUTH_ERROR_TEXT_PATTERNS: list[str] = [
    "invalid username", "invalid password", "incorrect password",
    "incorrect username", "wrong credentials", "wrong password", "wrong username",
    "authentication failed", "login failed", "access denied",
    "invalid email", "invalid user", "user not found", "account not found",
    "account locked", "too many attempts",
    "verify your identity", "mfa required", "multi-factor authentication",
    "2fa required", "two-factor authentication", "captcha", "please complete the captcha",
]

# Post-login success indicators (title keywords)
_POST_LOGIN_TITLE_KW: set[str] = {
    "dashboard", "home", "workspace", "welcome",
    "overview", "projects", "portal", "app",
}

# CSS selectors for post-login authenticated UI (ONLY structural, NO class-substring)
_POST_LOGIN_UI_SELECTORS: list[str] = [
    'nav:visible', '[role="navigation"]:visible',
    'a:has-text("Logout"):visible', 'a:has-text("Log out"):visible',
    'a:has-text("Sign out"):visible', 'button:has-text("Logout"):visible',
    'a:has-text("Profile"):visible', 'a:has-text("Account"):visible',
    '[aria-label="User menu"]:visible', '[aria-label="Account"]:visible',
]


class CrawlPhase(StrEnum):
    DISCOVERY = "discovery"
    NAVIGATION = "navigation"
    GOAL_COMPLETION = "goal_completion"
    CRAWL_COMPLETION = "crawl_completion"


class CrawlerService(IService, LoggerMixin):
    """
    Crawler service orchestrating web discovery.
    
    Responsibilities:
    - Execute crawl strategy (BFS)
    - Manage browser lifecycle via BrowserManager
    - Discover pages, links, and assets
    - Capture screenshots and HAR files
    - Generate crawl-package.json contract
    - Handle errors and retries
    """

    def __init__(self, browser_manager: BrowserManager) -> None:
        """
        Initialize crawler service.

        Args:
            browser_manager: Browser lifecycle manager
        """
        super().__init__()
        self.browser_manager = browser_manager

        # Set by the workflow node so the crawler can emit SSE events
        # for the active run. If not set, events are silently skipped.
        self._event_run_id: str | None = None

        # Phase 5/6 — set by CrawlerAgent before calling crawl()
        self._auth_context = None           # AuthContext | None  (SECURITY: never logged)
        self._exclude_patterns: list[str] = []
        self._include_patterns: list[str] = []
        self._screenshots_dir: str | None = None  # set during crawl(); used by _perform_login

        # Execution Scope Enforcement — authoritative scope from ExecutionPlan.
        self._scope_resolver: ExecutionScopeResolver | None = None
        self._scope_trace: list[dict[str, Any]] = []
        self._stopped = False

        # Goal Completion Engine state
        self._crawl_phase: CrawlPhase = CrawlPhase.DISCOVERY
        self._goal_achieved: bool = False
        self._goal_criteria_met: list[str] = []

        # Crawl state
        self._visited_urls: set[str] = set()
        self._queued_urls: set[str] = set()
        self._visited_pages: list[PageRecord] = []
        self._navigation_edges: list[NavigationEdge] = []
        self._assets: dict[str, list[AssetRecord]] = {
            "stylesheets": [],
            "scripts": [],
            "images": [],
            "fonts": [],
        }
        self._redirects: list[RedirectRecord] = []
        self._cookies: list[CookieRecord] = []
        self._warnings: list[CrawlEvent] = []
        self._errors: list[CrawlEvent] = []
        self._page_map: dict[str, UUID] = {}
        self._page_ids_by_url: dict[str, UUID] = {}
        self._screenshot_page_ids: set[UUID] = set()
        self._screenshots: list[ScreenshotRecord] = []
        self._timed_out_pages: set[str] = set()
        self._pages_skipped = 0
        self._authenticated = False
        self._auth_page_id: UUID | None = None

        # Extracted DOM elements (populated by _visit_page, consumed by _build_crawl_package)
        self._extracted_forms: list[FormRecord] = []
        self._extracted_inputs: list[InputRecord] = []
        self._extracted_buttons: list[ButtonRecord] = []
        self._extracted_checkboxes: list[CheckboxRecord] = []
        self._extracted_radios: list[RadioRecord] = []
        self._extracted_dropdowns: list[DropdownRecord] = []
        self._extracted_tables: list[TableRecord] = []
        self._extracted_dialogs: list[DialogRecord] = []
        self._extracted_uploads: list[UploadRecord] = []

        # Statistics
        self._response_times: list[int] = []
        self._status_codes: dict[str, int] = {}
        self._content_types: dict[str, int] = {}
        self._bytes_downloaded: int = 0
        self._crawl_lock = asyncio.Lock()

    def _reset_state(self) -> None:
        """Reset internal crawl state for a new crawl run."""
        self._stopped = False
        self._visited_urls.clear()
        self._queued_urls.clear()
        self._visited_pages.clear()
        self._navigation_edges.clear()
        self._assets = {"stylesheets": [], "scripts": [], "images": [], "fonts": []}
        self._redirects.clear()
        self._cookies.clear()
        self._warnings.clear()
        self._errors.clear()
        self._page_map.clear()
        self._page_ids_by_url.clear()
        self._screenshot_page_ids.clear()
        self._screenshots.clear()
        self._timed_out_pages.clear()
        self._pages_skipped = 0
        self._authenticated = False
        self._auth_page_id = None
        self._extracted_forms.clear()
        self._extracted_inputs.clear()
        self._extracted_buttons.clear()
        self._extracted_checkboxes.clear()
        self._extracted_radios.clear()
        self._extracted_dropdowns.clear()
        self._extracted_tables.clear()
        self._extracted_dialogs.clear()
        self._extracted_uploads.clear()
        self._response_times.clear()
        self._status_codes.clear()
        self._content_types.clear()
        self._bytes_downloaded = 0
        self._scope_trace.clear()
        self._crawl_phase = CrawlPhase.DISCOVERY
        self._goal_achieved = False
        self._goal_criteria_met.clear()
        if self._scope_resolver is not None:
            self._scope_resolver.reset_completion_state()

    async def _mark_goal_achieved(self, result: Any, eid: str | None) -> None:
        """Mark goal as achieved, set phase to GOAL_COMPLETION, stop BFS and emit event."""
        self._goal_achieved = True
        self._crawl_phase = CrawlPhase.GOAL_COMPLETION
        self._goal_criteria_met = getattr(result, "matched_criteria", []) or []
        self._stopped = True
        reason = getattr(result, "reason", "")
        self.logger.info("goal_completion_achieved", criteria=self._goal_criteria_met, reason=reason)
        if eid:
            await emit(eid, EventType.GOAL_COMPLETED, {
                "criteria_met": self._goal_criteria_met,
                "reason": reason,
            })
            await emit(eid, EventType.CRAWL_PHASE_CHANGED, {
                "phase": CrawlPhase.GOAL_COMPLETION,
            })

    def _page_observations(self) -> dict[str, Any]:
        """Gather lightweight supporting evidence buckets for the current crawl state.

        These are supporting observations only — they never declare goal
        completion by themselves. The GoalCompletionEngine decides whether the
        observed transitions satisfy the plan's ExpectedStateGraph.
        """
        return {
            "dom": {
                "form_count": len(self._extracted_forms),
                "input_count": len(self._extracted_inputs),
                "button_count": len(self._extracted_buttons),
                "table_count": len(self._extracted_tables),
                "dialog_count": len(self._extracted_dialogs),
            },
            "network": [
                {"status": code} for code in self._status_codes.values()
            ],
            "storage": {
                "cookie_count": len(self._cookies),
            },
            "accessibility": {"visible_dialogs": len(self._extracted_dialogs)},
        }

    async def initialize(self) -> None:
        """Initialize service resources."""
        self.logger.info("crawler_service_initializing")
        await self.browser_manager.initialize()
        self.logger.info("crawler_service_initialized")

    async def cleanup(self) -> None:
        """Cleanup service resources."""
        self.logger.info("crawler_service_cleaning_up")
        await self.browser_manager.cleanup()
        self.logger.info("crawler_service_cleaned_up")

    async def crawl(self, request: CrawlRequest) -> CrawlPackage:
        """Run one crawl at a time because crawl state is instance-owned."""
        async with self._crawl_lock:
            return await self._crawl_impl(request)

    async def _crawl_impl(self, request: CrawlRequest) -> CrawlPackage:
        start_time = datetime.now(UTC)
        crawl_status = "completed"
        run_id_str = str(request.run_id)
        self._event_run_id = run_id_str

        try:
            self.logger.info("crawl_started", run_id=run_id_str, target_url=request.target_url)

            self._reset_state()
            await emit(run_id_str, EventType.CRAWLER_STARTED, {"target_url": request.target_url})

            if not self.browser_manager.is_initialized:
                await emit(run_id_str, EventType.BROWSER_LAUNCHING, {})
                await self.browser_manager.initialize()
                await emit(run_id_str, EventType.BROWSER_INITIALIZED, {})

            workspace = Path(request.workspace_path)
            artifacts_dir = workspace / "artifacts"
            screenshots_dir = workspace / "screenshots"
            contracts_dir = workspace / "contracts"
            artifacts_dir.mkdir(parents=True, exist_ok=True)
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            contracts_dir.mkdir(parents=True, exist_ok=True)
            # Make screenshots_dir accessible to _perform_login
            self._screenshots_dir = str(screenshots_dir)

            har_path = artifacts_dir / "crawl.har"

            context = await self.browser_manager.create_context(
                record_har=True, har_path=har_path, timeout=request.timeout,
            )
            await emit(run_id_str, EventType.BROWSER_CONTEXT_CREATED, {})

            try:
                # Phase 5/6: attempt login if credentials are available
                post_login_url: str | None = None
                if self._auth_context and self._auth_context.is_populated():
                    login_succeeded, post_login_url = await self._perform_login(context)
                    if login_succeeded:
                        self._authenticated = True
                        # Record authentication as chronological evidence. A
                        # successful authenticate() does NOT imply GOAL_COMPLETED —
                        # the intent-derived ExpectedStateGraph decides whether
                        # authentication is a prerequisite, the goal, or neither.
                        if self._scope_resolver is not None:
                            self._scope_resolver.record_action(
                                "authenticate",
                                url=post_login_url,
                                auth_succeeded=True,
                            )
                        await emit(run_id_str, EventType.STAGE_STARTED, {
                            "stage": "crawler_auth", "label": "Authentication",
                        })
                    else:
                        self._warnings.append(
                            CrawlEvent(
                                code="AUTH_FAILED",
                                message="Login failed — crawling will be limited to publicly accessible pages",
                                url=request.target_url,
                                timestamp=datetime.now(UTC),
                            )
                        )

                # Seed the crawl with the target URL and, if different, the post-login landing page.
                seed_urls: list[str] = []
                if post_login_url and post_login_url != request.target_url:
                    seed_urls.append(post_login_url)
                    self.logger.info("seeding_post_login_url", post_login_url=post_login_url)
                    if self._scope_resolver is not None:
                        decision = self._scope_resolver.evaluate(post_login_url)
                        if not decision.allowed:
                            self._log_scope_decision(
                                post_login_url,
                                allowed=True,
                                reason="Required after login verification — not added to crawl scope.",
                                kind="seed",
                            )
                elif post_login_url and post_login_url == request.target_url:
                    self.logger.warning("login_did_not_redirect", login_url=request.target_url,
                                        hint="Credentials may be invalid or the app requires SSO/MFA.")

                # If login failed and the target URL is a login page, redirect crawl
                # to the app root so we still try to discover pages behind auth.
                if not post_login_url and self._is_login_url(request.target_url):
                    root_url = self._derive_root_url(request.target_url)
                    self.logger.info("redirecting_crawl_from_login_to_root",
                                     login_url=request.target_url, root_url=root_url)
                    if root_url != request.target_url:
                        seed_urls.append(root_url)

                if not seed_urls:
                    seed_urls = [request.target_url]

                # Execute breadth-first crawl
                await self._crawl_bfs(
                    context=context,
                    start_url=request.target_url,
                    seed_urls=seed_urls,
                    max_depth=request.max_depth,
                    max_pages=request.max_pages,
                    page_timeout_ms=request.timeout,
                    max_retries=request.max_retries,
                    screenshots_dir=screenshots_dir if request.screenshot else None,
                )

                if self._timed_out_pages:
                    crawl_status = "timeout"
                elif self._errors:
                    crawl_status = "partial"

                # Raise error if no pages were visited
                if not self._visited_pages:
                    raise ServiceError(
                        f"Crawl failed: no pages could be visited starting from {request.target_url}"
                    )

                # Collect session information
                await self._collect_session_info(context)

            finally:
                # Close context (finalizes HAR)
                await self.browser_manager.close_context(context)

            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            # Build crawl package
            crawl_package = self._build_crawl_package(
                request=request,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                status=crawl_status,
            )

            # Save crawl-package.json
            package_path = contracts_dir / "crawl-package.json"
            await save_file(package_path, crawl_package.model_dump(mode="json", by_alias=True))

            if self._event_run_id:
                await emit(self._event_run_id, EventType.CRAWL_COMPLETED, {
                    "pages_visited": len(self._visited_pages), "duration_ms": duration_ms,
                    "total_links": len(self._navigation_edges),
                    "forms_found": sum(1 for p in self._visited_pages if p.content_type and "form" in p.content_type),
                })

            self.logger.info("crawl_completed", run_id=str(request.run_id), pages_visited=len(self._visited_pages), duration_ms=duration_ms)

            return crawl_package

        except Exception as e:
            end_time = datetime.now(UTC)
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            self.logger.error(
                "crawl_failed",
                run_id=str(request.run_id),
                error=str(e),
            )

            # Record error
            self._errors.append(
                CrawlEvent(
                    code="CRAWL_FATAL_ERROR",
                    message=f"Crawl failed: {str(e)}",
                    timestamp=datetime.now(UTC),
                )
            )

            # Build partial package
            crawl_package = self._build_crawl_package(
                request=request,
                start_time=start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                status="error",
            )

            # Try to save partial results
            try:
                workspace = Path(request.workspace_path)
                contracts_dir = workspace / "contracts"
                contracts_dir.mkdir(parents=True, exist_ok=True)
                package_path = contracts_dir / "crawl-package.json"
                await save_file(package_path, crawl_package.model_dump(mode="json", by_alias=True))
            except Exception as save_error:
                self.logger.error("failed_to_save_partial_package", error=str(save_error))

            raise ServiceError(f"Crawl failed: {str(e)}") from e

    async def _crawl_bfs(
        self,
        context: BrowserContext,
        start_url: str,
        max_depth: int,
        max_pages: int,
        page_timeout_ms: int,
        max_retries: int,
        screenshots_dir: Path | None,
        seed_urls: list[str] | None = None,
    ) -> None:
        """
        Execute breadth-first crawl.

        Args:
            context: Browser context
            start_url: Starting URL
            max_depth: Maximum depth
            max_pages: Maximum pages
            screenshots_dir: Screenshot output directory
            seed_urls: Optional additional URLs to seed the queue with
        """
        # Queue entries are reserved when enqueued so the same canonical URL
        # cannot be added repeatedly before its first visit starts.
        queue: list[tuple[str, int, UUID | None, UUID]] = []
        for raw_url in seed_urls or []:
            canonical_url = self._canonicalize_url(raw_url)
            if canonical_url and canonical_url not in self._queued_urls:
                allowed, reason = self._scope_decision(canonical_url)
                if not allowed:
                    self._log_scope_decision(canonical_url, allowed=True, reason=f"Seed entry URL allowed: {reason}", kind="seed")
                page_id = uuid4()
                self._queued_urls.add(canonical_url)
                self._page_ids_by_url[canonical_url] = page_id
                queue.append((canonical_url, 0, None, page_id))
        root_page_id: UUID | None = None

        while queue and len(self._visited_pages) < max_pages and not self._stopped:
            current_url, depth, parent_page_id, page_id = queue.pop(0)
            self.logger.info(
                "crawl_queue_dequeue",
                url=current_url,
                depth=depth,
                queue_size=len(queue),
                visited_count=len(self._visited_pages),
            )

            # Skip if already visited
            if current_url in self._visited_urls:
                self._pages_skipped += 1
                self.logger.info("crawl_url_skipped_duplicate", url=current_url)
                continue

            # Skip if max depth exceeded
            if depth > max_depth:
                self._pages_skipped += 1
                self._warnings.append(
                    CrawlEvent(
                        code="MAX_DEPTH_REACHED",
                        message=f"Skipped {current_url} (depth {depth} > max {max_depth})",
                        url=current_url,
                        timestamp=datetime.now(UTC),
                    )
                )
                continue

            eid = self._event_run_id
            page_record: PageRecord | None = None
            page: Page | None = None
            last_error: Exception | None = None
            for attempt in range(max_retries + 1):
                try:
                    page_record, page = await asyncio.wait_for(
                        self._visit_page(
                            context=context,
                            url=current_url,
                            depth=depth,
                            parent_page_id=parent_page_id,
                            page_id=page_id,
                            screenshots_dir=screenshots_dir,
                            timeout_ms=page_timeout_ms,
                            keep_page=True,
                        ),
                        timeout=(page_timeout_ms / 1000) + 2,
                    )
                    self._timed_out_pages.discard(current_url)
                    break
                except TimeoutError as exc:
                    last_error = exc
                    self._timed_out_pages.add(current_url)
                    self.logger.warning(
                        "crawl_page_timeout",
                        url=current_url,
                        timeout_ms=page_timeout_ms,
                        attempt=attempt,
                    )
                    if eid:
                        await emit(eid, EventType.PAGE_FAILED, {
                            "url": current_url,
                            "error": "page timeout",
                            "attempt": attempt,
                        })
                except Exception as exc:
                    last_error = exc
                    self.logger.warning(
                        "crawl_page_attempt_failed",
                        url=current_url,
                        attempt=attempt,
                        max_retries=max_retries,
                        error=str(exc),
                    )
                if attempt < max_retries:
                    if eid:
                        await emit(eid, EventType.BROWSER_ACTION, {
                            "action": "retry",
                            "url": current_url,
                            "attempt": attempt + 1,
                            "label": "Retrying page",
                        })
                    await asyncio.sleep(min(0.25 * (attempt + 1), 1.0))

            if page_record is None or page is None:
                code = "PAGE_TIMEOUT" if current_url in self._timed_out_pages else "PAGE_VISIT_FAILED"
                if current_url in self._timed_out_pages:
                    await self._capture_timeout_artifacts(
                        context=context,
                        url=current_url,
                        page_id=page_id,
                        timeout_ms=page_timeout_ms,
                        screenshots_dir=screenshots_dir,
                    )
                self._errors.append(CrawlEvent(
                    code=code,
                    message=f"Failed to visit {current_url}: {last_error}",
                    url=current_url,
                    timestamp=datetime.now(UTC),
                ))
                if eid:
                    await emit(eid, EventType.PAGE_FAILED, {
                        "url": current_url,
                        "error": str(last_error),
                        "retries": max_retries,
                    })
                continue

            try:
                if eid:
                    await emit(eid, EventType.PAGE_VISITED, {
                        "url": page_record.url, "title": page_record.title,
                        "status_code": page_record.status_code, "depth": depth,
                        "response_time": page_record.response_time,
                        "queue_size": len(queue), "pages_so_far": len(self._visited_pages) + 1,
                    })

                if root_page_id is None:
                    root_page_id = page_record.page_id

                # Execution Scope — post-visit verification using the page title,
                # route learning, and stopping-condition checks. A page that fails
                # title-level verification is never added to the crawl package.
                scope_skip_reason: str | None = None
                if self._scope_resolver is not None:
                    post_allowed, post_reason = self._scope_decision(
                        page_record.url, title=page_record.title
                    )
                    if not post_allowed:
                        scope_skip_reason = post_reason
                    else:
                        self._scope_resolver.learn(page_record.url, title=page_record.title)
                        self._log_scope_decision(
                            page_record.url, allowed=True, reason=post_reason, kind="page"
                        )
                        stop_condition = self._scope_resolver.stopping_condition_hit(
                            page_record.url, title=page_record.title
                        )
                        if stop_condition:
                            self._stopped = True
                            self._log_scope_decision(
                                page_record.url,
                                allowed=True,
                                reason=f"Stopping condition satisfied after {stop_condition}.",
                                kind="stop",
                            )
                        elif not self._goal_achieved:
                            completion = self._scope_resolver.evaluate_completion(
                                url=page_record.url,
                                title=page_record.title,
                                auth_succeeded=self._authenticated,
                                capability="page_visit",
                                observations=self._page_observations(),
                            )
                            if completion.satisfied:
                                await self._mark_goal_achieved(completion, eid)

                if scope_skip_reason:
                    self._log_scope_decision(
                        page_record.url, allowed=False, reason=scope_skip_reason, kind="page"
                    )
                    continue

                self._visited_urls.add(current_url)
                self._visited_urls.add(self._canonicalize_url(page_record.url))
                self._visited_pages.append(page_record)
                self._page_map[current_url] = page_record.page_id
                self._page_map[page_record.url] = page_record.page_id

                if self._goal_achieved:
                    queue.clear()
                    break

                if depth < max_depth and not self._stopped:
                    links = await self._extract_links(page, page_record.url)
                    links.extend(await self._discover_dynamic_links(page, page_record.url))
                    links = list(dict.fromkeys(links))
                    self.logger.info("navigation_links_discovered", url=page_record.url, count=len(links))
                    discovered = 0
                    duplicate_count = 0
                    for raw_link_url, link_text in links:
                        link_url = self._canonicalize_url(raw_link_url)
                        if not link_url:
                            continue
                        allowed, reason = self._scope_decision(link_url)
                        if not allowed:
                            self._log_scope_decision(link_url, allowed=False, reason=reason, kind="link")
                            continue
                        target_page_id = self._page_ids_by_url.get(link_url)
                        if target_page_id is None:
                            target_page_id = uuid4()
                            self._page_ids_by_url[link_url] = target_page_id
                        self._page_map.setdefault(link_url, target_page_id)
                        self._navigation_edges.append(NavigationEdge(
                            source_page_id=page_record.page_id,
                            target_page_id=target_page_id,
                            link_text=link_text,
                            link_url=link_url,
                            relationship="navigation",
                        ))
                        if link_url in self._queued_urls or link_url in self._visited_urls:
                            duplicate_count += 1
                            continue
                        self._queued_urls.add(link_url)
                        queue.append((link_url, depth + 1, page_record.page_id, target_page_id))
                        discovered += 1
                    await self._extract_assets(page, page_record.url, page_record.page_id)
                    self.logger.info(
                        "crawl_links_processed",
                        url=page_record.url,
                        discovered=discovered,
                        duplicates=duplicate_count,
                        queue_size=len(queue),
                    )
                    if eid:
                        await emit(eid, EventType.LINKS_EXTRACTED, {
                            "url": page_record.url,
                            "count": len(links),
                            "discovered": discovered,
                            "duplicates": duplicate_count,
                        })
                        await emit(eid, EventType.QUEUE_UPDATED, {"queue_size": len(queue)})

                if eid:
                    await emit(eid, EventType.PAGE_COMPLETED, {
                        "url": page_record.url, "title": page_record.title,
                        "pages_visited": len(self._visited_pages), "queue_size": len(queue),
                    })
            finally:
                await page.close()

        if not self._goal_achieved:
            self._crawl_phase = CrawlPhase.CRAWL_COMPLETION
            if eid:
                await emit(eid, EventType.CRAWL_PHASE_CHANGED, {
                    "phase": CrawlPhase.CRAWL_COMPLETION,
                })

    async def _visit_page(
        self,
        context: BrowserContext,
        url: str,
        depth: int,
        parent_page_id: UUID | None,
        screenshots_dir: Path | None,
        page_id: UUID | None = None,
        timeout_ms: int = 30000,
        keep_page: bool = False,
    ) -> tuple[PageRecord, Page] | PageRecord:
        """
        Visit single page and collect metadata.

        Args:
            context: Browser context
            url: Page URL
            depth: Crawl depth
            parent_page_id: Parent page ID
            screenshots_dir: Screenshot directory

        Returns:
            Page record

        Raises:
            BrowserError: If page visit fails
        """
        self.logger.info("visiting_page", url=url, depth=depth)

        page = await self.browser_manager.new_page(context)
        page_id = page_id or uuid4()
        discovered_at = datetime.now(UTC)
        eid = self._event_run_id
        page_completed = False
        console_logs: list[dict[str, str]] = []
        page_errors: list[str] = []
        request_failures: list[dict[str, str | None]] = []
        response_failures: list[dict[str, str | int]] = []
        diagnostics_dir = screenshots_dir.parent / "artifacts" / "pages" if screenshots_dir else None

        page.on("console", lambda msg: console_logs.append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda exc: page_errors.append(str(exc)))
        page.on("requestfailed", lambda req: request_failures.append({
            "url": req.url,
            "method": req.method,
            "failure": req.failure,
        }))
        page.on("response", lambda response: response_failures.append({
            "url": response.url,
            "status": response.status,
        }) if response.status >= 400 else None)

        async def _frame(action: str, url: str = url):
            """Take a lightweight frame screenshot and emit as BROWSER_FRAME."""
            if not eid:
                return
            try:
                ts = datetime.now(UTC).isoformat()
                title = await page.title()
                timestamp = int(datetime.now(UTC).timestamp() * 1000)
                frame_filename = f"frame_{page_id}_{timestamp}.png"
                frame_path = Path(screenshots_dir) / frame_filename if screenshots_dir else None
                if frame_path:
                    await page.screenshot(path=str(frame_path), full_page=False)
                    await emit(eid, EventType.BROWSER_FRAME, {
                        "filename": frame_filename, "url": url, "title": title,
                        "action": action, "timestamp": ts,
                    })
            except Exception:
                pass

        try:
            start_time = datetime.now(UTC)

            # Action: Goto URL
            if eid: await emit(eid, EventType.PAGE_NAVIGATION_STARTED, {"url": url, "depth": depth})
            if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "goto", "target": url, "label": "Opening URL"})
            response = await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

            # Action: Wait for load
            if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "wait_for_load", "target": url, "label": "Waiting for page to load"})
            if eid: await emit(eid, EventType.DOM_CONTENT_LOADED, {"url": url, "depth": depth})
            # Do not wait for networkidle: SPAs and polling/WebSocket pages may
            # never become idle. DOMContentLoaded is the bounded crawl barrier.
            if eid: await emit(eid, EventType.PAGE_LOADED, {"url": url, "depth": depth, "status_code": response.status if response else 0})
            end_time = datetime.now(UTC)

            if not response:
                raise BrowserError(f"No response from {url}")

            response_time = int((end_time - start_time).total_seconds() * 1000)
            self._response_times.append(response_time)
            status_code = response.status
            self._status_codes[str(status_code)] = self._status_codes.get(str(status_code), 0) + 1

            # Action: Get title
            if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "read_title", "label": "Reading page title"})
            title = await page.title()
            headers = response.headers
            content_type = headers.get("content-type", "unknown")
            self._content_types[content_type] = self._content_types.get(content_type, 0) + 1

            # Action: Extract HTML
            if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "extract_html", "label": "Extracting page HTML"})
            content = await response.body()
            content_length = len(content)
            self._bytes_downloaded += content_length
            if eid: await emit(eid, EventType.HTML_EXTRACTED, {"url": url, "bytes": content_length})

            # Action: Extract DOM elements
            extracted = {"inputs": [], "buttons": [], "checkboxes": [], "radios": [], "dropdowns": [], "forms": [], "tables": [], "dialogs": [], "uploads": []}
            try:
                if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "extract_dom", "label": "Extracting page elements"})
                extracted = await extract_all(page)
                if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "process_elements", "label": "Processing extracted elements"})
            except Exception as ex:
                self.logger.warning("dom_extraction_failed", url=url, error=str(ex))

            # Populate CrawlPackage records from extracted data
            form_records: list[FormRecord] = []
            for f in extracted.get("forms", []):
                form_records.append(FormRecord(
                    page_id=page_id,
                    form_id=f.get("id") or f.get("name"),
                    action=f.get("action"),
                    method=f.get("method"),
                    label=f.get("label"),
                ))
            self._extracted_forms.extend(form_records)

            input_records: list[InputRecord] = []
            for inp in extracted.get("inputs", []):
                input_records.append(InputRecord(
                    page_id=page_id,
                    input_type=inp.get("inputType", "text"),
                    name=inp.get("name"),
                    label=inp.get("label"),
                    placeholder=inp.get("placeholder"),
                    required=inp.get("required", False),
                    disabled=inp.get("disabled", False),
                    max_length=inp.get("maxLength"),
                ))
            self._extracted_inputs.extend(input_records)

            btn_records: list[ButtonRecord] = []
            for btn in extracted.get("buttons", []):
                btype = btn.get("buttonType", "button")
                if btype not in ("submit", "reset", "button", "menu"):
                    btype = "button"
                btn_records.append(ButtonRecord(
                    page_id=page_id,
                    text=btn.get("text"),
                    button_type=btype,
                    disabled=btn.get("disabled", False),
                ))
            self._extracted_buttons.extend(btn_records)

            for c in extracted.get("checkboxes", []):
                self._extracted_checkboxes.append(CheckboxRecord(
                    page_id=page_id,
                    name=c.get("name"),
                    label=c.get("label"),
                    checked=c.get("checked", False),
                    required=c.get("required", False),
                ))

            for r in extracted.get("radios", []):
                self._extracted_radios.append(RadioRecord(
                    page_id=page_id,
                    name=r.get("name"),
                    label=r.get("label"),
                    value=r.get("value"),
                    checked=r.get("checked", False),
                ))

            for d in extracted.get("dropdowns", []):
                self._extracted_dropdowns.append(DropdownRecord(
                    page_id=page_id,
                    name=d.get("name"),
                    label=d.get("label"),
                    options=d.get("options", []),
                    multiple=d.get("multiple", False),
                ))

            for t in extracted.get("tables", []):
                self._extracted_tables.append(TableRecord(
                    page_id=page_id,
                    table_id=t.get("id"),
                    caption=t.get("caption"),
                    headers=t.get("headers", []),
                    row_count=t.get("rowCount", 0),
                    column_count=t.get("columnCount", 0),
                ))

            for d in extracted.get("dialogs", []):
                dtype = d.get("dialogType", "modal")
                if dtype not in ("alert", "confirm", "prompt", "modal", "popup"):
                    dtype = "modal"
                self._extracted_dialogs.append(DialogRecord(
                    page_id=page_id,
                    dialog_type=dtype,
                    title=d.get("title"),
                    message=d.get("message"),
                    trigger_element=d.get("triggerElement"),
                ))

            for u in extracted.get("uploads", []):
                self._extracted_uploads.append(UploadRecord(
                    page_id=page_id,
                    name=u.get("name"),
                    label=u.get("label"),
                    accept=u.get("accept", []),
                    multiple=u.get("multiple", False),
                    required=u.get("required", False),
                ))

            # Emit counts
            form_count = len(extracted.get("forms", []))
            button_count = len(extracted.get("buttons", []))
            input_count = len(extracted.get("inputs", []))
            if eid and form_count:
                await emit(eid, EventType.FORMS_DETECTED, {"url": url, "count": form_count, "total": len(self._visited_pages) + 1})
            if eid and button_count:
                await emit(eid, EventType.BUTTONS_DETECTED, {"url": url, "count": button_count, "total": len(self._visited_pages) + 1})
            if eid and input_count:
                await emit(eid, EventType.INPUTS_DETECTED, {"url": url, "count": input_count, "total": len(self._visited_pages) + 1})

            # Capture final screenshot
            if screenshots_dir:
                if eid: await emit(eid, EventType.BROWSER_ACTION, {"action": "screenshot", "label": "Taking primary screenshot"})
                screenshot_filename = f"{page_id}.png"
                screenshot_path = screenshots_dir / screenshot_filename
                try:
                    if not screenshot_path.exists():
                        await self.browser_manager.screenshot(page, screenshot_path, full_page=True)
                    if page_id not in self._screenshot_page_ids:
                        viewport = page.viewport_size or {}
                        self._screenshots.append(ScreenshotRecord(
                            page_id=page_id,
                            url=page.url,
                            path=str(screenshot_path),
                            captured_at=datetime.now(UTC),
                            width=int(viewport.get("width", 0)),
                            height=int(viewport.get("height", 0)),
                        ))
                        self._screenshot_page_ids.add(page_id)
                    if eid:
                        await emit(eid, EventType.SCREENSHOT_CAPTURED, {
                            "url": url, "title": title, "filename": screenshot_filename,
                            "depth": depth, "response_time": response_time,
                        })
                except Exception as screenshot_error:
                    self.logger.warning("primary_screenshot_failed", url=url, error=str(screenshot_error))
                    self._warnings.append(CrawlEvent(
                        code="SCREENSHOT_FAILED",
                        message=f"Screenshot failed for {url}: {screenshot_error}",
                        page_id=page_id,
                        url=url,
                        timestamp=datetime.now(UTC),
                    ))

            page_record = PageRecord(
                page_id=page_id,
                url=self._canonicalize_url(page.url) or url,
                title=title if title else None,
                status_code=status_code,
                content_type=content_type if content_type else None,
                content_length=content_length,
                response_time=response_time,
                depth=depth,
                parent_page_id=parent_page_id,
                discovered_at=discovered_at,
                cached_content_path=f"pages/{page_id}.html",
            )

            self.logger.info(
                "page_visited",
                url=url,
                status=status_code,
                response_time=response_time,
            )

            page_completed = True
            return (page_record, page) if keep_page else page_record

        finally:
            if diagnostics_dir and (console_logs or page_errors or request_failures or response_failures):
                try:
                    await save_file(diagnostics_dir / f"{page_id}.diagnostics.json", {
                        "url": url,
                        "console": console_logs,
                        "page_errors": page_errors,
                        "request_failures": request_failures,
                        "response_failures": response_failures,
                    })
                except Exception as diagnostics_error:
                    self.logger.warning("page_diagnostics_save_failed", url=url, error=str(diagnostics_error))
            if not keep_page or not page_completed:
                await page.close()

    async def _capture_timeout_artifacts(
        self,
        context: BrowserContext,
        url: str,
        page_id: UUID,
        timeout_ms: int,
        screenshots_dir: Path | None,
    ) -> None:
        """Capture bounded evidence for a page that exhausted its retries."""
        page = await self.browser_manager.new_page(context)
        diagnostics: dict[str, Any] = {
            "url": url,
            "console": [],
            "page_errors": [],
            "request_failures": [],
            "response_failures": [],
        }
        page.on("console", lambda msg: diagnostics["console"].append({"type": msg.type, "text": msg.text}))
        page.on("pageerror", lambda exc: diagnostics["page_errors"].append(str(exc)))
        page.on("requestfailed", lambda req: diagnostics["request_failures"].append({
            "url": req.url, "method": req.method, "failure": req.failure,
        }))
        page.on("response", lambda response: diagnostics["response_failures"].append({
            "url": response.url, "status": response.status,
        }) if response.status >= 400 else None)
        try:
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            except Exception as navigation_error:
                diagnostics["navigation_error"] = str(navigation_error)
            if screenshots_dir:
                try:
                    await self.browser_manager.screenshot(
                        page, screenshots_dir / f"{page_id}.timeout.png", full_page=True,
                    )
                except Exception as screenshot_error:
                    diagnostics["screenshot_error"] = str(screenshot_error)
            try:
                html = await page.content()
                if screenshots_dir:
                    html_path = screenshots_dir.parent / "artifacts" / "pages" / f"{page_id}.timeout.html"
                    html_path.parent.mkdir(parents=True, exist_ok=True)
                    import aiofiles
                    async with aiofiles.open(html_path, "w", encoding="utf-8") as html_file:
                        await html_file.write(html)
                    diagnostics["html_path"] = str(html_path)
            except Exception as html_error:
                diagnostics["html_error"] = str(html_error)
            if screenshots_dir:
                await save_file(
                    screenshots_dir.parent / "artifacts" / "pages" / f"{page_id}.timeout.json",
                    diagnostics,
                )
        except Exception as evidence_error:
            self.logger.warning("timeout_artifact_capture_failed", url=url, error=str(evidence_error))
        finally:
            await page.close()

    async def _extract_links(self, page: Page, base_url: str) -> list[tuple[str, str]]:
        """
        Extract links from page.

        Args:
            page: Page to extract links from
            base_url: Base URL for resolution

        Returns:
            List of (url, link_text) tuples
        """
        try:
            # Extract normal anchors and route-bearing elements used by SPAs.
            links = await page.eval_on_selector_all(
                "a[href], [role='link'][href], [data-href], [data-url], [data-route], [routerlink]",
                """
                (elements) => elements.map(el => ({
                    href: el.getAttribute('href') || el.getAttribute('data-href') ||
                          el.getAttribute('data-url') || el.getAttribute('data-route') ||
                          el.getAttribute('routerlink'),
                    text: el.innerText?.trim() || el.textContent?.trim() || ''
                }))
                """,
            )

            parsed_base = urlparse(base_url)
            base_domain = parsed_base.netloc

            result: list[tuple[str, str]] = []

            for link in links:
                href = link.get("href", "")
                text = link.get("text", "")[:512]

                # Resolve relative URLs
                absolute_url = urljoin(base_url, href)
                parsed = urlparse(absolute_url)

                # Filter: only same domain, http/https
                if parsed.scheme in ("http", "https") and parsed.netloc == base_domain:
                    # Normalize: remove fragment
                    normalized = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
                    if parsed.query:
                        normalized += f"?{parsed.query}"

                    result.append((normalized, text))

            return result

        except Exception as e:
            self.logger.warning("link_extraction_failed", error=str(e))
            return []

    async def _discover_dynamic_links(self, page: Page, base_url: str) -> list[tuple[str, str]]:
        """Discover routes exposed only through SPA navigation controls."""
        try:
            candidates = await page.locator(
                "nav button:visible, [role='navigation'] button:visible, "
                "aside button:visible, header button:visible, "
                "nav [role='link']:visible, aside [role='link']:visible, "
                "nav [role='menuitem']:visible, aside [role='menuitem']:visible"
            ).all()
            discovered: list[tuple[str, str]] = []
            parsed_base = urlparse(base_url)

            for button in candidates[:30]:
                try:
                    label = (await button.inner_text()).strip()
                    lowered = label.lower()
                    if not label or any(word in lowered for word in (
                        "logout", "log out", "delete", "remove", "submit", "save",
                    )):
                        continue

                    before = page.url
                    await button.click(timeout=1500)
                    await page.wait_for_timeout(300)
                    after = page.url

                    if after != before:
                        parsed = urlparse(after)
                        if parsed.scheme in ("http", "https") and parsed.netloc == parsed_base.netloc:
                            discovered.append((after.split("#", 1)[0], label))

                    menu_links = await self._extract_links(page, before)
                    discovered.extend(menu_links)
                    await page.keyboard.press("Escape")
                    if page.url != before:
                        await page.go_back(wait_until="domcontentloaded", timeout=5000)
                except Exception:
                    continue

            return list(dict.fromkeys(discovered))
        except Exception as e:
            self.logger.warning("dynamic_link_discovery_failed", error=str(e))
            return []

    async def _extract_assets(self, page: Page, base_url: str, page_id: UUID) -> None:
        """
        Extract assets from page.

        Args:
            page: Page to extract from
            base_url: Base URL
            page_id: Current page ID
        """
        try:
            parsed_base = urlparse(base_url)
            base_domain = parsed_base.netloc

            # Extract stylesheets
            css_links = await page.eval_on_selector_all(
                "link[rel='stylesheet']",
                "(elements) => elements.map(el => el.getAttribute('href'))",
            )
            for href in css_links:
                if href:
                    absolute_url = urljoin(base_url, href)
                    parsed = urlparse(absolute_url)
                    self._assets["stylesheets"].append(
                        AssetRecord(
                            url=absolute_url,
                            type="text/css",
                            external=parsed.netloc != base_domain,
                            first_seen_on_page_id=page_id,
                        )
                    )

            # Extract scripts
            script_srcs = await page.eval_on_selector_all(
                "script[src]",
                "(elements) => elements.map(el => el.getAttribute('src'))",
            )
            for src in script_srcs:
                if src:
                    absolute_url = urljoin(base_url, src)
                    parsed = urlparse(absolute_url)
                    self._assets["scripts"].append(
                        AssetRecord(
                            url=absolute_url,
                            type="application/javascript",
                            external=parsed.netloc != base_domain,
                            first_seen_on_page_id=page_id,
                        )
                    )

            # Extract images
            img_srcs = await page.eval_on_selector_all(
                "img[src]",
                "(elements) => elements.map(el => el.getAttribute('src'))",
            )
            for src in img_srcs:
                if src:
                    absolute_url = urljoin(base_url, src)
                    parsed = urlparse(absolute_url)
                    self._assets["images"].append(
                        AssetRecord(
                            url=absolute_url,
                            type="image/*",
                            external=parsed.netloc != base_domain,
                            first_seen_on_page_id=page_id,
                        )
                    )

        except Exception as e:
            self.logger.warning("asset_extraction_failed", error=str(e))

    async def _collect_session_info(self, context: BrowserContext) -> None:
        """
        Collect session information from context.

        Args:
            context: Browser context
        """
        try:
            # Get cookies
            cookies = await context.cookies()
            for cookie in cookies:
                self._cookies.append(
                    CookieRecord(
                        name=cookie.get("name", ""),
                        domain=cookie.get("domain", ""),
                        path=cookie.get("path"),
                        http_only=cookie.get("httpOnly", False),
                        secure=cookie.get("secure", False),
                        same_site=cookie.get("sameSite"),
                        redacted=False,
                    )
                )

        except Exception as e:
            self.logger.warning("session_info_collection_failed", error=str(e))

    def _build_crawl_package(
        self,
        request: CrawlRequest,
        start_time: datetime,
        end_time: datetime,
        duration_ms: int,
        status: str,
    ) -> CrawlPackage:
        """
        Build final crawl package.

        Args:
            request: Original request
            start_time: Crawl start time
            end_time: Crawl end time
            duration_ms: Duration in milliseconds
            status: Crawl status

        Returns:
            Complete crawl package
        """
        # Calculate statistics
        response_time_stats = ResponseTimeStats()
        if self._response_times:
            response_time_stats = ResponseTimeStats(
                average=int(sum(self._response_times) / len(self._response_times)),
                median=int(sorted(self._response_times)[len(self._response_times) // 2]),
                max=max(self._response_times),
                min=min(self._response_times),
            )

        statistics = CrawlStatistics(
            response_time_ms=response_time_stats,
            pages_by_status_code=self._status_codes,
            pages_by_content_type=self._content_types,
            unique_domains=len({urlparse(page.url).netloc for page in self._visited_pages}),
            bytes_downloaded=self._bytes_downloaded,
        )

        # Find root page
        root_page_id = self._visited_pages[0].page_id if self._visited_pages else None

        # Build package
        return CrawlPackage(
            run_id=request.run_id,
            request_id=request.request_id,
            crawl_summary=CrawlSummary(
                start_time=start_time,
                end_time=end_time,
                duration=duration_ms,
                status=status,
                pages_visited=len(self._visited_pages),
                pages_skipped=self._pages_skipped,
                total_links=len(self._navigation_edges),
                crawl_depth_reached=max((p.depth for p in self._visited_pages), default=0),
            ),
            visited_pages=self._visited_pages,
            navigation_graph=NavigationGraph(
                edges=self._navigation_edges,
                root_page_id=root_page_id,
            ),
            forms=self._extracted_forms,
            inputs=self._extracted_inputs,
            buttons=self._extracted_buttons,
            checkboxes=self._extracted_checkboxes,
            radios=self._extracted_radios,
            dropdowns=self._extracted_dropdowns,
            tables=self._extracted_tables,
            dialogs=self._extracted_dialogs,
            uploads=self._extracted_uploads,
            screenshots=self._screenshots,
            assets=AssetsCollection(
                stylesheets=self._assets["stylesheets"],
                scripts=self._assets["scripts"],
                images=self._assets["images"],
                fonts=self._assets["fonts"],
            ),
            session=SessionInfo(
                authenticated=self._authenticated,
                auth_method=(self._auth_context.auth_strategy if self._authenticated and self._auth_context else "none"),
                auth_page_id=self._auth_page_id,
                cookies=self._cookies,
                redirects=self._redirects,
            ),
            warnings=self._warnings,
            errors=self._errors,
            statistics=statistics,
            scope_trace=list(self._scope_trace),
        )

    def _reset_state(self) -> None:
        """Reset internal crawl state."""
        # NOTE: _auth_context, _exclude_patterns, _include_patterns, _scope_resolver
        # are intentionally NOT reset here — they are set per-run by CrawlerAgent
        # before calling crawl().
        self._visited_urls.clear()
        self._queued_urls.clear()
        self._visited_pages.clear()
        self._navigation_edges.clear()
        self._assets = {
            "stylesheets": [],
            "scripts": [],
            "images": [],
            "fonts": [],
        }
        self._redirects.clear()
        self._cookies.clear()
        self._warnings.clear()
        self._errors.clear()
        self._page_map.clear()
        self._page_ids_by_url.clear()
        self._screenshot_page_ids.clear()
        self._screenshots.clear()
        self._timed_out_pages.clear()
        self._pages_skipped = 0
        self._scope_trace.clear()
        self._stopped = False
        self._authenticated = False
        self._auth_page_id = None
        self._response_times.clear()
        self._status_codes.clear()
        self._content_types.clear()
        self._extracted_forms.clear()
        self._extracted_inputs.clear()
        self._extracted_buttons.clear()
        self._extracted_checkboxes.clear()
        self._extracted_radios.clear()
        self._extracted_dropdowns.clear()
        self._extracted_tables.clear()
        self._extracted_dialogs.clear()
        self._extracted_uploads.clear()
        self._bytes_downloaded = 0

    @staticmethod
    def _canonicalize_url(url: str) -> str:
        """Return one stable key for equivalent HTTP(S) URLs."""
        try:
            parts = urlsplit(url.strip())
            if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
                return ""
            host = parts.hostname.lower() if parts.hostname else ""
            port = parts.port
            if port and not ((parts.scheme.lower() == "http" and port == 80) or
                             (parts.scheme.lower() == "https" and port == 443)):
                host = f"{host}:{port}"
            path = parts.path or "/"
            while "//" in path:
                path = path.replace("//", "/")
            if path != "/":
                path = path.rstrip("/")
            query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
            fragment = parts.fragment.rstrip("/") if parts.fragment.startswith("/") else ""
            return urlunsplit((parts.scheme.lower(), host, path, query, fragment))
        except ValueError:
            return ""

    def _scope_decision(self, url: str, *, title: str | None = None) -> tuple[bool, str]:
        """
        Decide scope for a URL (with optional title), returning (allowed, reason).

        Uses the ExecutionScopeResolver when configured so ExecutionPlan is the
        single source of truth; falls back to legacy include/exclude patterns
        for backward compatibility.
        """
        if self._scope_resolver is not None:
            decision = self._scope_resolver.evaluate(url, title=title)
            return decision.allowed, decision.reason
        canonical = self._canonicalize_url(url)
        if not canonical:
            return False, "Invalid URL"
        if self._exclude_patterns:
            for pat in self._exclude_patterns:
                if re.search(pat, canonical, re.IGNORECASE):
                    return False, "Matches excluded page pattern"
        if self._include_patterns:
            for pat in self._include_patterns:
                if re.search(pat, canonical, re.IGNORECASE):
                    return True, "Matches included page pattern"
            return False, "Outside include scope"
        return True, "No include scope"

    def _should_crawl_url(self, url: str) -> bool:
        """Backward-compatible predicate — only allowed URLs enter the queue."""
        return self._scope_decision(url)[0]

    def _log_scope_decision(
        self,
        url: str,
        *,
        allowed: bool,
        reason: str,
        kind: str = "link",
    ) -> None:
        """Record a scope decision for the execution trace (Phase 9)."""
        decision = "ALLOWED" if allowed else "SKIPPED"
        self._scope_trace.append({
            "url": url,
            "decision": decision,
            "reason": reason,
            "kind": kind,
        })
        self.logger.info(
            "crawl_scope_decision",
            url=url,
            decision=decision,
            reason=reason,
            kind=kind,
        )

    async def _perform_login(self, context: BrowserContext) -> tuple[bool, str | None]:
        """
        Attempt to log in using the stored AuthContext.

        Uses Playwright's role/label-based locators first (framework-agnostic),
        then falls back to comprehensive CSS selectors, and finally tries any
        visible text/password input pair as a last resort.

        SECURITY: credentials are used directly in page.fill() calls;
        they are never written to logs or returned in any output.

        Returns:
            Tuple of (login succeeded, post-login URL or None).
            Returns (False, None) if credentials are missing, form fields
            cannot be found, or the login attempt fails.
        """
        auth = self._auth_context
        if not auth or not auth.is_populated():
            return False, None
        eid = getattr(self, "_event_run_id", None)
        try:
            login_url = auth.login_url
            if not login_url:
                self.logger.info("login_skipped_no_login_url")
                return False, None

            if eid:
                await emit(eid, EventType.STAGE_STARTED, {"stage": "authentication", "label": "Logging In"})

            # Try multiple login URL candidates if the first one doesn't have a login form
            urls_to_try = [login_url]
            parsed = urlparse(login_url)
            base = f"{parsed.scheme}://{parsed.netloc}"
            for path in ["/login", "/signin", "/sign-in", "/auth/login"]:
                candidate = urljoin(base, path)
                if candidate not in urls_to_try:
                    urls_to_try.append(candidate)

            login_succeeded = False
            post_login_url: str | None = None

            for attempt_url in urls_to_try:
                if login_succeeded:
                    break

                if eid:
                    await emit(eid, EventType.BROWSER_ACTION, {"action": "goto", "target": attempt_url, "label": f"Opening login page: {attempt_url}"})

                page = await context.new_page()
                try:
                    pre_login_url = attempt_url
                    await page.goto(attempt_url, wait_until="domcontentloaded", timeout=15000)

                    if eid:
                        await emit(eid, EventType.PAGE_LOADED, {"url": attempt_url, "depth": 0, "status_code": 200})

                    # Wait for React/SPA to render login form (critical for Next.js apps)
                    await page.wait_for_timeout(2000)

                    # Try to wait for password input to appear (strong signal of login form)
                    try:
                        await page.wait_for_selector('input[type="password"]', timeout=3000, state="visible")
                    except Exception:
                        # Fallback: wait for any input field
                        try:
                            await page.wait_for_selector('input:visible', timeout=2000)
                        except Exception:
                            pass  # Continue anyway, might be a different form structure

                    pre_login_url = page.url

                    username_field = await self._locate_username_field(page)
                    if username_field and eid:
                        await self._emit_action_with_position(eid, username_field, "fill", "Typing username / user ID...")

                    password_field = await self._locate_password_field(page)
                    if password_field and eid:
                        await self._emit_action_with_position(eid, password_field, "fill", "Typing password...")

                    if username_field and password_field:
                        await username_field.fill(auth.username or "")
                        self.logger.info("auth_username_filled", has_username=bool(auth.username))
                        await password_field.fill(auth.password or "")
                        self.logger.info("auth_password_filled", has_password=bool(auth.password))

                        submit_button = await self._locate_submit_button(page)
                        if submit_button:
                            if eid:
                                await self._emit_action_with_position(eid, submit_button, "click", "Clicking Login button...")

                            self.logger.info("auth_submit_clicked", url=pre_login_url)

                            # Phase 4.5 fix: Use proper navigation-aware submit with network inspection
                            auth_state = await self._submit_and_wait_for_auth(
                                page, submit_button, pre_login_url, eid,
                            )
                            post_login_url = auth_state["url"]
                            login_succeeded = auth_state["success"]
                            failure_reason = auth_state.get("failure_reason", AuthFailureReason.UNKNOWN_AUTH_ERROR)

                            self.logger.info(
                                "auth_result",
                                success=login_succeeded,
                                url_before=pre_login_url,
                                url_after=post_login_url,
                                url_changed=post_login_url != pre_login_url,
                                cookies=len(auth_state.get("cookies", [])),
                                has_local_storage_token=auth_state.get("local_storage_token") is not None,
                                has_session_storage_token=auth_state.get("session_storage_token") is not None,
                                status_code=auth_state.get("status_code"),
                                failure_reason=failure_reason.value if not login_succeeded else None,
                            )

                            if login_succeeded:
                                if eid and self._screenshots_dir:
                                    await self._capture_login_screenshot(page, eid, post_login_url or attempt_url)
                                if eid:
                                    await emit(eid, EventType.STAGE_COMPLETED, {"stage": "authentication", "label": "Login Successful"})
                                self.logger.info("login_succeeded", login_url=attempt_url, post_login_url=post_login_url)
                                await page.wait_for_timeout(2000)
                            else:
                                self.logger.warning("login_failed", reason=failure_reason.value, pre_login_url=pre_login_url, post_login_url=post_login_url)
                                await page.wait_for_timeout(2000)
                        else:
                            self.logger.warning("login_submit_button_not_found", url=attempt_url)
                            await page.wait_for_timeout(1000)
                    else:
                        missing = []
                        if not username_field:
                            missing.append("username")
                        if not password_field:
                            missing.append("password")
                        self.logger.info("login_fields_not_found_on_url", url=attempt_url, missing=missing)
                        await page.wait_for_timeout(1000)
                finally:
                    await page.close()

            if login_succeeded:
                return True, post_login_url

            if eid:
                await emit(eid, EventType.STAGE_FAILED, {"stage": "authentication", "error": f"Login failed: {failure_reason.value}"})
            return False, None
        except Exception as e:
            self.logger.warning("login_failed", error=str(e))
            if eid:
                await emit(eid, EventType.STAGE_FAILED, {"stage": "authentication", "error": str(e)})
            return False, None

    @staticmethod
    async def _locate_username_field(page: Page) -> Locator | None:
        try:
            field = page.get_by_role("textbox", name="username")
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_role("textbox", name="email")
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_role("textbox", name="user")
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_label("Username", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_label("Email", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_label("User ID", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_placeholder("username", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_placeholder("email", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_placeholder("user", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass

        _username_selectors = [
            'input[type="email"]',
            'input[name="email"]',
            'input[type="text"][name*="user" i]',
            'input[name="username"]',
            'input[id*="user" i]',
            'input[id*="email" i]',
            'input[id*="login" i]',
            'input[name="login"]',
            'input[id*="username" i]',
            'input[autocomplete="username"]',
            'input[autocomplete="email"]',
            'input[placeholder*="email" i]',
            'input[placeholder*="user" i]',
        ]
        for sel in _username_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue

        try:
            all_visible = page.locator('input:visible:not([type="hidden"]):not([type="submit"]):not([type="button"])'
                                        ':not([type="checkbox"]):not([type="radio"]):not([type="file"])'
                                        ':not([type="password"]):not([type="image"]):not([type="reset"])')
            count = await all_visible.count()
            if count > 0:
                return all_visible.first
        except Exception:
            pass

        return None

    @staticmethod
    async def _locate_password_field(page: Page) -> Locator | None:
        try:
            field = page.get_by_role("textbox", name="password")
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_label("Password", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_placeholder("password", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass
        try:
            field = page.get_by_placeholder("pass", exact=False)
            if await field.count() > 0:
                return field
        except Exception:
            pass

        _password_selectors = [
            'input[type="password"]',
            'input[name="password"]',
            'input[id*="pass" i]',
            'input[id*="password" i]',
            'input[autocomplete="current-password"]',
            'input[autocomplete="new-password"]',
            'input[placeholder*="password" i]',
        ]
        for sel in _password_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue

        try:
            all_pass = page.locator('input[type="password"]:visible')
            count = await all_pass.count()
            if count > 0:
                return all_pass.first
        except Exception:
            pass

        return None

    @staticmethod
    async def _locate_submit_button(page: Page) -> Locator | None:
        try:
            btn = page.get_by_role("button", name="Login")
            if await btn.count() > 0:
                return btn.first
        except Exception:
            pass
        try:
            btn = page.get_by_role("button", name="Sign in")
            if await btn.count() > 0:
                return btn.first
        except Exception:
            pass
        try:
            btn = page.get_by_role("button", name="Log in")
            if await btn.count() > 0:
                return btn.first
        except Exception:
            pass
        try:
            btn = page.get_by_role("button", name="Submit")
            if await btn.count() > 0:
                return btn.first
        except Exception:
            pass

        _submit_selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button:has-text("Login")',
            'button:has-text("Sign in")',
            'button:has-text("Log in")',
            'button:has-text("Sign In")',
            'button:has-text("Submit")',
            '[role="button"]:has-text("Login")',
            'button[class*="login" i]',
            'button[class*="submit" i]',
        ]
        for sel in _submit_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible():
                    return loc
            except Exception:
                continue

        return None

    @staticmethod
    def _is_login_url(url: str) -> bool:
        """Check if a URL looks like a login/auth page."""
        lower = url.lower()
        login_indicators = ["/login", "/signin", "/sign-in", "/sign_in",
                           "/auth", "/logon", "login?", "signin?"]
        return any(ind in lower for ind in login_indicators)

    @staticmethod
    def _derive_root_url(login_url: str) -> str:
        """Derive the application root URL from a login page URL."""
        parsed = urlparse(login_url)
        root = f"{parsed.scheme}://{parsed.netloc}/"
        qs = parse_qs(parsed.query)
        next_url = qs.get("next", [None])[0] or qs.get("redirect", [None])[0] or qs.get("return", [None])[0]
        if next_url:
            if next_url.startswith("/"):
                root = f"{parsed.scheme}://{parsed.netloc}{next_url}"
            elif next_url.startswith("http"):
                root = next_url
        return root

    @staticmethod
    async def _check_login_success(
        page: Page,
        post_login_url: str | None,
        pre_login_url: str,
        login_url: str,
    ) -> bool:
        return False  # Kept for backward compat — logic moved to _submit_and_wait_for_auth

    async def _submit_and_wait_for_auth(
        self,
        page: Page,
        submit_button: Locator,
        pre_login_url: str,
        eid: str | None,
    ) -> dict[str, Any]:
        """
        Phase 4.5 fix: Submit login form and wait for authentication to complete.

        Uses proper Playwright navigation handling, adaptive waiting, network
        inspection, cookie/storage checks, and weighted multi-signal scoring.

        Returns dict with keys: success, url, cookies, local_storage_token,
        session_storage_token, status_code, signals, failure_reason.
        """
        result: dict[str, Any] = {
            "success": False, "url": pre_login_url, "cookies": [],
            "local_storage_token": None, "session_storage_token": None,
            "status_code": None, "signals": {}, "failure_reason": AuthFailureReason.UNKNOWN_AUTH_ERROR,
        }

        # Track network responses for auth inspection
        captured_responses: list[dict[str, Any]] = []

        async def _on_response(response):
            try:
                captured_responses.append({
                    "url": response.url,
                    "status": response.status,
                    "headers": dict(response.headers) if response.headers else {},
                })
            except Exception:
                pass

        page.on("response", _on_response)

        try:
            # Step 1: Click submit with proper navigation-aware handling
            self.logger.info("auth_click_submit", pre_url=pre_login_url)
            if eid:
                await emit(eid, EventType.BROWSER_ACTION, {"action": "click", "label": "Submitting login form..."})

            try:
                async with page.expect_navigation(wait_until="domcontentloaded", timeout=30000) as nav:
                    try:
                        await submit_button.click(timeout=5000)
                    except Exception:
                        await page.keyboard.press("Enter")
                    nav_response = await nav.value
                    result["status_code"] = nav_response.status if nav_response else None
                    self.logger.info("auth_navigation_completed", status=result["status_code"], url=page.url)
                result["url"] = page.url
            except Exception:
                # No full page navigation — SPA, in-place, or redirect in progress
                self.logger.info("auth_no_full_navigation", url=page.url)

            # Step 2: Adaptive wait for auth completion
            await self._wait_for_auth_completion(page, pre_login_url)

            # Step 3: Capture current state
            result["url"] = page.url

            # Step 4: Inspect cookies, localStorage, sessionStorage, network
            auth_state = await self._inspect_auth_state(page, captured_responses)
            result.update(auth_state)

            # Step 5: Multi-signal weighted scoring
            signals = await self._evaluate_auth_signals(page, pre_login_url, result)
            result["signals"] = signals
            score = signals.get("score", 0)

            # Step 6: Determine failure reason if applicable
            failure_reason = self._determine_failure_reason(signals, result, captured_responses)
            result["failure_reason"] = failure_reason

            # Step 7: Verdict — need >= 3 weighted points (cookies 4, url_change 3, storage_token 4, etc)
            if score >= 3:
                result["success"] = True
                self.logger.info("auth_success_detected", score=score, signals=signals)
            else:
                self.logger.warning("auth_failure_detected", score=score, failure_reason=failure_reason.value, signals=signals)

            if eid:
                await emit(eid, EventType.BROWSER_ACTION, {
                    "action": "auth_check",
                    "score": score,
                    "success": result["success"],
                    "failure_reason": failure_reason.value if not result["success"] else None,
                })

        finally:
            try:
                page.remove_listener("response", _on_response)
            except Exception:
                pass

        return result

    async def _wait_for_auth_completion(
        self, page: Page, pre_login_url: str,
    ) -> None:
        """
        Adaptive wait for authentication to finish.

        Tries multiple strategies with increasing timeouts:
        1. URL change (traditional redirect) — 8s
        2. Password field disappearance (SPA form unmount) — 5s
        3. Post-login UI appearance (navbar, sidebar, logout) — 5s
        4. Network idle (all XHR/fetch completed) — 10s
        5. Hard fallback wait — 3s
        """
        strategies = [
            ("url_change", lambda: page.wait_for_url(lambda u: u != pre_login_url, timeout=8000), 0),
            ("password_hidden", lambda: page.wait_for_selector('input[type="password"]', state="hidden", timeout=5000), 0),
            ("post_login_ui", lambda: page.wait_for_selector(', '.join(_POST_LOGIN_UI_SELECTORS[:3]), timeout=5000), 0),
            ("network_idle", lambda: page.wait_for_load_state("networkidle", timeout=10000), 0),
        ]

        for name, wait_fn, _ in strategies:
            try:
                self.logger.info("auth_wait_strategy", strategy=name)
                await wait_fn()
                return
            except Exception:
                self.logger.info("auth_wait_strategy_timeout", strategy=name)
                continue

        await page.wait_for_timeout(3000)

    @staticmethod
    async def _inspect_auth_state(
        page: Page,
        captured_responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Inspect cookies, localStorage, sessionStorage, and network responses for auth evidence."""
        result: dict[str, Any] = {
            "cookies": [],
            "local_storage_token": None,
            "session_storage_token": None,
            "set_cookie_count": 0,
            "auth_status_codes": [],
        }

        # Cookies
        try:
            cookies = await page.context.cookies()
            result["cookies"] = [{"name": c["name"], "domain": c.get("domain", "")} for c in cookies]
            result["set_cookie_count"] = sum(1 for r in captured_responses if "set-cookie" in r.get("headers", {}))
        except Exception:
            pass

        # localStorage token
        try:
            for key in ["token", "auth_token", "access_token", "jwt", "id_token", "user"]:
                val = await page.evaluate(f"localStorage.getItem('{key}')")
                if val:
                    result["local_storage_token"] = key
                    break
        except Exception:
            pass

        # sessionStorage token
        try:
            for key in ["token", "auth_token", "access_token", "jwt"]:
                val = await page.evaluate(f"sessionStorage.getItem('{key}')")
                if val:
                    result["session_storage_token"] = key
                    break
        except Exception:
            pass

        # Auth status codes from captured responses
        result["auth_status_codes"] = [
            r.get("status") for r in captured_responses
            if any(k in (r.get("url") or "").lower() for k in ("/login", "/auth", "/signin", "/oauth", "/token"))
        ]

        return result

    @staticmethod
    async def _evaluate_auth_signals(
        page: Page,
        pre_login_url: str,
        auth_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Weighted multi-signal scoring for authentication success."""
        score = 0
        signals: dict[str, Any] = {}

        # Signal 1: URL changed to non-login page (strong)
        current_url = auth_state.get("url", pre_login_url)
        signals["url_changed"] = current_url != pre_login_url
        if signals["url_changed"]:
            parsed_pre = urlparse(pre_login_url)
            parsed_post = urlparse(current_url)
            if parsed_pre.path != parsed_post.path:
                score += 3
                signals["url_path_changed"] = True

        # Signal 2: Auth cookies present (strongest)
        cookies = auth_state.get("cookies") or []
        auth_cookie_names = {"session", "connect.sid", "auth", "token", "jwt", "access_token", "JSESSIONID", "PHPSESSID"}
        signals["auth_cookie_found"] = any(
            any(ak in (c.get("name") or "").lower() for ak in auth_cookie_names)
            for c in cookies
        )
        if signals["auth_cookie_found"]:
            score += 4

        # Signal 3: Token in localStorage or sessionStorage (strong)
        signals["local_storage_token"] = auth_state.get("local_storage_token")
        signals["session_storage_token"] = auth_state.get("session_storage_token")
        if signals["local_storage_token"] or signals["session_storage_token"]:
            score += 4

        # Signal 4: HTTP status code indicates auth success
        status_codes = auth_state.get("auth_status_codes") or []
        has_2xx = any(200 <= (s or 0) < 300 for s in status_codes)
        has_302 = any((s or 0) == 302 for s in status_codes)
        signals["auth_2xx_response"] = has_2xx
        signals["auth_302_redirect"] = has_302
        if has_2xx or has_302:
            score += 2

        # Signal 5: Set-Cookie headers in response
        signals["set_cookie_present"] = auth_state.get("set_cookie_count", 0) > 0
        if signals["set_cookie_present"]:
            score += 2

        # Signal 6: Title changed away from login
        try:
            title = (await page.title()).lower()
            signals["title"] = title
            signals["title_post_login"] = any(kw in title for kw in _POST_LOGIN_TITLE_KW)
            if signals["title_post_login"]:
                score += 2
            elif title and not any(k in title for k in ("login", "sign in", "signin", "log in", "authenticate")):
                score += 1
        except Exception:
            pass

        # Signal 7: Password field no longer visible
        try:
            pw_count = await page.locator('input[type="password"]:visible').count()
            signals["password_field_gone"] = pw_count == 0
            if signals["password_field_gone"]:
                score += 2
        except Exception:
            pass

        # Signal 8: Post-login UI appeared (nav, logout, profile)
        try:
            ui_detected = 0
            for sel in _POST_LOGIN_UI_SELECTORS:
                try:
                    if await page.locator(sel).count() > 0:
                        ui_detected += 1
                        if ui_detected >= 2:
                            break
                except Exception:
                    continue
            signals["post_login_ui"] = ui_detected
            if ui_detected >= 2:
                score += 3
            elif ui_detected >= 1:
                score += 1
        except Exception:
            pass

        # Signal 0 (NEGATIVE): Auth error text detected
        try:
            body = (await page.text_content("body", timeout=2000) or "").lower()
            error_matched = [p for p in _AUTH_ERROR_TEXT_PATTERNS if p in body]
            signals["auth_error_text"] = error_matched
            if error_matched:
                score -= 5  # Heavy penalty for detected auth error text
        except Exception:
            pass

        # Signal 0b (NEGATIVE): aria-invalid on a form field
        try:
            aria_invalid = await page.locator('[aria-invalid="true"]:visible').count() > 0
            signals["aria_invalid"] = aria_invalid
            if aria_invalid:
                score -= 3
        except Exception:
            pass

        signals["score"] = max(score, 0)
        return signals

    def _determine_failure_reason(
        self,
        signals: dict[str, Any],
        auth_state: dict[str, Any],
        captured_responses: list[dict[str, Any]],
    ) -> AuthFailureReason:
        """Determine the most specific failure reason from available evidence."""
        error_text = signals.get("auth_error_text") or []

        if any("mfa" in e or "two-factor" in e or "verify your identity" in e for e in error_text):
            return AuthFailureReason.MFA_REQUIRED
        if any("captcha" in e for e in error_text):
            return AuthFailureReason.CAPTCHA_REQUIRED
        if any(k in " ".join(error_text) for k in ("invalid", "incorrect", "wrong", "not found", "access denied", "locked")):
            return AuthFailureReason.INVALID_CREDENTIALS
        if any(s == 401 for s in (auth_state.get("auth_status_codes") or [])):
            return AuthFailureReason.AUTHORIZATION_DENIED
        if any(s == 403 for s in (auth_state.get("auth_status_codes") or [])):
            return AuthFailureReason.AUTHORIZATION_DENIED

        # If signals look positive but score is low
        if signals.get("auth_cookie_found") or signals.get("local_storage_token"):
            return AuthFailureReason.LOGIN_SUCCESS_BUT_VALIDATION_FAILED

        if any(s and s >= 500 for s in (auth_state.get("auth_status_codes") or [])):
            return AuthFailureReason.NETWORK_ERROR

        if not signals.get("url_changed") and not signals.get("password_field_gone"):
            if signals.get("score", 0) <= 0:
                return AuthFailureReason.LOGIN_TIMEOUT

        return AuthFailureReason.UNKNOWN_AUTH_ERROR

    async def _capture_login_screenshot(self, page: Page, eid: str, url: str) -> None:
        try:
            shot_path = Path(self._screenshots_dir) / "login_result.png"
            await page.screenshot(path=str(shot_path), full_page=False)
            await emit(eid, EventType.SCREENSHOT_CAPTURED, {
                "url": url,
                "title": await page.title(),
                "filename": "login_result.png",
                "path": str(shot_path),
                "action": "post_login",
            })
            await emit(eid, EventType.BROWSER_ACTION, {
                "action": "authenticated",
                "label": f"Authenticated — now on: {url}",
                "filename": "login_result.png",
            })
        except Exception:
            pass

    @staticmethod
    async def _emit_action_with_position(eid: str, locator: Locator, action: str, label: str) -> None:
        try:
            box = await locator.bounding_box()
            if box:
                x = box["x"] + box["width"] / 2
                y = box["y"] + box["height"] / 2
                await emit(eid, EventType.BROWSER_ACTION, {
                    "action": action,
                    "label": label,
                    "position": {"x": round(x), "y": round(y)},
                    "selector": await locator.evaluate("el => el.tagName + (el.id ? '#'+el.id : '') + (el.className ? '.'+el.className.split(' ').slice(0,2).join('.') : '')"),
                })
                return
        except Exception:
            pass
        await emit(eid, EventType.BROWSER_ACTION, {"action": action, "label": label})

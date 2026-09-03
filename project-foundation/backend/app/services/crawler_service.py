"""
Crawler Service

Business logic for web crawling and discovery.
"""

import asyncio
import re
import time
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
from app.services.auth_state import (
    RETRYABLE_AUTH_FAILURES,
    AuthEvidence,
    AuthFailureReason,
    AuthResult,
    AuthState,
)
from app.services.dom_extractor import extract_all
from app.utils import save_file

# Generic authentication *failure* text indicators (invalid credentials / denial).
# These are generic error-message keywords, NOT application routes or success
# heuristics. Challenge indicators (MFA/OTP/captcha) live separately below.
_AUTH_ERROR_TEXT_PATTERNS: list[str] = [
    "invalid username", "invalid password", "incorrect password",
    "incorrect username", "wrong credentials", "wrong password", "wrong username",
    "authentication failed", "login failed", "access denied",
    "invalid email", "invalid user", "user not found", "account not found",
    "account locked", "too many attempts",
]

# Generic authentication *challenge* indicators (MFA / OTP / captcha). These
# signal an in-progress challenge, never a success or a terminal failure.
_AUTH_CHALLENGE_TEXT_PATTERNS: list[str] = [
    "verify your identity", "mfa required", "multi-factor authentication",
    "2fa required", "two-factor authentication", "one-time code",
    "verification code", "enter the code", "authentication code",
    "captcha", "please complete the captcha",
]

# Generic selectors for an OTP / verification-code input (structural only).
_OTP_FIELD_SELECTOR: str = (
    'input[autocomplete="one-time-code"], '
    'input[name*="otp" i], input[name*="code" i], input[name*="mfa" i], '
    'input[name*="verification" i]'
)


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
        self._target_url = request.target_url

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
                # Attempt authentication when credentials/strategy were supplied.
                post_login_url: str | None = None
                if self._auth_context and self._auth_context.has_auth_config():
                    # Capture the pre-auth state of the target URL before credentials are
                    # submitted so the unauthenticated page appears in the inventory.
                    canonical_target = self._canonicalize_url(request.target_url)
                    if canonical_target and canonical_target not in self._visited_urls:
                        try:
                            pre_auth_record = await self._visit_page(
                                context=context,
                                url=request.target_url,
                                depth=0,
                                parent_page_id=None,
                                screenshots_dir=screenshots_dir if request.screenshot else None,
                                timeout_ms=request.timeout,
                            )
                            self._visited_urls.add(canonical_target)
                            canonical_actual = self._canonicalize_url(pre_auth_record.url)
                            if canonical_actual:
                                self._visited_urls.add(canonical_actual)
                            self._visited_pages.append(pre_auth_record)
                            self.logger.info(
                                "pre_auth_page_captured",
                                url=request.target_url,
                                page_id=str(pre_auth_record.page_id),
                            )
                        except Exception as pre_auth_err:
                            self.logger.warning(
                                "pre_auth_page_capture_failed",
                                url=request.target_url,
                                error=str(pre_auth_err),
                            )
                    auth_result = await self._perform_login(context)
                    if auth_result.success:
                        self._authenticated = True
                        post_login_url = auth_result.post_login_url
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
                    elif auth_result.stop_crawl:
                        # Credentials were supplied => authentication is required.
                        # A failed/unknown/unsupported/challenged outcome must NOT
                        # continue as if public crawling produced authenticated
                        # inventory.
                        code = (
                            auth_result.failure_reason.value
                            if auth_result.failure_reason
                            else "AUTH_FAILED"
                        )
                        self._warnings.append(
                            CrawlEvent(
                                code=code,
                                message=auth_result.reason or "Authentication required but not completed",
                                url=request.target_url,
                                timestamp=datetime.now(UTC),
                            )
                        )
                        self.logger.error(
                            "authentication_required_but_not_completed",
                            state=auth_result.state.value,
                            reason=auth_result.reason,
                        )
                        raise ServiceError(
                            f"Authentication failed ({auth_result.state.value}): {auth_result.reason}"
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
            # SPA-aware settle barrier. DOMContentLoaded fires before JS
            # frameworks (Angular/React/Vue) bootstrap and render async data;
            # extracting the DOM at that instant yields an empty shell. Wait a
            # bounded amount of time for the network to go quiet so the rendered
            # links/buttons/forms/tables are visible to the extractor. The wait is
            # bounded — apps that poll or stream forever simply hit the timeout and
            # crawling proceeds. A short fixed settle then covers the final render
            # tick after the last request.
            try:
                await page.wait_for_load_state("networkidle", timeout=4000)
            except Exception:
                pass  # app may poll/stream forever — crawl with what is rendered
            try:
                await page.wait_for_timeout(400)
            except Exception:
                pass
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

    async def _perform_login(self, context: BrowserContext) -> AuthResult:
        """
        Attempt authentication using the stored AuthContext.

        Honors ``auth_strategy``: the form strategy is driven directly; oauth/sso
        use a generic browser redirect flow; any other strategy returns a
        structured ``AUTH_STRATEGY_UNSUPPORTED`` outcome.

        SECURITY: credentials are used directly in browser fill calls; they are
        never written to logs, events, or returned in any output.
        """
        auth = self._auth_context
        if not auth:
            return AuthResult(state=AuthState.UNAUTHENTICATED, reason="No authentication context")
        eid = getattr(self, "_event_run_id", None)
        strategy = (auth.auth_strategy or "form").lower()

        if eid:
            await emit(eid, EventType.AUTH_STARTED, {"strategy": strategy})

        if strategy == "form":
            if not auth.is_populated():
                return AuthResult(
                    state=AuthState.UNAUTHENTICATED,
                    reason="Username and password required for form authentication",
                )
            return await self._perform_form_login(context, auth, eid)

        if strategy in ("oauth", "sso"):
            return await self._perform_oauth_sso_flow(context, auth, eid)

        if eid:
            await emit(eid, EventType.AUTH_STRATEGY_UNSUPPORTED, {"strategy": strategy})
        return AuthResult(
            state=AuthState.AUTH_STRATEGY_UNSUPPORTED,
            failure_reason=AuthFailureReason.AUTH_STRATEGY_UNSUPPORTED,
            reason=f"Authentication strategy '{strategy}' is not supported by the crawler",
        )

    async def _perform_form_login(self, context: BrowserContext, auth, eid: str | None) -> AuthResult:
        """Drive a username/password form at the explicit (or discovered) login URL."""
        login_url = await self._resolve_login_url(context, auth)
        if not login_url:
            if eid:
                await emit(eid, EventType.AUTH_URL_NOT_FOUND, {"reason": "no_login_url_supplied"})
            return AuthResult(
                state=AuthState.AUTH_URL_NOT_FOUND,
                failure_reason=AuthFailureReason.AUTH_URL_NOT_FOUND,
                reason="No login URL supplied and none could be discovered",
            )

        if eid:
            await emit(eid, EventType.STAGE_STARTED, {"stage": "authentication", "label": "Logging In"})
            await emit(eid, EventType.AUTH_URL_DISCOVERED, {"url": login_url})

        # Bounded retry for transient failures only.
        transient_attempts = 0
        while True:
            result = await self._attempt_form_login_once(context, auth, login_url, eid)
            if result.success:
                return result
            if result.failure_reason not in RETRYABLE_AUTH_FAILURES:
                return result
            transient_attempts += 1
            if transient_attempts >= 2:
                return result
            self.logger.info(
                "auth_transient_retry",
                attempt=transient_attempts,
                reason=result.failure_reason.value,
            )

    async def _attempt_form_login_once(self, context: BrowserContext, auth, login_url: str, eid: str | None) -> AuthResult:
        if eid:
            await emit(eid, EventType.BROWSER_ACTION, {"action": "goto", "target": login_url, "label": f"Opening login page: {login_url}"})

        page = await context.new_page()
        try:
            try:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as nav_error:
                self.logger.warning("auth_navigation_failed", url=login_url, error=str(nav_error))
                return AuthResult(
                    state=AuthState.AUTHENTICATION_TIMEOUT,
                    failure_reason=AuthFailureReason.NETWORK_ERROR,
                    reason=f"Could not reach login URL: {nav_error}",
                )

            if eid:
                await emit(eid, EventType.PAGE_LOADED, {"url": login_url, "depth": 0, "status_code": 200})

            username_field = await self._locate_username_field(page)
            password_field = await self._locate_password_field(page)
            if not (username_field and password_field):
                await self._wait_for_login_form(page)
                username_field = await self._locate_username_field(page)
                password_field = await self._locate_password_field(page)

            if not (username_field and password_field):
                self.logger.info("login_form_not_found", url=login_url)
                return AuthResult(
                    state=AuthState.AUTH_URL_NOT_FOUND,
                    failure_reason=AuthFailureReason.AUTH_URL_NOT_FOUND,
                    reason=f"No login form found at {login_url}",
                )

            if eid:
                await emit(eid, EventType.AUTH_FORM_DETECTED, {"url": login_url})
                await self._emit_action_with_position(eid, username_field, "fill", "Typing username / user ID...")
                await self._emit_action_with_position(eid, password_field, "fill", "Typing password...")

            await username_field.fill(auth.username or "")
            await password_field.fill(auth.password or "")
            self.logger.info("auth_credentials_filled", has_username=bool(auth.username))

            submit_button = await self._locate_submit_button(page)
            pre_login_url = page.url
            if eid and submit_button:
                await self._emit_action_with_position(eid, submit_button, "click", "Clicking Login button...")
            self.logger.info("auth_submit_clicked", url=pre_login_url)
            result = await self._submit_and_wait_for_auth(page, submit_button, pre_login_url, eid)
            if result.success:
                if eid:
                    if self._screenshots_dir:
                        await self._capture_login_screenshot(page, eid, result.post_login_url or login_url)
                    await emit(eid, EventType.STAGE_COMPLETED, {"stage": "authentication", "label": "Login Successful"})
            else:
                await self._capture_auth_failure_evidence(page, eid, result)
            return result
        finally:
            await page.close()

    async def _perform_oauth_sso_flow(self, context: BrowserContext, auth, eid: str | None) -> AuthResult:
        """
        Generic OAuth/SSO browser-flow handling.

        Navigates to the configured login URL, follows cross-origin redirects to
        an identity provider within the same context (session state preserved),
        drives any username/password form that appears, detects MFA challenges,
        and verifies the final authenticated state. No provider-specific
        hostnames, routes, or selectors are used.
        """
        login_url = await self._resolve_login_url(context, auth)
        if not login_url:
            if eid:
                await emit(eid, EventType.AUTH_URL_NOT_FOUND, {"reason": "no_login_url_supplied"})
            return AuthResult(
                state=AuthState.AUTH_URL_NOT_FOUND,
                failure_reason=AuthFailureReason.AUTH_URL_NOT_FOUND,
                reason="No login URL supplied and none could be discovered",
            )

        if eid:
            await emit(eid, EventType.STAGE_STARTED, {"stage": "authentication", "label": "Logging In"})
            await emit(eid, EventType.OAUTH_DETECTED, {"url": login_url, "strategy": (auth.auth_strategy or "sso").lower()})

        page = await context.new_page()
        try:
            try:
                await page.goto(login_url, wait_until="domcontentloaded", timeout=15000)
            except Exception as nav_error:
                return AuthResult(
                    state=AuthState.AUTHENTICATION_TIMEOUT,
                    failure_reason=AuthFailureReason.NETWORK_ERROR,
                    reason=f"Could not reach login URL: {nav_error}",
                )

            before = await self._capture_auth_snapshot(page)

            # Follow any external identity-provider redirect (bounded, no networkidle).
            await self._wait_for_auth_completion(page, login_url, timeout_ms=10000)

            username_field = await self._locate_username_field(page)
            password_field = await self._locate_password_field(page)
            if username_field and password_field:
                if eid:
                    await emit(eid, EventType.AUTH_FORM_DETECTED, {"url": page.url})
                await username_field.fill(auth.username or "")
                await password_field.fill(auth.password or "")
                pre_url = page.url
                submit_button = await self._locate_submit_button(page)
                try:
                    async with page.expect_navigation(wait_until="domcontentloaded", timeout=20000):
                        if submit_button:
                            await submit_button.click(timeout=5000)
                        else:
                            await page.keyboard.press("Enter")
                except Exception:
                    pass
                await self._wait_for_auth_completion(page, pre_url)
                await self._wait_for_auth_transition_settle(page, pre_url)

            if eid:
                await emit(eid, EventType.AUTH_VERIFICATION_STARTED, {"url": page.url})

            after = await self._capture_auth_snapshot(page)
            challenge = await self._detect_auth_challenge(page)
            error_text = await self._detect_auth_error_text(page)
            evidence = self._build_auth_evidence(before, after, [], bool(challenge), bool(error_text))
            result = await self._evaluate_auth_evidence(evidence, after, challenge, error_text, eid)
            if result.success and eid:
                await emit(eid, EventType.STAGE_COMPLETED, {"stage": "authentication", "label": "Login Successful"})
            return result
        finally:
            await page.close()

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
        submit_button: Locator | None,
        pre_login_url: str,
        eid: str | None,
    ) -> AuthResult:
        """
        Submit the login form, wait for the authentication transition, and
        classify the result using generic, application-agnostic evidence.

        Returns a structured ``AuthResult`` (never a raw score or dict).
        """
        captured_responses: list[dict[str, Any]] = []

        async def _on_response(response):
            try:
                captured_responses.append({"url": response.url, "status": response.status})
            except Exception:
                pass

        page.on("response", _on_response)
        try:
            if eid:
                await emit(eid, EventType.AUTH_SUBMITTED, {"url": pre_login_url})

            before = await self._capture_auth_snapshot(page)

            await self._trigger_form_submit(page, submit_button)

            await self._wait_for_auth_completion(page, pre_login_url)
            await self._wait_for_auth_transition_settle(page, pre_login_url)

            after = await self._capture_auth_snapshot(page)

            self.logger.info(
                "auth_submit_network_activity",
                url_after=page.url,
                captured_responses=captured_responses,
            )

            if eid:
                await emit(eid, EventType.AUTH_VERIFICATION_STARTED, {"url": page.url})

            challenge = await self._detect_auth_challenge(page)
            error_text = await self._detect_auth_error_text(page)
            evidence = self._build_auth_evidence(before, after, captured_responses, bool(challenge), bool(error_text))

            return await self._evaluate_auth_evidence(evidence, after, challenge, error_text, eid)
        finally:
            try:
                page.remove_listener("response", _on_response)
            except Exception:
                pass

    async def _trigger_form_submit(self, page: Page, submit_button: Locator | None) -> None:
        """Submit the login form using the most reliable strategy available.

        React/Next.js forms typically bind their login handler to the form's
        ``submit`` event (or a Server Action), not the button's raw pointer
        click. A bare ``.click()`` can therefore fire no handler and produce a
        click with no login request. We prefer the native form submission
        (``requestSubmit()``), then a real click, then the Enter key.
        """
        # Strategy 1: native form submission — reliably fires React onSubmit and
        # Next.js Server Actions (which a plain button click may miss).
        if submit_button is not None:
            try:
                submitted = await submit_button.evaluate(
                    "el => { const f = el.form || el.closest('form'); "
                    "if (f) { f.requestSubmit(); return true; } return false; }"
                )
                if submitted:
                    self.logger.info("auth_submit_via_request_submit")
                    return
            except Exception:
                pass

        # Strategy 2: real pointer click on the submit button.
        if submit_button is not None:
            try:
                await submit_button.click(timeout=5000)
                self.logger.info("auth_submit_via_click")
                return
            except Exception:
                pass

        # Strategy 3: Enter key (submits the enclosing form if focus is inside it).
        try:
            await page.keyboard.press("Enter")
            self.logger.info("auth_submit_via_enter")
        except Exception:
            pass

    async def _wait_for_auth_completion(
        self, page: Page, pre_login_url: str, timeout_ms: int = 15000,
    ) -> None:
        """
        Bounded adaptive wait for the post-submit authentication transition.

        Returns early when any of these generic conditions are observed:
          - the URL changed from the pre-login URL,
          - an authentication challenge or error text appeared.

        Never waits on networkidle: SPAs and applications with polling /
        websocket connections may never become network-idle.
        """
        deadline = time.monotonic() + (timeout_ms / 1000)
        while time.monotonic() < deadline:
            try:
                if page.url != pre_login_url:
                    return
            except Exception:
                pass
            try:
                body = (await page.text_content("body", timeout=1000) or "").lower()
                if any(p in body for p in _AUTH_CHALLENGE_TEXT_PATTERNS):
                    return
                if any(p in body for p in _AUTH_ERROR_TEXT_PATTERNS):
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def _wait_for_auth_transition_settle(
        self, page: Page, pre_login_url: str, timeout_ms: int = 15000,
    ) -> None:
        """
        Bounded wait for the post-login SPA transition to fully commit before the
        verification snapshot is taken.

        Next.js / Angular-style client-side navigation fetches the next route and
        then swaps the DOM (and updates the URL bar) a beat later. Snapshotting in
        that gap still shows the login form and can misclassify a successful login
        as a credential failure. Returns early once:
          - the password field has disappeared from the DOM, or
          - an authentication challenge or error text appeared.
        """
        deadline = time.monotonic() + (timeout_ms / 1000)
        while time.monotonic() < deadline:
            try:
                if not await self._password_field_present(page):
                    return
            except Exception:
                pass
            try:
                body = (await page.text_content("body", timeout=1000) or "").lower()
                if any(p in body for p in _AUTH_CHALLENGE_TEXT_PATTERNS):
                    return
                if any(p in body for p in _AUTH_ERROR_TEXT_PATTERNS):
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def _wait_for_login_form(self, page: Page, timeout_ms: int = 8000) -> None:
        """Bounded wait for a password field to appear (SPA / async form render)."""
        deadline = time.monotonic() + (timeout_ms / 1000)
        while time.monotonic() < deadline:
            try:
                if await page.locator('input[type="password"]:visible').count() > 0:
                    return
            except Exception:
                pass
            await asyncio.sleep(0.5)

    async def _password_field_present(self, page: Page) -> bool:
        """True when a visible password field is present (generic login-form signal)."""
        try:
            return await page.locator('input[type="password"]:visible').count() > 0
        except Exception:
            return False

    async def _resolve_login_url(self, context: BrowserContext, auth) -> str | None:
        """Return the explicit login URL, else discover it generically at runtime.

        Prefers the user-supplied ``login_url``. When absent, navigates to the
        application entry URL (following redirects) and looks for a login form,
        then falls back to following a generic sign-in link. Never guesses a
        conventional route from a hardcoded list.
        """
        if auth.login_url:
            return auth.login_url
        target = getattr(self, "_target_url", None)
        if not target:
            return None
        return await self._discover_login_url(context, target)

    async def _discover_login_url(self, context: BrowserContext, start_url: str) -> str | None:
        """Generic runtime discovery of the authentication entry point."""
        page = await context.new_page()
        try:
            try:
                await page.goto(start_url, wait_until="domcontentloaded", timeout=15000)
            except Exception:
                return None
            await self._wait_for_login_form(page, timeout_ms=5000)
            if await self._password_field_present(page):
                return page.url

            link = await self._find_login_link(page)
            if link:
                try:
                    await page.goto(link, wait_until="domcontentloaded", timeout=15000)
                except Exception:
                    return None
                await self._wait_for_login_form(page, timeout_ms=5000)
                if await self._password_field_present(page):
                    return page.url
            return None
        finally:
            await page.close()

    async def _find_login_link(self, page: Page) -> str | None:
        """Find a generic sign-in link on the page (text/role based, not route based)."""
        for text in ("Sign in", "Log in", "Login", "Sign In", "Log In"):
            for selector in (f'a:has-text("{text}")', f'[role="link"]:has-text("{text}")'):
                try:
                    loc = page.locator(selector).first
                    if await loc.count() > 0:
                        href = await loc.get_attribute("href")
                        if href:
                            return urljoin(page.url, href)
                except Exception:
                    continue
        return None

    async def _capture_auth_snapshot(self, page: Page) -> dict[str, Any]:
        """Capture generic, application-agnostic auth state around a transition."""
        snapshot: dict[str, Any] = {
            "url": "",
            "password_present": False,
            "cookie_names": set(),
            "storage_keys": set(),
        }
        try:
            snapshot["url"] = page.url
        except Exception:
            pass
        try:
            snapshot["password_present"] = await page.locator('input[type="password"]:visible').count() > 0
        except Exception:
            pass
        try:
            snapshot["cookie_names"] = {c.get("name") for c in await page.context.cookies()}
        except Exception:
            pass
        try:
            keys: set[str] = set()
            for store in ("localStorage", "sessionStorage"):
                try:
                    k = await page.evaluate(f"Object.keys(window.{store})")
                    keys.update(f"{store}:{x}" for x in k)
                except Exception:
                    continue
            snapshot["storage_keys"] = keys
        except Exception:
            pass
        return snapshot

    @staticmethod
    def _build_auth_evidence(
        before: dict[str, Any],
        after: dict[str, Any],
        captured_responses: list[dict[str, Any]],
        challenge_detected: bool,
        error_text_detected: bool,
    ) -> AuthEvidence:
        """Assemble generic authentication evidence from before/after snapshots."""
        statuses = [int(r.get("status") or 0) for r in captured_responses]
        return AuthEvidence(
            navigation_changed=before.get("url") != after.get("url"),
            redirect_completed=any(s in (301, 302, 303, 307, 308) for s in statuses),
            login_form_disappeared=bool(before.get("password_present")) and not bool(after.get("password_present")),
            cookies_changed=before.get("cookie_names") != after.get("cookie_names"),
            storage_changed=before.get("storage_keys") != after.get("storage_keys"),
            challenge_detected=challenge_detected,
            network_auth_response=any(200 <= s < 300 for s in statuses),
            error_text_detected=error_text_detected,
        )

    async def _detect_auth_challenge(self, page: Page) -> str | None:
        """Return 'mfa' / 'captcha' if a generic authentication challenge is present."""
        body = ""
        try:
            body = (await page.text_content("body", timeout=2000) or "").lower()
        except Exception:
            pass
        if any(p in body for p in _AUTH_CHALLENGE_TEXT_PATTERNS):
            return "captcha" if "captcha" in body else "mfa"
        try:
            if await page.locator(_OTP_FIELD_SELECTOR).count() > 0:
                return "mfa"
        except Exception:
            pass
        return None

    async def _detect_auth_error_text(self, page: Page) -> str | None:
        """Return the first generic authentication error indicator found, if any."""
        body = ""
        try:
            body = (await page.text_content("body", timeout=2000) or "").lower()
        except Exception:
            pass
        matched = [p for p in _AUTH_ERROR_TEXT_PATTERNS if p in body]
        return matched[0] if matched else None

    async def _evaluate_auth_evidence(
        self,
        evidence: AuthEvidence,
        after: dict[str, Any],
        challenge: str | None,
        error_text: str | None,
        eid: str | None,
    ) -> AuthResult:
        """Classify the authentication transition from generic evidence alone."""
        url = after.get("url")

        if challenge == "captcha":
            return AuthResult(
                state=AuthState.AUTHENTICATION_FAILED,
                post_login_url=url,
                failure_reason=AuthFailureReason.CAPTCHA_REQUIRED,
                reason="CAPTCHA challenge detected",
            )
        if challenge == "mfa":
            if eid:
                await emit(eid, EventType.MFA_REQUIRED, {"url": url})
            return AuthResult(
                state=AuthState.MFA_REQUIRED,
                post_login_url=url,
                failure_reason=AuthFailureReason.MFA_REQUIRED,
                reason="Multi-factor authentication required",
            )

        if evidence.error_text_detected and not evidence.login_form_disappeared:
            return AuthResult(
                state=AuthState.AUTHENTICATION_FAILED,
                post_login_url=url,
                failure_reason=AuthFailureReason.INVALID_CREDENTIALS,
                reason=f"Authentication rejected: {error_text}",
            )

        # Authoritative, generic proof of authentication: the login form went
        # away AND the session state actually changed (navigation/cookies/storage).
        if evidence.login_form_disappeared and (
            evidence.cookies_changed or evidence.storage_changed or evidence.navigation_changed
        ):
            if eid:
                await emit(eid, EventType.AUTHENTICATED, {"url": url})
            return AuthResult(state=AuthState.AUTHENTICATED, post_login_url=url)

        # Form still present with no state change → credentials did not work.
        if (
            not evidence.login_form_disappeared
            and not evidence.navigation_changed
            and not evidence.cookies_changed
            and not evidence.storage_changed
        ):
            return AuthResult(
                state=AuthState.AUTHENTICATION_FAILED,
                post_login_url=url,
                failure_reason=AuthFailureReason.INVALID_CREDENTIALS,
                reason="Login form still present after submit",
            )

        # Otherwise we cannot authoritatively verify authentication.
        if eid:
            await emit(eid, EventType.AUTHENTICATION_UNKNOWN, {"url": url})
        return AuthResult(
            state=AuthState.AUTHENTICATION_UNKNOWN,
            post_login_url=url,
            reason="No authoritative authentication signal observed",
        )

    async def _capture_auth_failure_evidence(self, page: Page, eid: str | None, result: AuthResult) -> None:
        """Capture diagnostic evidence when form login does not succeed."""
        try:
            body = (await page.text_content("body") or "")[:3000]
            self.logger.info(
                "auth_failure_body_text",
                url=page.url,
                reason=getattr(result, "reason", None),
                body=body,
            )
        except Exception:
            pass

        if not self._screenshots_dir or not eid:
            return
        try:
            shot_path = Path(self._screenshots_dir) / "login_failure.png"
            await page.screenshot(path=str(shot_path), full_page=False)
            await emit(eid, EventType.SCREENSHOT_CAPTURED, {
                "url": page.url,
                "title": await page.title(),
                "filename": "login_failure.png",
                "path": str(shot_path),
                "action": "post_login_failure",
            })
        except Exception:
            pass

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

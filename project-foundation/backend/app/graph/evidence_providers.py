"""
EvidenceProvider abstraction — supporting evidence gathering only.

Providers gather observations (DOM, Network, Storage, Navigation,
Accessibility, Browser events, Screenshots, Action results) and return them
as plain dicts. No provider may declare GOAL_COMPLETED. Only the
GoalCompletionEngine — after verifying the plan's expected transition — may
emit GOAL_COMPLETED.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlsplit

try:  # pragma: no cover - playwright may not be importable in unit env
    from playwright.async_api import BrowserContext, Page
except Exception:  # pragma: no cover
    Page = Any  # type: ignore[assignment, misc]
    BrowserContext = Any  # type: ignore[assignment, misc]

from app.graph.expected_state import ObservedState


def url_path(url: str | None) -> str:
    """Return URL path/query only — hostname and domain excluded."""
    if not url:
        return ""
    try:
        parts = urlsplit(url)
        path = parts.path or "/"
        query = f"?{parts.query}" if parts.query else ""
        return f"{path}{query}"
    except ValueError:
        return url


def build_observed_state(
    *,
    url: str | None = None,
    title: str | None = None,
    authenticated: bool = False,
    dom_observations: dict[str, Any] | None = None,
    network_observations: list[dict[str, Any]] | None = None,
    storage_observations: dict[str, Any] | None = None,
    accessibility_observations: dict[str, Any] | None = None,
    browser_events: list[dict[str, Any]] | None = None,
    screenshots: list[dict[str, Any]] | None = None,
    action_results: dict[str, Any] | None = None,
) -> ObservedState:
    """Construct an ObservedState from runtime signals."""
    return ObservedState(
        timestamp=time.time(),
        authenticated=bool(authenticated),
        navigation_url_path=url_path(url),
        page_title=title or "",
        dom_observations=dom_observations or {},
        network_observations=network_observations or [],
        storage_observations=storage_observations or {},
        accessibility_observations=accessibility_observations or {},
        browser_events=browser_events or [],
        screenshots=screenshots or [],
        action_results=action_results or {},
    )


class IEvidenceProvider(ABC):
    """Base class for evidence providers. Gathers supporting observations only."""

    label: str = ""

    @abstractmethod
    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        """Gather structural runtime observations from the browser."""
        raise NotImplementedError


class DOMEvidenceProvider(IEvidenceProvider):
    """Gathers active interactive element counts and page signatures."""

    label = "dom"

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        result: dict[str, Any] = {"form_count": 0, "input_count": 0, "button_count": 0,
                                  "table_count": 0, "dialog_count": 0}
        try:
            result["form_count"] = await page.locator("form").count()
            result["input_count"] = await page.locator("input, textarea, select").count()
            result["button_count"] = await page.locator("button").count()
            result["table_count"] = await page.locator("table").count()
            result["dialog_count"] = await page.locator("[role='dialog'], dialog").count()
        except Exception:
            pass
        return result


class NetworkEvidenceProvider(IEvidenceProvider):
    """Monitors network activity summaries since the last action."""

    label = "network"

    def __init__(self, captured_responses: list[dict[str, Any]] | None = None) -> None:
        self._captured = captured_responses or []

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        return {
            "responses": list(self._captured),
            "status_codes": [int(r.get("status") or 0) for r in self._captured],
        }


class StorageEvidenceProvider(IEvidenceProvider):
    """Inspects cookies and session/local storage indicators."""

    label = "storage"

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        result: dict[str, Any] = {"cookie_count": 0, "cookie_names": [], "storage_tokens": []}
        try:
            cookies = await page.context.cookies()
            result["cookie_count"] = len(cookies)
            result["cookie_names"] = [c.get("name") for c in cookies]
        except Exception:
            pass
        try:
            result["storage_tokens"] = [
                key for key in ("token", "auth_token", "access_token", "jwt", "id_token")
                if await page.evaluate(f"localStorage.getItem('{key}')")
            ]
        except Exception:
            pass
        return result


class NavigationEvidenceProvider(IEvidenceProvider):
    """Captures URL path and page title."""

    label = "navigation"

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        result: dict[str, Any] = {"url": "", "path": "", "title": ""}
        try:
            result["url"] = page.url
            result["path"] = url_path(page.url)
            result["title"] = await page.title()
        except Exception:
            pass
        return result


class AccessibilityEvidenceProvider(IEvidenceProvider):
    """Gathers basic accessibility observations."""

    label = "accessibility"

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        result: dict[str, Any] = {"aria_invalid_count": 0, "visible_dialogs": 0}
        try:
            result["aria_invalid_count"] = await page.locator('[aria-invalid="true"]').count()
            result["visible_dialogs"] = await page.locator("[role='dialog'], dialog").count()
        except Exception:
            pass
        return result


class BrowserEventEvidenceProvider(IEvidenceProvider):
    """Records browser events accumulated since the last action."""

    label = "browser_events"

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self._events = events or []

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        return {"events": list(self._events)}


class ScreenshotEvidenceProvider(IEvidenceProvider):
    """Records screenshot fingerprints."""

    label = "screenshots"

    def __init__(self, screenshots: list[dict[str, Any]] | None = None) -> None:
        self._screenshots = screenshots or []

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        return {"screenshots": list(self._screenshots)}


class ActionResultEvidenceProvider(IEvidenceProvider):
    """Records the result of the last executed capability."""

    label = "action_results"

    def __init__(self, result: dict[str, Any] | None = None) -> None:
        self._result = result or {}

    async def gather(self, page: Page, context: BrowserContext) -> dict[str, Any]:
        return dict(self._result)


def gather_all(
    page: Page,
    context: BrowserContext,
    providers: list[IEvidenceProvider] | None = None,
) -> dict[str, Any]:
    """Collective evidence gatherer used by the crawler (sync helper)."""
    raise NotImplementedError(
        "gather_all is async in production use; call providers via 'await provider.gather(...)' "
        "and fold the buckets into ObservedState."
    )

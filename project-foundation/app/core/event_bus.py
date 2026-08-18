"""
Workflow Event Bus

A lightweight, in-process asyncio pub/sub event bus that allows workflow
stages and agents to emit structured events, which are then streamed to
frontend clients via Server-Sent Events (SSE).

Architecture:
    Agents / Workflow Nodes
          │  publish(run_id, event)
          ▼
    WorkflowEventBus (singleton)
          │  asyncio.Queue per subscriber
          ▼
    SSE endpoint → EventSource in browser → Zustand store

This is the single source of truth for live UI state — the frontend
builds its entire run-detail view from these events, using REST APIs
only for initial page load and artifact retrieval.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from uuid import uuid4

from app.logging import get_logger

logger = get_logger("core.event_bus")


# ---------------------------------------------------------------------------
# Event type constants — keep in sync with frontend WorkflowEventType enum
# ---------------------------------------------------------------------------

class EventType:
    # Workflow lifecycle
    WORKFLOW_STARTED        = "workflow_started"
    WORKFLOW_COMPLETED      = "workflow_completed"
    WORKFLOW_FAILED         = "workflow_failed"
    WORKFLOW_PAUSED         = "workflow_paused"

    # Stage lifecycle (generic — carries stage name in data)
    STAGE_STARTED           = "stage_started"
    STAGE_COMPLETED         = "stage_completed"
    STAGE_FAILED            = "stage_failed"
    STAGE_SKIPPED           = "stage_skipped"

    # Trigger / setup
    WORKSPACE_CREATED       = "workspace_created"
    RUN_METADATA_SAVED      = "run_metadata_saved"

    # Crawler — granular
    CRAWLER_STARTED            = "crawler_started"
    BROWSER_LAUNCHING          = "browser_launching"
    BROWSER_INITIALIZED        = "browser_initialized"
    BROWSER_CONTEXT_CREATED    = "browser_context_created"
    PAGE_NAVIGATION_STARTED    = "page_navigation_started"
    DOM_CONTENT_LOADED         = "dom_content_loaded"
    PAGE_LOADED                = "page_loaded"
    HTML_EXTRACTED             = "html_extracted"
    SCREENSHOT_CAPTURED        = "screenshot_captured"
    FORMS_DETECTED             = "forms_detected"
    BUTTONS_DETECTED           = "buttons_detected"
    INPUTS_DETECTED            = "inputs_detected"
    LINKS_EXTRACTED            = "links_extracted"
    PAGE_VISITED               = "page_visited"
    PAGE_FAILED                = "page_failed"
    QUEUE_UPDATED              = "queue_updated"
    PAGE_COMPLETED             = "page_completed"
    CRAWL_COMPLETED            = "crawl_completed"

    # Goal Completion Engine
    GOAL_COMPLETED             = "goal_completed"
    GOAL_CRITERION_MET         = "goal_criterion_met"
    CRAWL_PHASE_CHANGED        = "crawl_phase_changed"

    # Authentication — generic structured lifecycle (no secrets in data)
    AUTH_STARTED               = "auth_started"
    AUTH_URL_DISCOVERED        = "auth_url_discovered"
    AUTH_FORM_DETECTED         = "auth_form_detected"
    AUTH_SUBMITTED             = "auth_submitted"
    AUTH_REDIRECT_STARTED      = "auth_redirect_started"
    AUTH_REDIRECT_COMPLETED    = "auth_redirect_completed"
    OAUTH_DETECTED             = "oauth_detected"
    MFA_REQUIRED               = "mfa_required"
    AUTH_VERIFICATION_STARTED  = "auth_verification_started"
    AUTHENTICATED              = "authenticated"
    AUTHENTICATION_FAILED      = "authentication_failed"
    AUTHENTICATION_TIMEOUT     = "authentication_timeout"
    AUTHENTICATION_UNKNOWN     = "authentication_unknown"
    AUTH_STRATEGY_UNSUPPORTED  = "auth_strategy_unsupported"
    AUTH_URL_NOT_FOUND         = "auth_url_not_found"

    # Inventory
    INVENTORY_STARTED       = "inventory_started"
    INVENTORY_GENERATED     = "inventory_generated"

    # Test design / LLM
    LLM_CALL_STARTED        = "llm_call_started"
    LLM_CALL_COMPLETED      = "llm_call_completed"
    TEST_PLAN_GENERATED     = "test_plan_generated"

    # AI Agent reasoning (granular thinking steps)
    AI_REASONING_STEP       = "ai_reasoning_step"
    MODULE_DETECTED         = "module_detected"
    SCENARIO_GENERATED      = "scenario_generated"
    CONFIDENCE_UPDATE       = "confidence_update"
    ANALYSIS_PROGRESS       = "analysis_progress"

    # Human review
    HUMAN_REVIEW_REQUIRED   = "human_review_required"
    HUMAN_REVIEW_APPROVED   = "human_review_approved"
    HUMAN_REVIEW_REJECTED   = "human_review_rejected"

    # IR generation
    IR_GENERATION_STARTED   = "ir_generation_started"
    IR_GENERATED            = "ir_generated"

    # Code generation — granular live progress
    CODE_GENERATION_STARTED     = "code_generation_started"
    CODE_GENERATION_COMPLETED   = "code_generation_completed"
    CODE_GENERATION_FAILED      = "code_generation_failed"
    LOADING_TEST_PLAN           = "loading_test_plan"
    TEST_PLAN_LOADED            = "test_plan_loaded"
    LOADING_INVENTORY           = "loading_inventory"
    LOADING_SCREENSHOTS         = "loading_screenshots"
    BUILDING_PROMPTS            = "building_prompts"
    PROMPTS_PREPARED            = "prompts_prepared"
    SENDING_LLM_REQUEST         = "sending_llm_request"
    WAITING_FOR_LLM_RESPONSE    = "waiting_for_llm_response"
    RECEIVED_LLM_RESPONSE       = "received_llm_response"
    LLM_TIMEOUT                 = "llm_timeout"
    LLM_ERROR                   = "llm_error"
    LLM_STREAMING_CHUNK         = "llm_streaming_chunk"
    PARSING_RESPONSE            = "parsing_response"
    JSON_PARSED                 = "json_parsed"
    IR_VALIDATION_STARTED       = "ir_validation_started"
    IR_VALIDATION_SUCCESS       = "ir_validation_success"
    IR_VALIDATION_FAILED        = "ir_validation_failed"
    IR_AUTO_REPAIR_STARTED      = "ir_auto_repair_started"
    IR_AUTO_REPAIR_SUCCESS      = "ir_auto_repair_success"
    PLANNING_PROJECT_STRUCTURE  = "planning_project_structure"
    PROJECT_STRUCTURE_PLANNED   = "project_structure_planned"
    GENERATING_PAGE_OBJECT      = "generating_page_object"
    PAGE_OBJECT_GENERATED       = "page_object_generated"
    GENERATING_TEST_FILE        = "generating_test_file"
    TEST_FILE_GENERATED         = "test_file_generated"
    GENERATING_FIXTURE          = "generating_fixture"
    FIXTURE_GENERATED           = "fixture_generated"
    GENERATING_HELPER           = "generating_helper"
    HELPER_GENERATED            = "helper_generated"
    GENERATING_CONFIG           = "generating_config"
    CONFIG_GENERATED            = "config_generated"
    WRITING_FILE                = "writing_file"
    FILE_WRITTEN                = "file_written"
    FORMATTING_CODE             = "formatting_code"
    CODE_FORMATTED              = "code_formatted"
    VALIDATING_GENERATED_CODE   = "validating_generated_code"
    CODE_VALIDATED              = "code_validated"
    PACKAGING_PROJECT           = "packaging_project"
    PROJECT_PACKAGED            = "project_packaged"
    FILE_STARTED                = "file_started"
    FILE_PROGRESS               = "file_progress"
    FILE_COMPLETED              = "file_completed"
    GENERATION_METRICS_UPDATE   = "generation_metrics_update"
    GENERATION_PROGRESS_UPDATE  = "generation_progress_update"
    CURRENT_ACTIVITY_UPDATE     = "current_activity_update"

    # Legacy / generic code-generation events (kept for compatibility)
    FILE_GENERATED              = "file_generated"
    PLAYWRIGHT_GENERATED        = "playwright_generated"

    # Execution
    EXECUTION_STARTED       = "execution_started"
    TEST_STARTED            = "test_started"
    TEST_PASSED             = "test_passed"
    TEST_FAILED             = "test_failed"
    TEST_SKIPPED            = "test_skipped"
    EXECUTION_COMPLETED     = "execution_completed"

    # Browser live actions
    BROWSER_ACTION          = "browser_action"
    BROWSER_FRAME           = "browser_frame"

    # Keepalive
    PING                    = "ping"


@dataclass
class WorkflowEvent:
    """Typed workflow event emitted by agents and workflow nodes."""

    type: str
    """Event type — one of the EventType constants."""

    run_id: str
    """The run this event belongs to."""

    data: dict[str, Any] = field(default_factory=dict)
    """Arbitrary payload specific to this event type."""

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    """ISO-8601 UTC timestamp when the event was emitted."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    """Unique identifier for idempotent replay."""

    def to_sse(self) -> str:
        """
        Serialise this event to the SSE wire format.

        Returns a string like::

            id: <event_id>
            event: <type>
            data: <json>

        """
        payload = json.dumps({
            "type": self.type,
            "run_id": self.run_id,
            "data": self.data,
            "timestamp": self.timestamp,
            "event_id": self.event_id,
        }, default=str)
        lines = [
            f"id: {self.event_id}",
            f"event: {self.type}",
            f"data: {payload}",
            "",  # blank line terminates SSE message
            "",
        ]
        return "\n".join(lines)


class WorkflowEventBus:
    """
    In-process asyncio pub/sub event bus.

    One instance is used per application lifetime (singleton via
    ``get_event_bus()``).  Multiple subscribers can listen to the same
    ``run_id``; each gets its own ``asyncio.Queue``.
    """

    # Maximum number of events buffered per subscriber before the oldest
    # is silently dropped (back-pressure protection).
    _QUEUE_MAX_SIZE = 512

    def __init__(self) -> None:
        # Map: run_id → set of asyncio.Queue[WorkflowEvent | None]
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        # Replay buffer: last N events per run_id for new subscribers
        self._replay_buffer: dict[str, list[WorkflowEvent]] = {}
        self._replay_limit = 200

    # ------------------------------------------------------------------
    # Publishing
    # ------------------------------------------------------------------

    async def publish(self, event: WorkflowEvent) -> None:
        """
        Emit ``event`` to all current subscribers for ``event.run_id``.

        Also stores the event in the replay buffer so late-joining
        subscribers can catch up.
        """
        run_id = event.run_id
        logger.debug("event_published", run_id=run_id, type=event.type)

        # Store in replay buffer
        buf = self._replay_buffer.setdefault(run_id, [])
        buf.append(event)
        if len(buf) > self._replay_limit:
            buf.pop(0)

        # Fan-out to all current subscribers
        queues = self._subscribers.get(run_id, set())
        for q in list(queues):
            if not q.full():
                await q.put(event)
            else:
                logger.warning(
                    "subscriber_queue_full",
                    run_id=run_id,
                    type=event.type,
                )

    def publish_sync(self, event: WorkflowEvent) -> None:
        """
        Synchronous fire-and-forget publish for use in non-async contexts
        (e.g. template engine running in a thread pool executor).

        When called from a worker thread, uses ``run_coroutine_threadsafe``
        so the event is delivered to the event loop immediately without waiting
        for the blocking thread to finish. When called from the event loop
        thread itself, falls back to ``create_task``.
        """
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                try:
                    # Check if we're on the event loop thread
                    running_loop = asyncio.get_running_loop()
                    # We ARE on the event loop thread — schedule as task
                    loop.create_task(self.publish(event))
                except RuntimeError:
                    # We're NOT on the event loop thread (worker thread) —
                    # use thread-safe scheduling so event fires immediately
                    asyncio.run_coroutine_threadsafe(self.publish(event), loop)
            else:
                loop.run_until_complete(self.publish(event))
        except RuntimeError:
            logger.warning("event_bus_no_loop", type=event.type, run_id=event.run_id)


    # ------------------------------------------------------------------
    # Subscribing
    # ------------------------------------------------------------------

    async def subscribe(
        self,
        run_id: str,
        replay: bool = True,
    ) -> AsyncGenerator[WorkflowEvent, None]:
        q: asyncio.Queue[WorkflowEvent | None] = asyncio.Queue(
            maxsize=self._QUEUE_MAX_SIZE
        )

        self._subscribers.setdefault(run_id, set()).add(q)
        logger.info("sse_subscriber_connected", run_id=run_id)

        try:
            if replay:
                for evt in list(self._replay_buffer.get(run_id, [])):
                    yield evt

            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    if event is None:
                        return
                    yield event
                except asyncio.TimeoutError:
                    yield WorkflowEvent(type=EventType.PING, run_id=run_id)

        except asyncio.CancelledError:
            logger.info("sse_subscriber_cancelled", run_id=run_id)
        finally:
            subs = self._subscribers.get(run_id, set())
            subs.discard(q)
            if not subs:
                self._subscribers.pop(run_id, None)
            logger.info("sse_subscriber_disconnected", run_id=run_id)

    def drain(self, run_id: str) -> None:
        """
        Send sentinel ``None`` to all subscribers for ``run_id``,
        signalling them to close gracefully.
        """
        queues = self._subscribers.get(run_id, set())
        for q in list(queues):
            try:
                q.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def clear_replay(self, run_id: str) -> None:
        """Discard the replay buffer for a completed run to free memory."""
        self._replay_buffer.pop(run_id, None)

    def get_history(self, run_id: str) -> list[WorkflowEvent]:
        """Return a snapshot of the replay buffer for *run_id* (may be empty)."""
        return list(self._replay_buffer.get(run_id, []))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_bus: WorkflowEventBus | None = None


def get_event_bus() -> WorkflowEventBus:
    """Return (or create) the process-wide WorkflowEventBus singleton."""
    global _bus
    if _bus is None:
        _bus = WorkflowEventBus()
    return _bus


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

async def emit(
    run_id: str,
    event_type: str,
    data: dict[str, Any] | None = None,
) -> None:
    """
    Shorthand for publishing a single event.

    Usage::

        await emit(run_id, EventType.PAGE_VISITED, {
            "url": "https://example.com/login",
            "title": "Login Page",
            "status_code": 200,
            "depth": 1,
        })
    """
    bus = get_event_bus()
    event = WorkflowEvent(
        type=event_type,
        run_id=run_id,
        data=data or {},
    )
    await bus.publish(event)

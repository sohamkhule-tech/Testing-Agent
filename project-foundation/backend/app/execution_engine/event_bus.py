"""
In-process Event Bus for task lifecycle coordination.

Every workflow node emits events instead of directly modifying shared state.
Subscribers (AgentState, Scheduler, Reporting, Planner) react to events.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

from app.logging import LoggerMixin

# Callback signature: async fn(event: dict) -> None
Subscriber = Callable[[dict[str, Any]], Coroutine[Any, Any, None]]


class ExecutionEvent:
    """Canonical event emitted by workflow stages."""

    TASK_STARTED = "task:started"
    TASK_COMPLETED = "task:completed"
    TASK_FAILED = "task:failed"
    TASK_SKIPPED = "task:skipped"
    TASK_BLOCKED = "task:blocked"
    TASK_RETRYING = "task:retrying"
    CRAWLER_DISCOVERED = "crawler:discovered"
    INVENTORY_GENERATED = "inventory:generated"
    TEST_PLAN_CREATED = "test_plan:created"
    CODE_GENERATED = "code:generated"
    EXECUTION_FINISHED = "execution:finished"
    CLARIFICATION_NEEDED = "plan:clarification_needed"
    PLAN_UPDATED = "plan:updated"
    CAPABILITY_UNHEALTHY = "capability:unhealthy"


class EventBus(LoggerMixin):
    """In-process pub/sub for task lifecycle events."""

    def __init__(self) -> None:
        super().__init__()
        self._subscribers: dict[str, list[Subscriber]] = {}
        self._event_log: list[dict[str, Any]] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def subscribe(self, event_type: str, callback: Subscriber) -> None:
        """Register an async callback for the given event type."""
        async with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if callback not in self._subscribers[event_type]:
                self._subscribers[event_type].append(callback)

    async def unsubscribe(self, event_type: str, callback: Subscriber) -> None:
        """Remove a subscriber."""
        async with self._lock:
            subs = self._subscribers.get(event_type, [])
            if callback in subs:
                subs.remove(callback)

    async def emit(self, event_type: str, **payload: Any) -> None:
        """Fire an event to all subscribers. Never raises."""
        event = {
            "type": event_type,
            "timestamp": datetime.now(UTC).isoformat(),
            **payload,
        }
        self._event_log.append(event)
        if len(self._event_log) > 1000:
            self._event_log = self._event_log[-1000:]

        subs = list((self._subscribers.get(event_type) or []) + (self._subscribers.get("*") or []))
        if not subs:
            return

        tasks = []
        for cb in subs:
            tasks.append(asyncio.create_task(self._safe_invoke(cb, event)))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def emit_task_started(self, task_id: str, stage: str, capability: str) -> None:
        await self.emit(ExecutionEvent.TASK_STARTED, task_id=task_id, stage=stage, capability=capability)

    async def emit_task_completed(self, task_id: str, stage: str, duration: float = 0.0) -> None:
        await self.emit(ExecutionEvent.TASK_COMPLETED, task_id=task_id, stage=stage, duration=duration)

    async def emit_task_failed(self, task_id: str, stage: str, error: str) -> None:
        await self.emit(ExecutionEvent.TASK_FAILED, task_id=task_id, stage=stage, error=error)

    async def emit_task_skipped(self, task_id: str, stage: str, reason: str) -> None:
        await self.emit(ExecutionEvent.TASK_SKIPPED, task_id=task_id, stage=stage, reason=reason)

    async def emit_plan_updated(self, revision: int, added_tasks: int = 0) -> None:
        await self.emit(ExecutionEvent.PLAN_UPDATED, revision=revision, added_tasks=added_tasks)

    async def emit_clarification_needed(self, plan: Any) -> None:
        await self.emit(ExecutionEvent.CLARIFICATION_NEEDED, clarification=plan.clarification_needed.model_dump(mode="json") if plan.clarification_needed else None)

    async def emit_capability_unhealthy(self, capability: str, reason: str) -> None:
        await self.emit(ExecutionEvent.CAPABILITY_UNHEALTHY, capability=capability, reason=reason)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _safe_invoke(self, cb: Subscriber, event: dict[str, Any]) -> None:
        try:
            await cb(event)
        except Exception:
            self.logger.error("event_subscriber_failed", event_type=event.get("type"), subscriber=str(cb))

    def drain(self, run_id: str) -> None:
        """Clear all subscribers for a run. Call when workflow ends."""
        self._subscribers.pop(run_id, None)


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_event_bus_singleton: EventBus | None = None


def get_event_bus() -> EventBus:
    """Return the process-wide EventBus singleton."""
    global _event_bus_singleton
    if _event_bus_singleton is None:
        _event_bus_singleton = EventBus()
    return _event_bus_singleton

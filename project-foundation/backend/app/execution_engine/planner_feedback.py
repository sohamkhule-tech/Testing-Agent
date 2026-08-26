"""
Planner Feedback Loop — continuous plan updates from execution events.

Listens to EventBus for task failures/completions and decides whether to
retry, skip, replan, or ask the user for clarification.
"""

from __future__ import annotations

from typing import Any

from app.context.execution_planner import ExecutionPlan, ExecutionPlanner, get_execution_planner
from app.execution_engine.capability_registry import CapabilityRegistry
from app.execution_engine.event_bus import EventBus, ExecutionEvent
from app.execution_engine.retry_policy import RetryPolicy
from app.logging import LoggerMixin


class PlannerFeedbackLoop(LoggerMixin):
    """
    Connects execution events → planner decisions → plan updates.
    """

    def __init__(
        self,
        planner: ExecutionPlanner | None = None,
        event_bus: EventBus | None = None,
        retry_policy: RetryPolicy | None = None,
        capability_registry: CapabilityRegistry | None = None,
    ) -> None:
        super().__init__()
        self.planner = planner or get_execution_planner()
        self.event_bus = event_bus
        self.retry_policy = retry_policy or RetryPolicy()
        self.capability_registry = capability_registry

    async def start(self) -> None:
        """Subscribe to relevant events on the bus."""
        if not self.event_bus:
            return
        await self.event_bus.subscribe(ExecutionEvent.TASK_FAILED, self._on_task_failed)
        await self.event_bus.subscribe(ExecutionEvent.TASK_COMPLETED, self._on_task_completed)
        await self.event_bus.subscribe(ExecutionEvent.CRAWLER_DISCOVERED, self._on_crawler_discovered)
        await self.event_bus.subscribe(ExecutionEvent.CAPABILITY_UNHEALTHY, self._on_capability_unhealthy)

    async def stop(self) -> None:
        if not self.event_bus:
            return
        await self.event_bus.unsubscribe(ExecutionEvent.TASK_FAILED, self._on_task_failed)
        await self.event_bus.unsubscribe(ExecutionEvent.TASK_COMPLETED, self._on_task_completed)
        await self.event_bus.unsubscribe(ExecutionEvent.CRAWLER_DISCOVERED, self._on_crawler_discovered)
        await self.event_bus.unsubscribe(ExecutionEvent.CAPABILITY_UNHEALTHY, self._on_capability_unhealthy)

    # ------------------------------------------------------------------
    # Decision logic
    # ------------------------------------------------------------------

    def decide_on_failure(self, task_id: str, error: str, attempt: int) -> str:
        """
        Returns: "retry" | "skip" | "replan" | "ask_user"
        """
        if self.retry_policy.should_retry(task_id, error, attempt=attempt):
            return "retry"
        if "timeout" in error.lower() or "connection" in error.lower():
            return "replan"
        if "auth" in error.lower() or "credential" in error.lower():
            return "ask_user"
        return "skip"

    def decide_after_discovery(self, plan: ExecutionPlan, discovered: list[str]) -> ExecutionPlan:
        """Add newly discovered modules to the plan."""
        return self.planner.replan_after_discovery(plan, discovered)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    async def _on_task_failed(self, event: dict[str, Any]) -> None:
        task_id = event.get("task_id", "")
        error = event.get("error", "")
        stage = event.get("stage", "")
        self.logger.warning("feedback_task_failed", task_id=task_id, stage=stage, error=error[:120])

        if self.capability_registry:
            self.capability_registry.record_failure(event.get("capability", ""))

        decision = self.decide_on_failure(task_id, error, attempt=1)
        self.logger.info("feedback_decision", task_id=task_id, decision=decision)

        if self.event_bus:
            await self.event_bus.emit("planner:decision", task_id=task_id, decision=decision)

    async def _on_task_completed(self, event: dict[str, Any]) -> None:
        capability = event.get("capability", "")
        duration = event.get("duration", 0.0)
        if self.capability_registry and capability:
            self.capability_registry.record_success(capability, duration)

    async def _on_crawler_discovered(self, event: dict[str, Any]) -> None:
        discovered = event.get("modules") or []
        self.logger.info("feedback_crawler_discovered", count=len(discovered), modules=discovered)

    async def _on_capability_unhealthy(self, event: dict[str, Any]) -> None:
        capability = event.get("capability", "")
        reason = event.get("reason", "")
        self.logger.warning("feedback_capability_unhealthy", capability=capability, reason=reason)

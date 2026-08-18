"""
Dependency Scheduler — topological execution with prerequisite checks and
Decision Engine integration (Phase 4.5).

Consumes the ExecutionGraph and DecisionEngine to determine which tasks
can execute next. Never executes blindly — always calls decide() first.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.execution_engine.capability_registry import CapabilityRegistry
from app.execution_engine.event_bus import EventBus
from app.execution_engine.execution_graph import ExecutionGraph, GraphNode
from app.logging import LoggerMixin

if TYPE_CHECKING:
    pass


class DependencyScheduler(LoggerMixin):
    """
    Only schedules a task when all dependencies are complete, the required
    capability is healthy, AND the DecisionEngine approves.
    """

    def __init__(
        self,
        graph: ExecutionGraph,
        event_bus: EventBus | None = None,
        capability_registry: CapabilityRegistry | None = None,
        decision_engine: Any | None = None,
    ) -> None:
        super().__init__()
        self.graph = graph
        self.event_bus = event_bus
        self.capability_registry = capability_registry
        if decision_engine is not None:
            self.decision_engine = decision_engine
        else:
            from app.reasoning.decision_engine import DecisionEngine
            self.decision_engine = DecisionEngine()
        self._reasoning = None
        self._constraints: list[Any] = []
        self._decisions: list[dict[str, Any]] = []
        self._stopped = False

    # ------------------------------------------------------------------
    # Reasoning context (set by workflow entrypoint)
    # ------------------------------------------------------------------

    def set_reasoning_context(self, reasoning: Any) -> None:
        self._reasoning = reasoning
        self._constraints = list(reasoning.constraints) if hasattr(reasoning, "constraints") else []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def next_ready(self) -> list[GraphNode]:
        """Return the next batch of ready-to-execute nodes, filtered by capability
        health AND DecisionEngine approval."""
        candidates = self.graph.get_ready_nodes()
        executable: list[GraphNode] = []
        for node in candidates:
            if not self._capability_ok(node):
                continue
            if not self._decide_can_execute(node):
                continue
            executable.append(node)
        return executable

    def decide_before_execute(self, node: GraphNode) -> bool:
        """
        Phase 4.5: ask the DecisionEngine before executing any task.

        Returns True if execution may proceed, False otherwise.
        """
        if self._stopped:
            node.skip("Scheduler is stopped")
            return False

        effective_status = node.status
        if node.retry_count > 0 and node.error:
            effective_status = "failed"

        decision = self.decision_engine.decide(
            stage=node.stage,
            task_id=node.id,
            current_status=effective_status,
            reasoning=self._reasoning,
            constraints=self._constraints,
            node=node,
            last_error=node.error,
        )
        self._decisions.append({
            "stage": node.stage, "task_id": node.id,
            "decision": decision.decision, "reasoning": decision.reasoning,
        })

        if decision.decision == "continue":
            return True
        elif decision.decision == "retry":
            node.retry_count += 1
            if node.retry_count <= node.max_retries:
                node.status = "ready"
                return True
            node.fail(f"Retries exhausted: {node.error}")
            self._block_descendants(node, f"Task {node.id} failed after {node.retry_count} retries")
            return False
        elif decision.decision == "skip":
            node.skip(decision.reasoning)
            return False
        elif decision.decision == "stop":
            self._stopped = True
            node.skip(f"Stopping condition: {decision.reasoning}")
            return False
        elif decision.decision == "ask_user":
            node.block(f"Awaiting user decision: {decision.reasoning}")
            return False
        elif decision.decision == "replan":
            node.block("Replanning requested")
            return False
        return False

    def on_task_completed(self, node_id: str, duration: float = 0.0) -> None:
        """Mark a node completed. Emits to EventBus."""
        node = self.graph.get_node(node_id)
        if node is None:
            return
        node.complete(duration)
        if self.event_bus:
            import asyncio
            asyncio.create_task(self.event_bus.emit_task_completed(node_id, node.stage, duration))

    def on_task_failed(self, node_id: str, error: str) -> None:
        """Mark a node as failed, block descendants. Emits to EventBus."""
        node = self.graph.get_node(node_id)
        if node is None:
            return
        node.fail(error)
        self._block_descendants(node, f"Upstream task {node_id} failed")
        if self.event_bus:
            import asyncio
            asyncio.create_task(self.event_bus.emit_task_failed(node_id, node.stage, error))

    def on_task_started(self, node_id: str) -> None:
        node = self.graph.get_node(node_id)
        if node is None:
            return
        node.start()
        if self.event_bus:
            import asyncio
            asyncio.create_task(self.event_bus.emit_task_started(node_id, node.stage, node.capability))

    def is_complete(self) -> bool:
        return self.graph.all_terminal() or self._stopped

    def summary(self) -> dict[str, Any]:
        s = self.graph.summary()
        s["stopped"] = self._stopped
        s["decisions"] = len(self._decisions)
        return s

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _capability_ok(self, node: GraphNode) -> bool:
        if not self.capability_registry or not node.capability:
            return True
        return self.capability_registry.is_healthy(node.capability)

    def _decide_can_execute(self, node: GraphNode) -> bool:
        """Ask DecisionEngine if this node can execute."""
        if not self.graph._all_parents_done(node):
            return False
        return True

    def _block_descendants(self, node: GraphNode, reason: str) -> None:
        for child_id in node.children:
            child = self.graph.get_node(child_id)
            if child and not child.is_terminal:
                child.block(reason)
                self._block_descendants(child, reason)

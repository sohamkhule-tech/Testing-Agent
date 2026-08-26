"""
Parallel Task Executor — concurrent execution of independent tasks.

Identifies tasks with no dependency conflicts and runs them concurrently
using asyncio. Never parallelises browser actions on the same page.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from app.execution_engine.capability_registry import CapabilityRegistry
from app.execution_engine.execution_graph import GraphNode
from app.execution_engine.scheduler import DependencyScheduler
from app.logging import LoggerMixin

TaskFn = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


class ParallelTaskExecutor(LoggerMixin):
    """
    Runs batches of independent tasks concurrently, respecting:
    - Dependency constraints (only ready nodes)
    - Capability health
    - Browser resource exclusivity (no parallel browser per page)
    """

    def __init__(
        self,
        scheduler: DependencyScheduler,
        capability_registry: CapabilityRegistry | None = None,
        max_concurrency: int = 4,
    ) -> None:
        super().__init__()
        self.scheduler = scheduler
        self.capability_registry = capability_registry
        self.max_concurrency = max_concurrency
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._active_browser_pages: set[str] = set()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute_ready_batch(
        self,
        task_fn: TaskFn,
        *task_fn_args: Any,
    ) -> dict[str, dict[str, Any]]:
        """
        Execute all currently ready nodes, respecting concurrency limits.
        Returns {node_id: result_dict}.

        task_fn receives (node, *task_fn_args) and returns a result dict.
        """
        ready = self.scheduler.next_ready()
        if not ready:
            return {}

        # Partition: browser-touching tasks go sequentially, others in parallel
        browser_tasks = [n for n in ready if self._is_browser_capability(n.capability)]
        compute_tasks = [n for n in ready if n not in browser_tasks]

        results: dict[str, dict[str, Any]] = {}

        # Compute tasks run in parallel
        if compute_tasks:
            parallel_results = await self._run_parallel(compute_tasks, task_fn, *task_fn_args)
            results.update(parallel_results)

        # Browser tasks run sequentially to avoid conflicts
        for node in browser_tasks:
            results[node.id] = await self._run_single(node, task_fn, *task_fn_args)

        return results

    async def run_all(
        self,
        task_fn: TaskFn,
        *task_fn_args: Any,
    ) -> dict[str, dict[str, Any]]:
        """
        Keep executing ready batches until no more tasks are ready.
        Respects the retry policy and scheduler state throughout.
        """
        all_results: dict[str, dict[str, Any]] = {}
        while not self.scheduler.is_complete():
            batch = await self.execute_ready_batch(task_fn, *task_fn_args)
            if not batch:
                pending = [n for n in self.scheduler.graph.nodes.values() if not n.is_terminal]
                if not pending:
                    break
                blocked = [n.id for n in pending]
                self.logger.warning("executor_blocked", blocked_tasks=blocked)
                break
            all_results.update(batch)
        return all_results

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    @staticmethod
    def _is_browser_capability(capability: str) -> bool:
        """Capabilities that require exclusive browser access."""
        return capability in ("open_page", "navigate", "discover", "capture_screenshot", "extract_forms")

    async def _run_parallel(
        self,
        nodes: list[GraphNode],
        task_fn: TaskFn,
        *args: Any,
    ) -> dict[str, dict[str, Any]]:
        """Run a batch of compute nodes concurrently."""
        async def _run_one(node: GraphNode) -> tuple[str, dict[str, Any]]:
            async with self._semaphore:
                return node.id, await self._run_single(node, task_fn, *args)

        gather_results = await asyncio.gather(
            *[_run_one(n) for n in nodes],
            return_exceptions=True,
        )
        results: dict[str, dict[str, Any]] = {}
        for item in gather_results:
            if isinstance(item, Exception):
                self.logger.error("parallel_task_crashed", error=str(item))
            elif isinstance(item, tuple):
                results[item[0]] = item[1]
        return results

    async def _run_single(
        self,
        node: GraphNode,
        task_fn: TaskFn,
        *args: Any,
    ) -> dict[str, Any]:
        """Execute a single node and update scheduler state."""
        self.scheduler.on_task_started(node.id)
        if self.capability_registry:
            self.capability_registry.set_busy(node.capability, True)

        try:
            result = await task_fn(node, *args)
            duration = result.get("duration_seconds", 0.0) if isinstance(result, dict) else 0.0
            self.scheduler.on_task_completed(node.id, duration)
            if self.capability_registry:
                self.capability_registry.record_success(node.capability, duration)
            return result
        except Exception as e:
            self.scheduler.on_task_failed(node.id, str(e))
            if self.capability_registry:
                self.capability_registry.record_failure(node.capability)
            return {"success": False, "error": str(e), "duration_seconds": 0.0}

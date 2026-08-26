"""
Execution Graph — DAG from ExecutionPlan with dependency-aware task scheduling.

Built FROM an ExecutionPlan. Each GraphNode wraps an ExecutionTask/SubTask
with parent references, dependency tracking, and execution state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.context.execution_planner import ExecutionPlan
from app.logging import LoggerMixin

# Topological sort order for guaranteed progress
_STAGE_PRIORITY: dict[str, int] = {
    "trigger": 0,
    "crawler": 1,
    "inventory_aggregator": 2,
    "test_design": 3,
    "human_review": 4,
    "code_generation": 5,
    "execution": 6,
}


@dataclass
class GraphNode:
    """A node in the execution DAG."""

    id: str
    name: str
    stage: str
    capability: str
    description: str = ""
    parents: list[str] = field(default_factory=list)        # nodes that must complete before this
    children: list[str] = field(default_factory=list)       # nodes that depend on this
    status: str = "pending"  # pending | ready | running | completed | skipped | failed | blocked
    retry_count: int = 0
    max_retries: int = 3
    discovered: bool = False
    duration: float = 0.0
    error: str | None = None

    @property
    def is_ready(self) -> bool:
        return self.status in ("pending", "ready")

    @property
    def is_terminal(self) -> bool:
        return self.status in ("completed", "skipped", "failed", "blocked")

    def start(self) -> None:
        self.status = "running"

    def complete(self, duration: float = 0.0) -> None:
        self.status = "completed"
        self.duration = duration

    def fail(self, error: str) -> None:
        self.status = "failed"
        self.error = error

    def skip(self, reason: str = "") -> None:
        self.status = "skipped"
        self.error = reason or "skipped"

    def block(self, reason: str) -> None:
        self.status = "blocked"
        self.error = reason


class ExecutionGraph(LoggerMixin):
    """
    DAG built from an ExecutionPlan.

    Nodes are arranged by dependency. The scheduler uses this graph to
    determine which tasks are ready. Only nodes whose parents are all
    completed can transition to 'ready'.
    """

    def __init__(self) -> None:
        super().__init__()
        self.nodes: dict[str, GraphNode] = {}
        self._stage_count: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, plan: ExecutionPlan) -> None:
        """Rebuild graph nodes from an ExecutionPlan."""
        self.nodes.clear()
        self._stage_count.clear()

        for task in plan.tasks:
            for st in task.subtasks:
                node = GraphNode(
                    id=st.id,
                    name=st.description,
                    stage=task.stage,
                    capability=st.capability or task.capability,
                    description=task.description,
                    parents=list(st.depends_on),
                    discovered=st.discovered,
                )
                self.nodes[node.id] = node

        # Wire children from parent references
        for node in self.nodes.values():
            for parent_id in node.parents:
                if parent_id in self.nodes:
                    parent = self.nodes[parent_id]
                    if node.id not in parent.children:
                        parent.children.append(node.id)

        self.logger.info("execution_graph_built", node_count=len(self.nodes))

    def rebuild(self, plan: ExecutionPlan) -> None:
        """In-place rebuild (e.g. after dynamic replanning)."""
        self.build(plan)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_ready_nodes(self) -> list[GraphNode]:
        """Nodes whose parents are all completed and which are pending/ready."""
        ready: list[GraphNode] = []
        for node in self.nodes.values():
            if not node.is_ready:
                continue
            if self._all_parents_done(node):
                node.status = "ready"
                ready.append(node)
        # Sort by stage priority for deterministic execution
        ready.sort(key=lambda n: (_STAGE_PRIORITY.get(n.stage, 99), n.id))
        return ready

    def get_node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def get_nodes_by_stage(self, stage: str) -> list[GraphNode]:
        return [n for n in self.nodes.values() if n.stage == stage]

    def _all_parents_done(self, node: GraphNode) -> bool:
        if not node.parents:
            return True
        return all(
            self.nodes.get(pid) and self.nodes[pid].status == "completed"
            for pid in node.parents
        )

    def all_terminal(self) -> bool:
        return all(n.is_terminal for n in self.nodes.values())

    def progress(self) -> float:
        if not self.nodes:
            return 0.0
        done = sum(1 for n in self.nodes.values() if n.is_terminal)
        return round((done / len(self.nodes)) * 100, 1)

    def summary(self) -> dict[str, Any]:
        return {
            "total_nodes": len(self.nodes),
            "completed": sum(1 for n in self.nodes.values() if n.status == "completed"),
            "failed": sum(1 for n in self.nodes.values() if n.status == "failed"),
            "skipped": sum(1 for n in self.nodes.values() if n.status == "skipped"),
            "blocked": sum(1 for n in self.nodes.values() if n.status == "blocked"),
            "running": sum(1 for n in self.nodes.values() if n.status == "running"),
            "ready": sum(1 for n in self.nodes.values() if n.status == "ready"),
            "progress": self.progress(),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_graph_singleton: ExecutionGraph | None = None


def get_execution_graph() -> ExecutionGraph:
    global _graph_singleton
    if _graph_singleton is None:
        _graph_singleton = ExecutionGraph()
    return _graph_singleton

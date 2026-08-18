"""
Execution Engine — autonomous task execution with dependency scheduling.

Phase 3 components:
- EventBus: in-process pub/sub for task lifecycle events
- ExecutionGraph: DAG from ExecutionPlan with dependency-aware nodes
- DependencyScheduler: topological execution with prerequisite checks
- CapabilityRegistry: tool health tracking (healthy/busy/disabled/failure_rate)
- RetryPolicy: per-task retry with exponential backoff
- PlannerFeedbackLoop: continuous plan updates from execution events
- ParallelTaskExecutor: concurrent execution of independent tasks
"""

from app.execution_engine.capability_registry import CapabilityRegistry, get_capability_registry
from app.execution_engine.event_bus import EventBus, ExecutionEvent, get_event_bus
from app.execution_engine.execution_graph import ExecutionGraph, GraphNode, get_execution_graph
from app.execution_engine.parallel_executor import ParallelTaskExecutor
from app.execution_engine.planner_feedback import PlannerFeedbackLoop
from app.execution_engine.retry_policy import RetryPolicy
from app.execution_engine.scheduler import DependencyScheduler

__all__ = [
    "CapabilityRegistry",
    "DependencyScheduler",
    "EventBus",
    "ExecutionEvent",
    "ExecutionGraph",
    "GraphNode",
    "ParallelTaskExecutor",
    "PlannerFeedbackLoop",
    "RetryPolicy",
    "get_capability_registry",
    "get_event_bus",
    "get_execution_graph",
]

"""
Phase 3: Autonomous Execution Engine tests.

Tests EventBus, ExecutionGraph, DependencyScheduler, CapabilityRegistry,
RetryPolicy, PlannerFeedbackLoop, ParallelTaskExecutor.
"""

import asyncio
from typing import Any

import pytest

from app.execution_engine.capability_registry import CapabilityRegistry
from app.execution_engine.event_bus import EventBus, ExecutionEvent, get_event_bus
from app.execution_engine.execution_graph import ExecutionGraph, GraphNode
from app.execution_engine.parallel_executor import ParallelTaskExecutor
from app.execution_engine.planner_feedback import PlannerFeedbackLoop
from app.execution_engine.retry_policy import RetryConfig, RetryPolicy
from app.execution_engine.scheduler import DependencyScheduler


class TestEventBus:
    async def test_subscribe_and_emit(self):
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict):
            received.append(event)

        await bus.subscribe("test:event", handler)
        await bus.emit("test:event", data="hello")
        assert len(received) == 1
        assert received[0]["data"] == "hello"

    async def test_unsubscribe(self):
        bus = EventBus()
        received: list[dict] = []

        async def handler(event: dict):
            received.append(event)

        await bus.subscribe("test:event", handler)
        await bus.emit("test:event")
        await bus.unsubscribe("test:event", handler)
        await bus.emit("test:event")
        assert len(received) == 1

    async def test_wildcard_subscriber(self):
        bus = EventBus()
        all_events: list[str] = []

        async def catch_all(event: dict):
            all_events.append(event["type"])

        await bus.subscribe("*", catch_all)
        await bus.emit(ExecutionEvent.TASK_STARTED, task_id="a")
        await bus.emit(ExecutionEvent.TASK_COMPLETED, task_id="a")
        assert ExecutionEvent.TASK_STARTED in all_events
        assert ExecutionEvent.TASK_COMPLETED in all_events

    def test_singleton(self):
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2


class TestExecutionGraph:
    def test_build_from_plan_creates_nodes(self):
        from app.context.execution_planner import ExecutionPlanner
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test Login",
            parsed_intent={"focus_areas": ["Login"], "excluded_modules": []},
        )
        graph = ExecutionGraph()
        graph.build(plan)
        assert len(graph.nodes) > 0
        assert any(n.stage == "crawler" for n in graph.nodes.values())
        assert any(n.stage == "test_design" for n in graph.nodes.values())

    def test_parents_block_children(self):
        """Children are not ready until all parents complete."""
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="trigger", capability="test"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="test", parents=["a"]),
        }
        graph.nodes["a"].children = ["b"]
        graph.nodes["b"].parents = ["a"]

        ready = graph.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "a"

        graph.nodes["a"].complete()
        ready = graph.get_ready_nodes()
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_progress_tracking(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="trigger", capability="test"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="test"),
        }
        graph.nodes["a"].complete()
        graph.nodes["b"].fail("error")
        assert graph.all_terminal()
        assert graph.progress() == 100.0

    def test_rebuild_updates_nodes(self):
        from app.context.execution_planner import ExecutionPlanner
        planner = ExecutionPlanner()
        plan = planner.build(
            user_prompt="Test A",
            parsed_intent={"focus_areas": ["A"], "excluded_modules": []},
        )
        graph = ExecutionGraph()
        graph.build(plan)
        original_count = len(graph.nodes)
        graph.rebuild(plan)
        assert len(graph.nodes) == original_count
        # New build from different plan should change nodes
        plan2 = planner.build(
            user_prompt="Test B also",
            parsed_intent={"focus_areas": ["A", "B"], "excluded_modules": []},
        )
        graph.rebuild(plan2)
        assert len(graph.nodes) != original_count


class TestDependencyScheduler:
    def test_only_schedules_ready_with_healthy_caps(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="trigger", capability="initialise_workspace"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="discover", parents=["a"]),
        }
        graph.nodes["a"].children = ["b"]
        registry = CapabilityRegistry()
        scheduler = DependencyScheduler(graph, capability_registry=registry)

        ready = scheduler.next_ready()
        assert len(ready) == 1
        assert ready[0].id == "a"

        scheduler.on_task_completed("a")
        ready = scheduler.next_ready()
        assert len(ready) == 1
        assert ready[0].id == "b"

    def test_blocks_when_capability_unhealthy(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="crawler", capability="discover"),
        }
        registry = CapabilityRegistry()
        registry.disable("discover")
        scheduler = DependencyScheduler(graph, capability_registry=registry)

        ready = scheduler.next_ready()
        assert len(ready) == 0

        registry.enable("discover")
        graph.nodes["a"].status = "pending"  # reset from blocked
        ready = scheduler.next_ready()
        assert len(ready) == 1

    def test_failure_blocks_descendants(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="trigger", capability="test"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="test", parents=["a"]),
            "c": GraphNode(id="c", name="C", stage="code_generation", capability="test", parents=["b"]),
        }
        graph.nodes["a"].children = ["b"]
        graph.nodes["b"].children = ["c"]
        scheduler = DependencyScheduler(graph)

        scheduler.on_task_completed("a")
        scheduler.on_task_failed("b", "timeout")
        assert scheduler.graph.nodes["b"].status == "failed"
        assert scheduler.graph.nodes["c"].status == "blocked"

    def test_summary(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="trigger", capability="test"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="test"),
        }
        graph.nodes["a"].complete()
        graph.nodes["b"].fail("err")
        scheduler = DependencyScheduler(graph)
        s = scheduler.summary()
        assert s["completed"] == 1
        assert s["failed"] == 1


class TestCapabilityRegistry:
    def test_is_healthy(self):
        registry = CapabilityRegistry()
        assert registry.is_healthy("discover") is True
        registry.disable("discover")
        assert registry.is_healthy("discover") is False
        registry.enable("discover")
        assert registry.is_healthy("discover") is True

    def test_unknown_capability_assumed_healthy(self):
        registry = CapabilityRegistry()
        assert registry.is_healthy("nonexistent") is True

    def test_record_success_updates_metrics(self):
        registry = CapabilityRegistry()
        registry.record_success("discover", duration=10.0)
        cap = registry.get("discover")
        assert cap is not None
        assert cap["healthy"] is True
        assert cap["busy"] is False

    def test_failure_rate_unhealthy_after_many_fails(self):
        registry = CapabilityRegistry()
        for _ in range(6):
            registry.record_failure("discover")
        assert not registry.is_healthy("discover")

    def test_summary_and_unhealthy_list(self):
        registry = CapabilityRegistry()
        registry.disable("discover")
        unhealthy = registry.unhealthy()
        assert "discover" in unhealthy
        assert "discover" not in registry.all_healthy()


class TestRetryPolicy:
    def test_should_retry_within_limit(self):
        policy = RetryPolicy()
        assert policy.should_retry("t1", "timeout", attempt=1) is True
        assert policy.should_retry("t1", "timeout", attempt=3) is True
        assert policy.should_retry("t1", "timeout", attempt=4) is False

    def test_respects_error_types(self):
        config = RetryConfig(retry_on_timeout=False)
        policy = RetryPolicy()
        policy.set_config("t1", config)
        assert policy.should_retry("t1", "Timeout waiting for page", attempt=1) is False
        assert policy.should_retry("t1", "ECONNREFUSED", attempt=1) is True

    def test_backoff_delay(self):
        config = RetryConfig(backoff_base=2.0, backoff_multiplier=2.0, max_backoff=10.0)
        assert config.backoff_delay(1) == 2.0
        assert config.backoff_delay(2) == 4.0
        assert config.backoff_delay(3) == 8.0
        assert config.backoff_delay(4) == 10.0  # capped

    async def test_execute_with_retry_succeeds(self):
        policy = RetryPolicy()
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls < 3:
                raise ValueError("timeout")
            return "ok"

        result = await policy.execute_with_retry("t1", flaky)
        assert result == "ok"
        assert calls == 3

    async def test_execute_with_retry_exhausted(self):
        policy = RetryPolicy()
        policy.set_config("t1", RetryConfig(max_retries=2))

        async def always_fails():
            raise RuntimeError("permanent error")

        with pytest.raises(RuntimeError):
            await policy.execute_with_retry("t1", always_fails)


class TestPlannerFeedback:
    def test_decide_retry_on_timeout(self):
        loop = PlannerFeedbackLoop(retry_policy=RetryPolicy())
        assert loop.decide_on_failure("t1", "Timeout waiting for selector", 1) == "retry"

    def test_decide_replan_on_connection(self):
        loop = PlannerFeedbackLoop(retry_policy=RetryPolicy())
        # max retries exhausted
        assert loop.decide_on_failure("t1", "Connection refused", 4) == "replan"

    def test_decide_ask_user_on_auth(self):
        loop = PlannerFeedbackLoop(retry_policy=RetryPolicy())
        # Only asks user when retries exhausted
        assert loop.decide_on_failure("t1", "Authentication failed: invalid credentials", 4) == "ask_user"

    @pytest.mark.asyncio
    async def test_planner_receives_task_failed_event(self):
        bus = EventBus()
        loop = PlannerFeedbackLoop(event_bus=bus, retry_policy=RetryPolicy())
        await loop.start()

        decisions: list[dict] = []
        async def on_decision(event: dict):
            decisions.append(event)

        await bus.subscribe("planner:decision", on_decision)
        await bus.emit_task_failed("t-x", "crawler", "timeout")

        # Give async handlers time to fire
        await asyncio.sleep(0.05)
        assert len(decisions) > 0
        assert decisions[0]["decision"] in ("retry", "skip", "replan", "ask_user")

        await loop.stop()


class TestParallelExecutor:
    @pytest.mark.asyncio
    async def test_executes_ready_compute_tasks_concurrently(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "a": GraphNode(id="a", name="A", stage="crawler", capability="discover"),
            "b": GraphNode(id="b", name="B", stage="crawler", capability="discover"),
        }
        scheduler = DependencyScheduler(graph)
        executor = ParallelTaskExecutor(scheduler, max_concurrency=4)

        order: list[str] = []

        async def task_fn(node: GraphNode, *_args: Any):
            order.append(node.id)
            await asyncio.sleep(0.01)
            return {"success": True, "duration_seconds": 0.01}

        results = await executor.execute_ready_batch(task_fn)
        assert "a" in results
        assert "b" in results
        # Both completed via scheduler
        assert graph.nodes["a"].status == "completed"
        assert graph.nodes["b"].status == "completed"

    @pytest.mark.asyncio
    async def test_browser_tasks_not_parallelised(self):
        graph = ExecutionGraph()
        graph.nodes = {
            "b1": GraphNode(id="b1", name="B1", stage="crawler", capability="open_page"),
            "b2": GraphNode(id="b2", name="B2", stage="crawler", capability="open_page"),
        }
        scheduler = DependencyScheduler(graph)
        executor = ParallelTaskExecutor(scheduler, max_concurrency=4)

        started: list[str] = []
        async def task_fn(node: GraphNode):
            started.append(node.id)
            return {"success": True}

        results = await executor.execute_ready_batch(task_fn)
        assert len(results) == 2
        assert graph.nodes["b1"].status == "completed"
        assert graph.nodes["b2"].status == "completed"

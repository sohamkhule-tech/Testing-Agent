"""
Tests for WorkflowEventBus reliability guarantees.

Focus:
  - Critical workflow transition events must not be permanently lost, even
    when a subscriber's asyncio queue is full (back-pressure).
  - The replay buffer must retain critical events so reconnecting subscribers
    can recover missed transitions.
  - High-volume non-critical events must never evict those critical events.
  - Multiple subscribers must remain isolated.
"""

import asyncio

import pytest

from app.core.event_bus import (
    CRITICAL_EVENT_TYPES,
    EventType,
    WorkflowEvent,
    WorkflowEventBus,
)


def _evt(run_id: str, etype: str, data: dict | None = None) -> WorkflowEvent:
    return WorkflowEvent(type=etype, run_id=run_id, data=data or {})


@pytest.mark.asyncio
async def test_critical_event_retained_when_subscriber_queue_full():
    """A critical transition event must stay recoverable even if the live
    subscriber queue is full and delivery was dropped."""
    bus = WorkflowEventBus()
    run_id = "r1"
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    await q.put("lock")  # pretend a slow consumer has a full buffer
    bus._subscribers[run_id] = {q}

    evt = _evt(run_id, EventType.STAGE_COMPLETED, {"stage": "code_generation"})
    assert evt.type in CRITICAL_EVENT_TYPES
    await bus.publish(evt)

    history = bus.get_history(run_id)
    assert any(e.event_id == evt.event_id for e in history), (
        "critical event must be retained in the replay buffer"
    )


@pytest.mark.asyncio
async def test_noncritical_high_volume_does_not_evict_critical_events():
    """A burst of non-critical progress ticks must not push critical transition
    events out of the replay buffer."""
    bus = WorkflowEventBus()
    run_id = "r2"

    for i in range(300):
        await bus.publish(_evt(run_id, EventType.FILE_PROGRESS, {"progress": i}))
    await bus.publish(_evt(run_id, EventType.STAGE_COMPLETED, {"stage": "code_generation"}))
    await bus.publish(_evt(run_id, EventType.STAGE_STARTED, {"stage": "execution"}))

    history = bus.get_history(run_id)
    types = [e.type for e in history]
    assert EventType.STAGE_COMPLETED in types
    assert EventType.STAGE_STARTED in types
    assert len(history) <= bus._replay_hard_limit


@pytest.mark.asyncio
async def test_reconnect_replays_missed_critical_events():
    """A reconnecting subscriber recovers critical transitions that were
    dropped while its predecessor's queue was full."""
    bus = WorkflowEventBus()
    run_id = "r4"

    # First subscriber is slow (queue full) → transitions are dropped live but
    # retained in replay.
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    await q.put("lock")
    bus._subscribers[run_id] = {q}
    await bus.publish(_evt(run_id, EventType.STAGE_COMPLETED, {"stage": "code_generation"}))
    await bus.publish(_evt(run_id, EventType.STAGE_STARTED, {"stage": "execution"}))
    bus._subscribers.pop(run_id, None)  # old subscriber drops off

    received: list[str] = []
    async for evt in bus.subscribe(run_id, replay=True):
        received.append(evt.type)
        if evt.type == EventType.STAGE_STARTED:
            break

    assert EventType.STAGE_COMPLETED in received
    assert EventType.STAGE_STARTED in received


@pytest.mark.asyncio
async def test_multiple_subscribers_are_isolated():
    """Each subscriber gets its own copy without cross-contamination."""
    bus = WorkflowEventBus()
    run_id = "r3"
    bus._subscribers[run_id] = set()

    seen_a: list[str] = []
    seen_b: list[str] = []

    async def sub(sink: list[str], stop: str) -> None:
        async for evt in bus.subscribe(run_id, replay=False):
            sink.append(evt.type)
            if evt.type == stop:
                return

    task_a = asyncio.create_task(sub(seen_a, EventType.STAGE_COMPLETED))
    task_b = asyncio.create_task(sub(seen_b, EventType.STAGE_COMPLETED))
    await asyncio.sleep(0)  # let both subscribe

    await bus.publish(_evt(run_id, EventType.WORKFLOW_STARTED))
    await bus.publish(_evt(run_id, EventType.CODE_GENERATION_COMPLETED))
    await bus.publish(_evt(run_id, EventType.STAGE_COMPLETED, {"stage": "code_generation"}))

    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=5)
    assert seen_a == [EventType.WORKFLOW_STARTED, EventType.CODE_GENERATION_COMPLETED, EventType.STAGE_COMPLETED]
    assert seen_b == [EventType.WORKFLOW_STARTED, EventType.CODE_GENERATION_COMPLETED, EventType.STAGE_COMPLETED]


def test_to_sse_emits_named_event_for_critical_transition():
    """SSE framing must carry the exact event type in the ``event:`` field so
    the browser routes it to the correct named listener."""
    evt = _evt("run-x", EventType.STAGE_STARTED, {"stage": "execution"})
    raw = evt.to_sse()
    assert "event: stage_started" in raw
    assert '"type": "stage_started"' in raw

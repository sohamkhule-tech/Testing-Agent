"""
Regression tests for the single-active-stage / duplicate-run workflow fix.

Covers the two backend changes:
  1. ``GET /runs/{id}/state`` ``completed_stages`` reconstruction — the list
     must never omit an actually-completed stage (e.g. ``test_design``) even
     when a partial ``checkpoint.json`` exists, and must never mark the
     recorded failed stage as completed.
  2. ``POST /runs/{id}/resume`` — reject resuming a run that is PAUSED awaiting
     human review, so Approve + Resume cannot spawn two workflow executions for
     the same run.
"""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.routes.trigger import get_run_state, resume_run
from app.constants import RunStatus as RS


class _FakeRun:
    def __init__(self, status, current_stage, workspace_path, error=None):
        self.status = status
        self.current_stage = current_stage
        self.workspace_path = str(workspace_path)
        self.error = error


class _FakeService:
    def __init__(self, run):
        self._run = run

    async def get_run(self, run_id):
        return self._run


def _write_contract(ws: Path, rel: str):
    (ws / rel).parent.mkdir(parents=True, exist_ok=True)
    (ws / rel).write_text("{}", encoding="utf-8")


def _ws_with_pre_review_done(tmp_path: Path) -> Path:
    """Create a workspace that completed trigger→crawler→inventory→test_design."""
    ws = tmp_path / "workspace"
    _write_contract(ws, "contracts/crawl-package.json")
    _write_contract(ws, "contracts/inventory.json")
    _write_contract(ws, "contracts/test-plan.json")
    return ws


@pytest.mark.asyncio
async def test_state_completed_stages_never_omit_test_design_with_partial_checkpoint(tmp_path):
    """A partial checkpoint (without test_design) must be reconciled with file
    evidence so test_design is still reported completed."""
    ws = _ws_with_pre_review_done(tmp_path)
    cp = {"completed_stages": ["trigger", "crawler", "inventory", "inventory_aggregator"]}
    _write_contract(ws, "contracts/checkpoint.json")
    (ws / "contracts" / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")

    run = _FakeRun(RS.RUNNING, "human_review", ws)
    service = _FakeService(run)

    result = await get_run_state(uuid4(), service)
    completed = result["completed_stages"]
    # test_design's artifact exists -> must NOT be omitted, even though the
    # (partial) checkpoint did not list it.
    assert "test_design" in completed
    # dedup: no duplicate entries introduced
    assert completed.count("test_design") == 1
    assert completed.count("inventory") == 1
    assert completed.count("inventory_aggregator") == 1


@pytest.mark.asyncio
async def test_state_completed_stages_includes_full_pre_review(tmp_path):
    """Without a checkpoint, filesystem inference yields the full pre-review set."""
    ws = _ws_with_pre_review_done(tmp_path)
    run = _FakeRun(RS.PAUSED, "awaiting_review", ws)
    service = _FakeService(run)

    result = await get_run_state(uuid4(), service)
    completed = result["completed_stages"]
    for stage in ("trigger", "crawler", "inventory", "inventory_aggregator", "test_design"):
        assert stage in completed
    # Human review is not completed/paused-and-being-run yet
    assert "human_review" not in completed


@pytest.mark.asyncio
async def test_state_failed_stage_never_marked_completed(tmp_path):
    """If a stage is the recorded failed stage, it must not appear completed."""
    ws = _ws_with_pre_review_done(tmp_path)
    # test_design failed: no test-plan.json; checkpoint records the failure.
    (ws / "contracts" / "test-plan.json").unlink(missing_ok=True)
    cp = {
        "completed_stages": ["trigger", "crawler", "inventory", "inventory_aggregator"],
        "failed_stage": "test_design",
    }
    _write_contract(ws, "contracts/checkpoint.json")
    (ws / "contracts" / "checkpoint.json").write_text(json.dumps(cp), encoding="utf-8")

    run = _FakeRun(RS.FAILED, "test_design", ws, error="boom")
    service = _FakeService(run)

    result = await get_run_state(uuid4(), service)
    assert result["failed_stage"] == "test_design"
    assert "test_design" not in result["completed_stages"]


@pytest.mark.asyncio
async def test_resume_rejected_when_awaiting_review(tmp_path):
    """A paused awaiting-review run must NOT be resumable (prevents a second
    workflow execution alongside the approve/post-review path)."""
    ws = _ws_with_pre_review_done(tmp_path)
    run = _FakeRun(RS.PAUSED, "awaiting_review", ws)
    service = _FakeService(run)

    with pytest.raises(HTTPException) as excinfo:
        await resume_run(uuid4(), service)
    assert excinfo.value.status_code == 400
    assert "awaiting human review" in excinfo.value.detail.lower()

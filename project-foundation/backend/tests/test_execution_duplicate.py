"""
Regression tests for the duplicate-execution fixes.

Covers:
- The execution-stage checkpoint now recognizes the REAL artifact location,
  so a resumed workflow no longer re-runs Playwright after execution already
  produced artifacts.
- The post-review approve endpoint is idempotent for a single run: two approve
  calls spawn exactly ONE background code-generation + execution workflow.

No real Playwright / browser / LLM is used.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

from app.api.routes import trigger as trigger_routes
from app.api.routes.trigger import (
    _acquire_post_review,
    _release_post_review,
    approve_run,
)
from app.constants import RunStatus
from app.workflows.trigger_workflow import (
    PlatformWorkflowState,
    _is_stage_completed,
    _with_checkpoint,
    execution_node,
)

RUN = "22222222-2222-2222-2222-222222222222"


class _FakeTask:
    """Minimal stand-in for asyncio.Task used to count spawns."""

    def __init__(self, coro):
        self._coro = coro

    def add_done_callback(self, cb):
        pass

    def cancelled(self):
        return False

    def exception(self):
        return None


def _entity(status) -> SimpleNamespace:
    return SimpleNamespace(
        status=status,
        workspace_path=str(Path.home()),
        requested_by="user",
    )


@pytest.mark.unit
class TestExecutionStageCheckpoint:
    def test_execution_not_completed_without_artifacts(self, tmp_path):
        assert _is_stage_completed(str(tmp_path), "execution") is False

    def test_execution_completed_with_metadata_artifact(self, tmp_path):
        p = tmp_path / "artifacts" / "generated-tests" / "execution-artifacts"
        p.mkdir(parents=True)
        (p / "execution-metadata.json").write_text("{}", encoding="utf-8")
        assert _is_stage_completed(str(tmp_path), "execution") is True

    def test_execution_completed_with_report_summary(self, tmp_path):
        p = tmp_path / "artifacts" / "generated-tests" / "execution-artifacts" / "reports"
        p.mkdir(parents=True)
        (p / "execution-summary.json").write_text("{}", encoding="utf-8")
        assert _is_stage_completed(str(tmp_path), "execution") is True

    def test_stale_root_execution_summary_no_longer_counts(self, tmp_path):
        (tmp_path / "execution-summary.json").write_text("{}", encoding="utf-8")
        assert _is_stage_completed(str(tmp_path), "execution") is False

    def test_code_generation_checkpoint_unchanged(self, tmp_path):
        meta = tmp_path / "artifacts" / "generated-tests" / "playwright"
        meta.mkdir(parents=True)
        (meta / "code-generation-metadata.json").write_text("{}", encoding="utf-8")
        assert _is_stage_completed(str(tmp_path), "code_generation") is True


@pytest.mark.unit
class TestExecutionNodeSkippedOnResume:
    @pytest.mark.asyncio
    async def test_resume_skips_execution_when_artifacts_exist(self, tmp_path):
        artifacts = tmp_path / "artifacts" / "generated-tests" / "execution-artifacts"
        artifacts.mkdir(parents=True)
        (artifacts / "execution-metadata.json").write_text("{}", encoding="utf-8")

        state = PlatformWorkflowState(
            run_id=RUN,
            status=RunStatus.RUNNING,
            workspace_path=str(tmp_path),
            completed_nodes=[],
            node_results={},
            metadata={},
            agent_state=None,
            execution_plan=None,
        )
        wrapped = _with_checkpoint(execution_node, "execution")
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            next_state = await wrapped(state)

        # Stage marked completed WITHOUT invoking execution_node (no
        # execution_service was provided, so calling it would have raised).
        assert "execution" in next_state.completed_nodes
        assert next_state.node_results["execution"].status == "completed"


@pytest.mark.unit
class TestPostReviewApproveGuard:
    def test_guard_blocks_duplicate_and_releases(self):
        assert _acquire_post_review(RUN) is True
        assert _acquire_post_review(RUN) is False  # duplicate blocked
        _release_post_review(RUN)
        assert _acquire_post_review(RUN) is True
        _release_post_review(RUN)

    @pytest.mark.asyncio
    async def test_duplicate_approve_spawns_exactly_one_workflow(self, monkeypatch):
        spawned = {"count": 0}

        def _fake_create_task(coro):
            spawned["count"] += 1
            coro.close()  # never scheduled (counting test); silence "never awaited"
            return _FakeTask(None)

        async def _fake_run_post_review(*args, **kwargs):
            return None

        monkeypatch.setattr(trigger_routes.asyncio, "create_task", _fake_create_task)
        monkeypatch.setattr(trigger_routes, "_run_post_review_workflow", _fake_run_post_review)
        monkeypatch.setattr(trigger_routes, "get_code_generation_agent", lambda: object())

        service = SimpleNamespace()
        service.update_status = AsyncMock(return_value=True)
        service.get_run = AsyncMock(side_effect=lambda run_id: _entity(RunStatus.PAUSED))

        try:
            first = await approve_run(UUID(RUN), service=service)
            assert first["status"] == "running"
            assert spawned["count"] == 1
            assert service.update_status.await_count == 1

            second = await approve_run(UUID(RUN), service=service)
            assert second["status"] == "running"
            assert "already in progress" in second["message"]
            # No second workflow, no second status write.
            assert spawned["count"] == 1
            assert service.update_status.await_count == 1
        finally:
            _release_post_review(RUN)

    @pytest.mark.asyncio
    async def test_already_completed_approve_is_noop(self, monkeypatch):
        service = SimpleNamespace()
        service.get_run = AsyncMock(side_effect=lambda run_id: _entity(RunStatus.COMPLETED))
        service.update_status = AsyncMock(return_value=True)

        result = await approve_run(UUID(RUN), service=service)
        assert result["status"] == "completed"
        assert service.update_status.await_count == 0

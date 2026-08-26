"""
Regression tests for failure-state propagation.

Covers the runtime bug where a Test Design LLM 500 (after retry exhaustion)
was masked by ``'NoneType' object has no attribute 'get'`` and the frontend
browser workspace was left stuck on "Loading...".

Guarantees:
1. Crawler succeeds + Test Design fails -> workflow failed, crawler result preserved.
2. LLM 500 after 3 retries -> STAGE_FAILED emitted, then WORKFLOW_FAILED with the
   real error (never the NoneType exception).
3. WORKFLOW_FAILED is emitted with structured stage/error payload so the frontend
   can leave the loading state.
4. A failed Test Design does NOT trigger an auth retry.
5. The state API returns a structured failure state (no unexpected NoneType).
6. Browser/crawler state survives a downstream (Test Design) failure.
7. The successful-workflow path is unchanged.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.constants import RunStatus
from app.core.event_bus import EventType, get_event_bus
from app.exceptions import LLMProviderError
from app.graph import NodeResult
from app.workflows.trigger_workflow import (
    PlatformWorkflowState,
    _build_pre_review_result,
)


def _build_success_state(run_id: str) -> PlatformWorkflowState:
    state = PlatformWorkflowState(
        run_id=run_id,
        status=RunStatus.PENDING,
        workspace_path="/tmp/ws",
        pages_visited=1,
        total_links=0,
        inventory_summary={"page_count": 1, "form_count": 1, "link_count": 0, "button_count": 3, "input_count": 2},
        test_plan_path="/tmp/ws/contracts/test-plan.json",
        test_plan_summary={"scenario_count": 8, "modules": 2, "summary": "ok"},
    )
    state.node_results["trigger"] = NodeResult(
        node_name="trigger", status="completed", data={"success": True, "run_id": run_id}
    )
    state.node_results["crawler"] = NodeResult(
        node_name="crawler", status="completed",
        data={"crawl_status": "completed", "pages_visited": 1, "total_links": 0},
    )
    state.node_results["inventory_aggregator"] = NodeResult(
        node_name="inventory_aggregator", status="completed",
        data={"page_count": 1, "form_count": 1, "button_count": 3, "input_count": 2},
    )
    state.node_results["test_design"] = NodeResult(
        node_name="test_design", status="completed", data={"scenario_count": 8}
    )
    return state


def _build_failed_state(run_id: str, error: str = "LLM provider error: HTTP 500 after 3 attempts") -> PlatformWorkflowState:
    state = _build_success_state(run_id)
    state.status = RunStatus.FAILED
    state.test_plan_path = None
    state.test_plan_summary = None
    state.node_results["test_design"] = NodeResult(
        node_name="test_design", status="failed", data={}, error=error
    )
    state.mark_failed(f"Test design node failed: {error}")
    return state


class TestPreReviewResultBuilds:
    """execute_platform_workflow's result must reflect the real workflow outcome."""

    @pytest.mark.unit
    def test_failed_test_design_keeps_crawler_and_inventory(self):
        state = _build_failed_state("run-a")
        result = _build_pre_review_result(state, "run-a", state.status)

        assert result["success"] is False
        assert result["status"] == "failed"
        assert "HTTP 500" in result["error"]
        assert result["failed_stage"] == "test_design"

        # Crawler/inventory artifacts produced upstream must survive.
        assert result["pages_visited"] == 1
        assert result["total_links"] == 0
        assert result["inventory_summary"]["page_count"] == 1
        assert result["crawler"]["crawl_status"] == "completed"
        assert result["inventory"]["form_count"] == 1

    @pytest.mark.unit
    def test_failed_result_never_reports_awaiting_review(self):
        state = _build_failed_state("run-b")
        result = _build_pre_review_result(state, "run-b", state.status)
        assert result["status"] != "awaiting_review"
        assert result["success"] is False

    @pytest.mark.unit
    def test_success_path_unchanged(self):
        state = _build_success_state("run-c")
        result = _build_pre_review_result(state, "run-c", state.status)

        assert result["success"] is True
        assert result["status"] == "awaiting_review"
        assert result["errors"] == []
        assert result["test_plan_summary"]["scenario_count"] == 8
        assert result["pages_visited"] == 1
        assert "error" not in result
        assert "failed_stage" not in result

    @pytest.mark.unit
    def test_dict_state_branch_preserves_crawler_on_failure(self):
        state = _build_failed_state("run-d")
        state_dict = {
            "status": state.status,
            "run_id": state.run_id,
            "workspace_path": state.workspace_path,
            "errors": list(state.errors),
            "pages_visited": state.pages_visited,
            "total_links": state.total_links,
            "inventory_path": state.inventory_path,
            "inventory_summary": state.inventory_summary,
            "test_plan_path": state.test_plan_path,
            "test_plan_summary": state.test_plan_summary,
            "node_results": {
                k: {"status": v.status, "data": dict(v.data), "error": v.error}
                for k, v in state.node_results.items()
            },
        }
        result = _build_pre_review_result(state_dict, "run-d", state.status)
        assert result["success"] is False
        assert result["failed_stage"] == "test_design"
        assert "HTTP 500" in result["error"]
        assert result["crawler"]["crawl_status"] == "completed"


class TestLLM500FailurePath:
    """LLM 500 after retry exhaustion must surface as stage + workflow failure."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_test_design_node_emits_stage_failed(self, tmp_path: Path):
        from app.workflows.trigger_workflow import test_design_node

        run_id = str(uuid4())
        bus = get_event_bus()
        bus.clear_replay(run_id)

        state = PlatformWorkflowState(
            run_id=run_id,
            status=RunStatus.RUNNING,
            workspace_path=str(tmp_path),
        )
        failing_agent = AsyncMock()
        failing_agent.execute = AsyncMock(side_effect=LLMProviderError("LLM provider error: HTTP 500 after 3 attempts"))
        state.metadata["test_design_agent"] = failing_agent

        result = await test_design_node(state)

        # Node records the failure without raising.
        assert result.status == RunStatus.FAILED
        assert result.node_results["test_design"].status == "failed"
        assert "HTTP 500" in str(result.errors[-1])

        # STAGE_FAILED carries the real LLM error.
        history = bus.get_history(run_id)
        stage_failed = [e for e in history if e.type == EventType.STAGE_FAILED]
        assert stage_failed
        assert stage_failed[0].data.get("stage") == "test_design"
        assert "HTTP 500" in stage_failed[0].data.get("error", "")

        # Checkpoint records failed_stage so the state API can report it.
        cp = tmp_path / "contracts" / "checkpoint.json"
        assert cp.exists()
        assert json.loads(cp.read_text(encoding="utf-8"))["failed_stage"] == "test_design"

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_run_pre_review_marks_failed_with_real_error(self):
        run_id = str(uuid4())
        bus = get_event_bus()
        bus.clear_replay(run_id)

        result = {
            "success": False,
            "status": "failed",
            "error": "Test design node failed: LLM provider error: HTTP 500 after 3 attempts",
            "errors": ["Test design node failed: LLM provider error: HTTP 500 after 3 attempts"],
            "failed_stage": "test_design",
            "pages_visited": 1,
            "total_links": 0,
            "inventory_summary": {"page_count": 1, "form_count": 1},
            "test_plan_path": None,
            "test_plan_summary": None,
        }

        ts = SimpleNamespace(
            get_run=AsyncMock(return_value=SimpleNamespace(project_id=None)),
            repository=SimpleNamespace(update=AsyncMock()),
            update_status=AsyncMock(),
        )
        execute_mock = AsyncMock(return_value=result)
        login_mock = AsyncMock()
        auth_mock = AsyncMock()

        with (
            patch("app.api.routes.trigger.execute_platform_workflow", execute_mock),
            patch("app.api.routes.trigger._get_ts", AsyncMock(return_value=ts)),
            patch("app.dependencies.get_trigger_agent", MagicMock(return_value=object())),
            patch("app.dependencies.get_crawler_agent", MagicMock(return_value=object())),
            patch("app.services.crawler_service.CrawlerService._perform_login", login_mock),
            patch("app.services.crawler_service.CrawlerService._submit_and_wait_for_auth", auth_mock),
        ):
            from app.api.routes.trigger import _run_pre_review_workflow

            await _run_pre_review_workflow(
                run_id_str=run_id,
                workspace_path="/tmp/ws",
                project_id=None,
                request_data={},
                requested_by="tester",
            )

        # Run is FAILED with the real error — never the NoneType exception.
        ts.update_status.assert_awaited_once()
        call = ts.update_status.await_args
        assert call.args[1] == RunStatus.FAILED
        assert call.kwargs["error"] == result["error"]
        assert "NoneType" not in call.kwargs["error"]

        # WORKFLOW_FAILED carries structured stage/error for the frontend.
        failed_events = [e for e in bus.get_history(run_id) if e.type == EventType.WORKFLOW_FAILED]
        assert failed_events
        assert failed_events[0].data.get("stage") == "test_design"
        assert "HTTP 500" in failed_events[0].data.get("error", "")

        # No re-crawl / no auth retry after a failed Test Design.
        execute_mock.assert_awaited_once()
        login_mock.assert_not_called()
        auth_mock.assert_not_called()

        # No HUMAN_REVIEW_REQUIRED for a failed run.
        review_events = [e for e in bus.get_history(run_id) if e.type == EventType.HUMAN_REVIEW_REQUIRED]
        assert not review_events

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_success_result_emits_human_review_required(self):
        """Guards the success path: None test_plan_summary must not crash."""
        run_id = str(uuid4())
        bus = get_event_bus()
        bus.clear_replay(run_id)

        result = {
            "success": True,
            "status": "awaiting_review",
            "test_plan_path": "/tmp/ws/contracts/test-plan.json",
            "test_plan_summary": None,
        }

        ts = SimpleNamespace(
            get_run=AsyncMock(return_value=SimpleNamespace(project_id=None)),
            repository=SimpleNamespace(update=AsyncMock()),
            update_status=AsyncMock(),
        )

        with (
            patch("app.api.routes.trigger.execute_platform_workflow", AsyncMock(return_value=result)),
            patch("app.api.routes.trigger._get_ts", AsyncMock(return_value=ts)),
            patch("app.dependencies.get_trigger_agent", MagicMock(return_value=object())),
            patch("app.dependencies.get_crawler_agent", MagicMock(return_value=object())),
        ):
            from app.api.routes.trigger import _run_pre_review_workflow

            await _run_pre_review_workflow(
                run_id_str=run_id,
                workspace_path="/tmp/ws",
                project_id=None,
                request_data={},
                requested_by="tester",
            )

        ts.update_status.assert_awaited_once()
        assert ts.update_status.await_args.args[1] == RunStatus.PAUSED

        review_events = [e for e in bus.get_history(run_id) if e.type == EventType.HUMAN_REVIEW_REQUIRED]
        assert review_events
        # Guard against the original NoneType crash: defaults are used.
        assert review_events[0].data.get("scenario_count") == 0
        assert review_events[0].data.get("modules") == 0


class TestStateAPIStructuredFailure:
    """GET /runs/{id}/state must return a structured failure without NoneType."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_failed_run_with_checkpoint_reports_failed_stage(self, tmp_path: Path):
        (tmp_path / "contracts").mkdir(parents=True, exist_ok=True)
        (tmp_path / "contracts" / "crawl-package.json").write_text("{}", encoding="utf-8")
        (tmp_path / "contracts" / "inventory.json").write_text("{}", encoding="utf-8")
        checkpoint = {
            "failed_stage": "test_design",
            "last_error": "LLM provider error: HTTP 500 after 3 attempts",
            "resume_allowed": True,
        }
        (tmp_path / "contracts" / "checkpoint.json").write_text(
            json.dumps(checkpoint), encoding="utf-8"
        )

        entity = SimpleNamespace(
            workspace_path=str(tmp_path),
            status=RunStatus.FAILED,
            current_stage="test_design",
            error="LLM provider error: HTTP 500 after 3 attempts",
        )
        service = SimpleNamespace(get_run=AsyncMock(return_value=entity))

        from app.api.routes.trigger import get_run_state

        resp = await get_run_state(uuid4(), service=service)

        assert resp["status"] == "failed"
        assert resp["failed_stage"] == "test_design"
        assert "HTTP 500" in resp["last_error"]
        assert "crawler" in resp["completed_stages"]
        assert "inventory" in resp["completed_stages"]
        assert resp["resume_allowed"] is True

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_failed_run_without_checkpoint_infers_from_entity(self, tmp_path: Path):
        (tmp_path / "contracts").mkdir(parents=True, exist_ok=True)
        (tmp_path / "contracts" / "crawl-package.json").write_text("{}", encoding="utf-8")

        entity = SimpleNamespace(
            workspace_path=str(tmp_path),
            status=RunStatus.FAILED,
            current_stage="test_design",
            error="Test design node failed: boom",
        )
        service = SimpleNamespace(get_run=AsyncMock(return_value=entity))

        from app.api.routes.trigger import get_run_state

        resp = await get_run_state(uuid4(), service=service)

        assert resp["status"] == "failed"
        assert resp["failed_stage"] == "test_design"
        assert resp["last_error"] == "Test design node failed: boom"


pytestmark = pytest.mark.unit

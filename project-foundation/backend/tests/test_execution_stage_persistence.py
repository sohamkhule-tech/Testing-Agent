"""
Regression tests for the backend Execution-stage persistence fix.

Verifies that starting the Execution node persists the run-entity transition
(status RUNNING, current_stage "execution") so that
GET /api/v1/runs/{id}/state reflects the real workflow stage, while Code
Generation stays completed and the existing STAGE_STARTED(execution) event is
still emitted. No real Playwright/LLM is used.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.constants import RunStatus
from app.core.event_bus import EventType
from app.dependencies import get_trigger_service
from app.graph import NodeResult
from app.main import app
from app.workflows.trigger_workflow import PlatformWorkflowState, execution_node

TEST_RUN = "11111111-2222-3333-4444-555555555555"


class _FakeExecutionService:
    """Deterministic stand-in for ExecutionService (no Playwright)."""

    async def execute_tests(self, **kwargs):
        return {
            "status": "completed",
            "duration_seconds": 0.01,
            "execution_summary": {},
            "metrics": {
                "total_tests": 1,
                "tests_passed": 1,
                "tests_failed": 0,
                "tests_skipped": 0,
                "tests_flaky": 0,
                "pass_rate": 100.0,
            },
            "report_files": {},
            "artifacts_path": str(kwargs.get("project_path") or ""),
            "reports_path": str(kwargs.get("project_path") or ""),
            "execution_logs": [],
        }


def _build_state(tmp_path: Path) -> PlatformWorkflowState:
    return PlatformWorkflowState(
        run_id=TEST_RUN,
        status=RunStatus.RUNNING,
        workspace_path=str(tmp_path),
        generated_project_path=str(tmp_path),
        completed_nodes=["code_generation"],
        node_results={
            "code_generation": NodeResult(
                node_name="code_generation",
                status="completed",
                data={},
            )
        },
        metadata={"execution_service": _FakeExecutionService()},
        agent_state=None,
        execution_plan=None,
    )


@pytest.mark.asyncio
async def test_execution_node_persists_running_execution_stage(tmp_path):
    """The Execution node must persist status=RUNNING, current_stage='execution'
    through the existing TriggerService.update_status path."""
    state = _build_state(tmp_path)
    fake_service = SimpleNamespace()
    fake_service.update_status = AsyncMock(return_value=True)

    with patch("app.dependencies.get_trigger_service", return_value=fake_service):
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()) as _emit:
            result = await execution_node(state)

    fake_service.update_status.assert_awaited_once()
    kwargs = fake_service.update_status.await_args.kwargs
    assert kwargs["status"] == RunStatus.RUNNING
    assert kwargs["stage"] == "execution"
    assert kwargs["run_id"] == UUID(TEST_RUN)
    assert "execution" in result.completed_nodes


@pytest.mark.asyncio
async def test_execution_node_emits_stage_started_execution(tmp_path):
    """STAGE_STARTED {stage:'execution'} must still be emitted (event order preserved)."""
    state = _build_state(tmp_path)
    emitted: list[tuple[str, dict]] = []

    async def _capture(run_id, event_type, data=None):
        emitted.append((event_type, data or {}))

    fake_service = SimpleNamespace()
    fake_service.update_status = AsyncMock(return_value=True)

    with patch("app.dependencies.get_trigger_service", return_value=fake_service):
        with patch("app.workflows.trigger_workflow.emit", new=_capture):
            await execution_node(state)

    starts = [(t, d) for (t, d) in emitted if t == EventType.STAGE_STARTED]
    assert starts, "STAGE_STARTED execution must be emitted"
    assert starts[0][1].get("stage") == "execution"


@pytest.mark.asyncio
async def test_code_generation_not_reverted_by_execution_persistence(tmp_path):
    """Persisting the execution transition must not remove Code Generation from
    the completed set (frontend/backend monotonic compatibility)."""
    state = _build_state(tmp_path)
    fake_service = SimpleNamespace()
    fake_service.update_status = AsyncMock(return_value=True)

    with patch("app.dependencies.get_trigger_service", return_value=fake_service):
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()) as _emit:
            result = await execution_node(state)

    assert "code_generation" in result.completed_nodes
    assert "execution" in result.completed_nodes


def _make_workspace_with_completed_codegen(tmp_path: Path) -> str:
    contracts = tmp_path / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    for name in ("crawl-package.json", "inventory.json", "test-plan.json", "approved-test-plan.json"):
        (contracts / name).write_text("{}", encoding="utf-8")
    meta = tmp_path / "artifacts" / "generated-tests" / "playwright"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "code-generation-metadata.json").write_text("{}", encoding="utf-8")
    return str(tmp_path)


def test_run_state_reflects_execution(tmp_path):
    """GET /api/v1/runs/{id}/state returns current_stage='execution', status='running'
    and keeps code_generation in completed_stages (what frontend reconcile consumes)."""
    ws = _make_workspace_with_completed_codegen(tmp_path)
    entity = SimpleNamespace(
        workspace_path=ws,
        status=RunStatus.RUNNING,
        current_stage="execution",
        error=None,
    )

    class _FakeTriggerService:
        async def get_run(self, run_id):
            return entity

    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTriggerService()
        try:
            resp = client.get(f"/api/v1/runs/{TEST_RUN}/state")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "running"
            assert data["current_stage"] == "execution"
            assert "code_generation" in data["completed_stages"]
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)
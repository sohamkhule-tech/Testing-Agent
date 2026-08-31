import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.constants import RunStatus
from app.dependencies import get_project_service, get_trigger_service
from app.domain.project import ProjectEntity
from app.graph import NodeResult
from app.main import app
from app.workflows.trigger_workflow import PlatformWorkflowState, execution_node


RUN_ID = "aaaaaaaa-1111-2222-3333-bbbbbbbbbbbb"
PROJECT_ID = "cccccccc-dddd-eeee-ffff-000000000001"


class _FakeExecutionService:
    async def execute_tests(self, **kwargs):
        return {
            "status": "completed",
            "duration_seconds": 0.02,
            "execution_summary": {},
            "metrics": {"total_tests": 3, "tests_passed": 2, "tests_failed": 1, "tests_skipped": 0, "tests_flaky": 0, "pass_rate": 66.6},
            "report_files": {},
            "artifacts_path": str(kwargs.get("project_path") or ""),
            "reports_path": str(kwargs.get("project_path") or ""),
            "execution_logs": {},
            "classification": "test_execution_completed_with_failures",
        }


def _build_state(tmp_path: Path, run_id: str = RUN_ID) -> PlatformWorkflowState:
    return PlatformWorkflowState(
        run_id=run_id,
        status=RunStatus.RUNNING,
        workspace_path=str(tmp_path),
        generated_project_path=str(tmp_path),
        completed_nodes=["code_generation"],
        node_results={"code_generation": NodeResult(node_name="code_generation", status="completed", data={})},
        metadata={"execution_service": _FakeExecutionService()},
        agent_state=None,
        execution_plan=None,
    )


def _make_completed_workspace(tmp_path: Path, with_results: bool = True, classification: str | None = None):
    contracts = tmp_path / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    for name in ("crawl-package.json", "inventory.json", "test-plan.json", "approved-test-plan.json"):
        (contracts / name).write_text("{}", encoding="utf-8")
    meta = tmp_path / "artifacts" / "generated-tests" / "playwright"
    meta.mkdir(parents=True, exist_ok=True)
    (meta / "code-generation-metadata.json").write_text("{}", encoding="utf-8")
    if with_results:
        tr = tmp_path / "artifacts" / "generated-tests" / "playwright" / "test-results"
        tr.mkdir(parents=True, exist_ok=True)
        (tr / "results.json").write_text(json.dumps({"stats": {"expected": 2, "unexpected": 1, "skipped": 0, "flaky": 0}, "suites": [{"title": "s"}]}), encoding="utf-8")
        (tr / "junit.xml").write_text("<testsuites/>", encoding="utf-8")
    if classification:
        em = tmp_path / "artifacts" / "generated-tests" / "execution-artifacts"
        em.mkdir(parents=True, exist_ok=True)
        (em / "execution-metadata.json").write_text(json.dumps({"classification": classification, "return_code": -1}), encoding="utf-8")


@pytest.mark.asyncio
async def test_execution_node_durable_completion_persists_completed(tmp_path):
    state = _build_state(tmp_path)
    fake_trigger = SimpleNamespace()
    fake_trigger.update_status = AsyncMock(return_value=True)
    fake_trigger.repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=UUID(PROJECT_ID), updated_at=None, created_at=None)))
    fake_project_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(last_run_status="running", last_run_at=None)), update=AsyncMock(return_value=None))
    fake_ps = SimpleNamespace(project_repo=fake_project_repo)
    with patch("app.dependencies.get_trigger_service", return_value=fake_trigger):
        with patch("app.dependencies.get_project_service", return_value=fake_ps):
            with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
                result = await execution_node(state)
    assert result.status == RunStatus.COMPLETED
    calls = [c.kwargs for c in fake_trigger.update_status.await_args_list]
    assert any(c.get("status") == RunStatus.COMPLETED and c.get("stage") == "completed" for c in calls)
    assert any(c.get("status") == RunStatus.RUNNING and c.get("stage") == "execution" for c in calls)


@pytest.mark.asyncio
async def test_execution_node_still_emits_stage_completed(tmp_path):
    from app.core.event_bus import EventType
    state = _build_state(tmp_path)
    fake_trigger = SimpleNamespace(update_status=AsyncMock(return_value=True), repository=SimpleNamespace(get_by_id=AsyncMock(return_value=None)))
    fake_ps = SimpleNamespace(project_repo=SimpleNamespace(get_by_id=AsyncMock(return_value=None), update=AsyncMock()))
    emitted = []
    async def _cap(run_id, et, data=None):
        emitted.append((et, data or {}))
    with patch("app.dependencies.get_trigger_service", return_value=fake_trigger):
        with patch("app.dependencies.get_project_service", return_value=fake_ps):
            with patch("app.workflows.trigger_workflow.emit", new=_cap):
                await execution_node(state)
    assert any(t == EventType.STAGE_COMPLETED and d.get("stage") == "execution" for t, d in emitted)


def test_state_reconciles_running_to_completed_when_results_exist(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=True)
    entity = SimpleNamespace(workspace_path=str(ws), status=RunStatus.RUNNING, current_stage="execution", error=None, updated_at=None, created_at=None)
    run_id = uuid4()
    updated = SimpleNamespace(workspace_path=str(ws), status=RunStatus.COMPLETED, current_stage="completed", error=None, updated_at=None, created_at=None)
    class _FakeTS:
        async def get_run(self, rid):
            return entity
        async def update_status(self, run_id, status, stage=None, message=None, error=None):
            entity.status = status
            entity.current_stage = stage or entity.current_stage
            return True
        async def get_run_refreshed(self, rid):
            return updated
        repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
        async def get_run_wrapper(self, rid):
            return entity
    # Need to mock get_run to return updated after update_status
    class _FakeTS2:
        def __init__(self):
            self.entity = entity
            self.repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
        async def get_run(self, rid):
            return self.entity
        async def update_status(self, run_id, status, stage=None, message=None, error=None):
            self.entity.status = status
            self.entity.current_stage = stage or self.entity.current_stage
            return True
    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTS2()
        try:
            resp = client.get(f"/api/v1/runs/{run_id}/state")
            assert resp.status_code == 200
            data = resp.json()
            assert "execution" in data["completed_stages"]
            assert "report" in data["completed_stages"]
            assert data["status"] == "completed"
            assert data["current_stage"] == "completed"
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)


def test_state_remains_running_when_no_results(tmp_path):
    ws = tmp_path / "ws2"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=False)
    entity = SimpleNamespace(workspace_path=str(ws), status=RunStatus.RUNNING, current_stage="code_generation", error=None, updated_at=None, created_at=None)
    run_id = uuid4()
    class _FakeTS:
        async def get_run(self, rid):
            return entity
        repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
        async def update_status(self, *a, **k):
            return True
    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTS()
        try:
            resp = client.get(f"/api/v1/runs/{run_id}/state")
            assert resp.status_code == 200
            data = resp.json()
            assert "execution" not in data["completed_stages"]
            assert data["status"] == "running"
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)


def test_state_does_not_promote_genuine_timeout(tmp_path):
    ws = tmp_path / "ws3"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=True, classification="execution_timeout")
    entity = SimpleNamespace(workspace_path=str(ws), status=RunStatus.RUNNING, current_stage="execution", error=None, updated_at=None, created_at=None)
    run_id = uuid4()
    class _FakeTS:
        async def get_run(self, rid):
            return entity
        async def update_status(self, *a, **k):
            entity.status = k.get("status", entity.status)
            return True
        repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTS()
        try:
            resp = client.get(f"/api/v1/runs/{run_id}/state")
            data = resp.json()
            assert data["status"] == "running"
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)


def test_state_does_not_promote_infrastructure_failure(tmp_path):
    ws = tmp_path / "ws4"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=True, classification="infrastructure_failure")
    entity = SimpleNamespace(workspace_path=str(ws), status=RunStatus.RUNNING, current_stage="execution", error=None, updated_at=None, created_at=None)
    run_id = uuid4()
    class _FakeTS:
        async def get_run(self, rid):
            return entity
        async def update_status(self, *a, **k):
            return True
        repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTS()
        try:
            resp = client.get(f"/api/v1/runs/{run_id}/state")
            data = resp.json()
            assert data["status"] == "running"
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)


@pytest.mark.asyncio
async def test_project_enrich_self_heals_running_to_completed(tmp_path):
    ws = tmp_path / "ws_proj"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=True)
    run_id = uuid4()
    project_id = uuid4()
    now = __import__("datetime").datetime.utcnow()
    run_entity = SimpleNamespace(run_id=run_id, project_id=project_id, status=RunStatus.RUNNING, workspace_path=str(ws), created_at=now, updated_at=now, started_at=now, request_id=uuid4(), requested_by="system")
    project_entity = ProjectEntity(id=project_id, name="Test Login", description="Test", application_url="http://example.com", auth_type=None, tags=[], total_runs=1, pending_reviews=0, created_at=now, updated_at=now, last_run_status=RunStatus.RUNNING, last_run_at=now)
    from app.services.project_service import ProjectService
    from app.repositories.project_repository import ProjectRepository
    from app.repositories.run_repository import RunRepository
    # Mock repos
    proj_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=project_entity), update=AsyncMock(return_value=project_entity), list_all=AsyncMock(return_value=[project_entity]))
    run_repo = SimpleNamespace(list_all=AsyncMock(return_value=[run_entity]), get_by_id=AsyncMock(return_value=run_entity))
    svc = ProjectService(project_repository=proj_repo, run_repository=run_repo)
    fake_ts = SimpleNamespace(update_status=AsyncMock(return_value=True), repository=SimpleNamespace(get_by_id=AsyncMock(return_value=run_entity)), get_by_id=AsyncMock(return_value=run_entity))
    # after update, run_repo should return completed
    completed_run = SimpleNamespace(run_id=run_id, project_id=project_id, status=RunStatus.COMPLETED, workspace_path=str(ws), created_at=now, updated_at=now, started_at=now, request_id=run_entity.request_id, requested_by="system")
    async def _get_by_id_after(rid):
        return completed_run
    with patch("app.dependencies.get_trigger_service", return_value=fake_ts):
        # Make run_repo reflect completed after healing
        run_repo.get_by_id = AsyncMock(return_value=completed_run)
        run_repo.list_all = AsyncMock(return_value=[run_entity])
        # First enrich will trigger healing via get_trigger_service
        # We need to patch run_repo.get_by_id to return completed after update
        orig_update = fake_ts.update_status
        async def _update_status(run_id_arg, status, stage=None, message=None, error=None):
            run_entity.status = status
            completed_run.status = status
            return True
        fake_ts.update_status = _update_status
        resp = await svc._enrich_entity_to_response(project_entity)
        assert resp.last_run_status == RunStatus.COMPLETED or str(resp.last_run_status).lower() == "completed"


@pytest.mark.asyncio
async def test_project_enrich_remains_running_when_no_artifacts(tmp_path):
    ws = tmp_path / "ws_proj2"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=False)
    run_id = uuid4()
    project_id = uuid4()
    now = __import__("datetime").datetime.utcnow()
    run_entity = SimpleNamespace(run_id=run_id, project_id=project_id, status=RunStatus.RUNNING, workspace_path=str(ws), created_at=now, updated_at=now, started_at=now, request_id=uuid4(), requested_by="system")
    project_entity = ProjectEntity(id=project_id, name="Test Login", description="Test", application_url="http://example.com", auth_type=None, tags=[], total_runs=1, pending_reviews=0, created_at=now, updated_at=now, last_run_status=RunStatus.RUNNING, last_run_at=now)
    from app.services.project_service import ProjectService
    proj_repo = SimpleNamespace(get_by_id=AsyncMock(return_value=project_entity), update=AsyncMock(return_value=project_entity))
    run_repo = SimpleNamespace(list_all=AsyncMock(return_value=[run_entity]), get_by_id=AsyncMock(return_value=run_entity))
    svc = ProjectService(project_repository=proj_repo, run_repository=run_repo)
    with patch("app.dependencies.get_trigger_service", return_value=SimpleNamespace(update_status=AsyncMock())):
        resp = await svc._enrich_entity_to_response(project_entity)
        assert str(resp.last_run_status).lower() == "running"


def test_state_idempotent_multiple_calls(tmp_path):
    ws = tmp_path / "ws_idem"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=True)
    entity = SimpleNamespace(workspace_path=str(ws), status=RunStatus.RUNNING, current_stage="execution", error=None, updated_at=None, created_at=None)
    run_id = uuid4()
    call_count = {"n": 0}
    class _FakeTS:
        async def get_run(self, rid):
            return entity
        async def update_status(self, run_id, status, stage=None, message=None, error=None):
            call_count["n"] += 1
            entity.status = status
            entity.current_stage = stage or entity.current_stage
            return True
        repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTS()
        try:
            r1 = client.get(f"/api/v1/runs/{run_id}/state")
            r2 = client.get(f"/api/v1/runs/{run_id}/state")
            r3 = client.get(f"/api/v1/runs/{run_id}/state")
            assert r1.json()["status"] == "completed"
            assert r2.json()["status"] == "completed"
            assert r3.json()["status"] == "completed"
            assert call_count["n"] == 1
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)


def test_completed_run_unchanged(tmp_path):
    ws = tmp_path / "ws_done"
    ws.mkdir()
    _make_completed_workspace(ws, with_results=True)
    entity = SimpleNamespace(workspace_path=str(ws), status=RunStatus.COMPLETED, current_stage="completed", error=None, updated_at=None, created_at=None)
    run_id = uuid4()
    class _FakeTS:
        async def get_run(self, rid):
            return entity
        async def update_status(self, *a, **k):
            raise AssertionError("should not update completed run")
        repository = SimpleNamespace(get_by_id=AsyncMock(return_value=SimpleNamespace(project_id=None)))
    with TestClient(app) as client:
        app.dependency_overrides[get_trigger_service] = lambda: _FakeTS()
        try:
            resp = client.get(f"/api/v1/runs/{run_id}/state")
            assert resp.json()["status"] == "completed"
            assert "execution" in resp.json()["completed_stages"]
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)

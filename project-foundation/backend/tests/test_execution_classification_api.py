"""
Regression tests for ``GET /api/v1/runs/{run_id}/execution`` classification.

Ensures:
- The execution API stays authoritative for logical metrics (20 total,
  3 passed / 17 failed → 15% pass rate).
- A legacy ``playwright_timeout`` classification with COMPLETE results is
  healed to ``test_execution_completed_with_failures`` (status completed) —
  it is NOT reported as a timeout.
- A genuine timeout (no executed results) is still reported as
  ``execution_timeout``.
- Infrastructure failures are reported as ``infrastructure_failure``.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_trigger_service
from app.main import app

client = TestClient(app)
RUN_ID = uuid4()


class _FakeTriggerService:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def get_run(self, run_id: UUID):
        return SimpleNamespace(workspace_path=str(self.workspace))


def _use_workspace(workspace: Path) -> None:
    app.dependency_overrides[get_trigger_service] = lambda: _FakeTriggerService(workspace)


def _clear() -> None:
    app.dependency_overrides.pop(get_trigger_service, None)


def _write_results_json(pw_dir: Path, passed: int, failed: int) -> None:
    """Write a Playwright-style JSON reporter output with N specs."""
    tr_dir = pw_dir / "test-results"
    tr_dir.mkdir(parents=True, exist_ok=True)
    specs = []
    for i in range(failed):
        specs.append({
            "title": f"Failed Test {i}",
            "ok": False,
            "tests": [{"projectName": "chromium", "results": [{"status": "failed", "duration": 100}]}],
        })
    for i in range(passed):
        specs.append({
            "title": f"Passed Test {i}",
            "ok": True,
            "tests": [{"projectName": "chromium", "results": [{"status": "passed", "duration": 50}]}],
        })
    data = {
        "suites": [{
            "title": "login-module.spec.ts",
            "file": "login-module.spec.ts",
            "specs": [],
            "suites": [{
                "title": "Login Module",
                "file": "login-module.spec.ts",
                "specs": specs,
                "suites": [],
            }],
        }]
    }
    (tr_dir / "results.json").write_text(json.dumps(data), encoding="utf-8")


def _write_metadata(exec_artifacts: Path, classification: str, return_code: int) -> None:
    ea = exec_artifacts
    ea.mkdir(parents=True, exist_ok=True)
    (ea / "execution-metadata.json").write_text(
        json.dumps({"classification": classification, "return_code": return_code}),
        encoding="utf-8",
    )


@pytest.fixture
def completed_run(tmp_path: Path):
    workspace = tmp_path / "workspace"
    pw = workspace / "artifacts" / "generated-tests" / "playwright"
    ea = workspace / "artifacts" / "generated-tests" / "execution-artifacts"
    pw.mkdir(parents=True)
    _write_results_json(pw, passed=3, failed=17)
    _write_metadata(ea, classification="playwright_timeout", return_code=-1)
    _use_workspace(workspace)
    yield workspace
    _clear()


class TestExecutionClassification:
    def test_completed_run_with_failures_not_classified_as_timeout(self, completed_run: Path):
        """The 20-test run must be reported as completed, NOT a timeout.

        Also verifies the execution API numbers stay authoritative:
        Total 20 / Passed 3 / Failed 17 / Pass rate 15%.
        """
        response = client.get(f"/api/v1/runs/{RUN_ID}/execution")
        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "completed"
        assert data["classification"] == "test_execution_completed_with_failures"

        summary = data["summary"]
        assert summary["total"] == 20
        assert summary["passed"] == 3
        assert summary["failed"] == 17
        assert summary["not_executed"] == 0
        assert summary["pass_rate"] == 15.0
        assert len(data["tests"]) == 20

    def test_legacy_timeout_healed_only_when_results_exist(self, completed_run: Path):
        """The healed classification only applies when executed tests exist."""
        response = client.get(f"/api/v1/runs/{RUN_ID}/execution")
        data = response.json()
        assert data["classification"] == "test_execution_completed_with_failures"

    def test_genuine_timeout_without_results_stays_execution_timeout(self, tmp_path: Path):
        workspace = tmp_path / "timeout-workspace"
        pw = workspace / "artifacts" / "generated-tests" / "playwright"
        ea = workspace / "artifacts" / "generated-tests" / "execution-artifacts"
        pw.mkdir(parents=True)  # NO results.json, NO spec files
        _write_metadata(ea, classification="execution_timeout", return_code=-1)
        _use_workspace(workspace)
        try:
            response = client.get(f"/api/v1/runs/{RUN_ID}/execution")
            data = response.json()
            assert data["status"] == "execution_timeout"
            assert data["classification"] == "execution_timeout"
        finally:
            _clear()

    def test_infrastructure_failure_reported(self, tmp_path: Path):
        workspace = tmp_path / "infra-workspace"
        pw = workspace / "artifacts" / "generated-tests" / "playwright"
        ea = workspace / "artifacts" / "generated-tests" / "execution-artifacts"
        pw.mkdir(parents=True)
        _write_metadata(ea, classification="infrastructure_failure", return_code=-128)
        _use_workspace(workspace)
        try:
            response = client.get(f"/api/v1/runs/{RUN_ID}/execution")
            data = response.json()
            assert data["status"] == "infrastructure_failure"
            assert data["classification"] == "infrastructure_failure"
        finally:
            _clear()

    def test_new_timeout_with_complete_results_healed(self, tmp_path: Path):
        """Even with the NEW taxonomy, timeout + complete results must heal."""
        workspace = tmp_path / "new-tax-workspace"
        pw = workspace / "artifacts" / "generated-tests" / "playwright"
        ea = workspace / "artifacts" / "generated-tests" / "execution-artifacts"
        pw.mkdir(parents=True)
        _write_results_json(pw, passed=1, failed=2)
        _write_metadata(ea, classification="execution_timeout", return_code=-1)
        _use_workspace(workspace)
        try:
            response = client.get(f"/api/v1/runs/{RUN_ID}/execution")
            data = response.json()
            assert data["status"] == "completed"
            assert data["classification"] == "test_execution_completed_with_failures"
            assert data["summary"]["total"] == 3
        finally:
            _clear()

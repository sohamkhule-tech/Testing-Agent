"""
Tests for workflow API endpoints.

Verifies:
- Endpoints are registered
- Missing runs return 404
- Existing runs with workspace data return correct schemas
"""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.dependencies import get_trigger_service
from app.main import app

client = TestClient(app)

NONEXISTENT_RUN_ID = uuid4()


def _allure_report_dir(workspace: Path) -> Path:
    return (
        workspace
        / "artifacts"
        / "generated-tests"
        / "execution-artifacts"
        / "reports"
        / "allure-report"
    )


class _FakeTriggerService:
    def __init__(self, workspace: Path):
        self.workspace = workspace

    async def get_run(self, run_id: UUID):
        return SimpleNamespace(workspace_path=str(self.workspace))


@pytest.fixture
def allure_report_run(tmp_path: Path):
    workspace = tmp_path / "workspace"
    report_dir = _allure_report_dir(workspace)
    report_dir.mkdir(parents=True)
    index = report_dir / "index.html"
    index.write_text("<html><body>Allure Report</body></html>", encoding="utf-8")
    (report_dir / "app.js").write_text("console.log('allure');", encoding="utf-8")
    (report_dir / "data").mkdir()
    (report_dir / "data" / "suites.json").write_text("[]", encoding="utf-8")
    (report_dir / "data" / "test-cases").mkdir()
    (report_dir / "data" / "test-cases" / "case-1.json").write_text(
        '{"uid":"case-1"}',
        encoding="utf-8",
    )

    fake_service = _FakeTriggerService(workspace)
    app.dependency_overrides[get_trigger_service] = lambda: fake_service
    yield workspace
    app.dependency_overrides.pop(get_trigger_service, None)


class TestEndpointRegistration:
    """Verify all new endpoints exist in the OpenAPI schema."""

    def test_workflow_endpoint_registered(self):
        paths = app.openapi()["paths"]
        assert "/api/v1/runs/{run_id}/workflow" in paths
        assert "/api/v1/runs/{run_id}/crawler" in paths
        assert "/api/v1/runs/{run_id}/inventory" in paths
        assert "/api/v1/runs/{run_id}/test-plan" in paths
        assert "/api/v1/runs/{run_id}/review" in paths

    def test_existing_endpoints_still_registered(self):
        paths = app.openapi()["paths"]
        assert "/api/v1/runs" in paths  # POST
        assert "/api/v1/runs/{run_id}" in paths  # GET
        assert "/api/v1/runs/{run_id}/status" in paths

    def test_all_endpoints_have_summaries(self):
        openapi = app.openapi()
        for path, methods in openapi["paths"].items():
            for method, details in methods.items():
                assert "summary" in details, f"{method.upper()} {path} missing summary"
                assert "responses" in details, f"{method.upper()} {path} missing responses"


class TestWorkflowEndpoint:
    """Test ``GET /api/v1/runs/{run_id}/workflow``."""

    def test_nonexistent_run_returns_404(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/workflow")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_workflow_response_structure(self):
        """Verify the response has the expected top-level keys."""
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/workflow")
        assert response.status_code == 404  # Run doesn't exist
        # When a valid run exists, the response should contain:
        # run_id, overall_status, current_stage, progress_percent,
        # stages[], total_stages, completed_stages, pending_stages


class TestCrawlerEndpoint:
    """Test ``GET /api/v1/runs/{run_id}/crawler``."""

    def test_nonexistent_run_returns_404(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/crawler")
        assert response.status_code == 404

    def test_missing_crawler_data_returns_404(self):
        """Without a workspace with crawl data, should 404."""
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/crawler")
        assert response.status_code == 404


class TestInventoryEndpoint:
    """Test ``GET /api/v1/runs/{run_id}/inventory``."""

    def test_nonexistent_run_returns_404(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/inventory")
        assert response.status_code == 404


class TestTestPlanEndpoint:
    """Test ``GET /api/v1/runs/{run_id}/test-plan``."""

    def test_nonexistent_run_returns_404(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/test-plan")
        assert response.status_code == 404


class TestReviewEndpoint:
    """Test ``GET /api/v1/runs/{run_id}/review``."""

    def test_nonexistent_run_returns_404(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/review")
        assert response.status_code == 404


class TestBackwardCompatibility:
    """Verify existing endpoints are unchanged."""

    def test_get_run_still_works(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}")
        assert response.status_code == 404
        # Verify response is RunResponse-like, not new schema
        data = response.json()
        assert "detail" in data  # FastAPI error format

    def test_get_run_status_still_works(self):
        response = client.get(f"/api/v1/runs/{NONEXISTENT_RUN_ID}/status")
        assert response.status_code == 404

    def test_health_still_works(self):
        response = client.get("/health/")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


class TestAllureReportEndpoints:
    """Tests for the Allure report endpoints."""

    def test_allure_report_endpoints_registered(self):
        paths = app.openapi()["paths"]
        assert "/api/v1/runs/{run_id}/report/status" in paths
        assert "/api/v1/runs/{run_id}/report" in paths
        assert "/api/v1/runs/{run_id}/report/{file_path}" in paths
        assert "/api/v1/runs/{run_id}/{asset_dir}/{file_path}" in paths

    def test_report_status_unavailable(self, allure_report_run: Path):
        workspace = allure_report_run
        _allure_report_dir(workspace).rename(workspace / "moved-report")

        response = client.get(f"/api/v1/runs/{uuid4()}/report/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unavailable"
        assert data["report_available"] is False

    def test_report_status_generated(self, allure_report_run: Path):
        response = client.get(f"/api/v1/runs/{uuid4()}/report/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "generated"
        assert data["report_available"] is True
        assert data["report_path"].endswith("allure-report")

    def test_report_status_failed(self, allure_report_run: Path):
        workspace = allure_report_run
        report_dir = _allure_report_dir(workspace)
        (report_dir / "index.html").unlink()

        response = client.get(f"/api/v1/runs/{uuid4()}/report/status")
        assert response.status_code == 200
        assert response.json()["status"] == "failed"

    def test_report_index_served(self, allure_report_run: Path):
        response = client.get(f"/api/v1/runs/{uuid4()}/report")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/html")
        assert "Allure Report" in response.text

    def test_report_asset_served(self, allure_report_run: Path):
        response = client.get(f"/api/v1/runs/{uuid4()}/report/app.js")
        assert response.status_code == 200
        assert response.text == "console.log('allure');"

    def test_report_root_asset_served(self, allure_report_run: Path):
        report_dir = _allure_report_dir(allure_report_run)
        assets_dir = report_dir / "assets"
        assets_dir.mkdir()
        (assets_dir / "index-test.js").write_text("console.log('asset');", encoding="utf-8")

        response = client.get(f"/api/v1/runs/{uuid4()}/assets/index-test.js")
        assert response.status_code == 200
        assert response.text == "console.log('asset');"

    def test_report_root_data_asset_served(self, allure_report_run: Path):
        response = client.get(f"/api/v1/runs/{uuid4()}/data/suites.json")
        assert response.status_code == 200
        assert response.json() == []

    def test_report_root_nested_data_asset_served(self, allure_report_run: Path):
        response = client.get(f"/api/v1/runs/{uuid4()}/data/test-cases/case-1.json")
        assert response.status_code == 200
        assert response.json() == {"uid": "case-1"}

    def test_report_asset_missing_returns_404(self, allure_report_run: Path):
        response = client.get(f"/api/v1/runs/{uuid4()}/report/not-there.js")
        assert response.status_code == 404

    def test_report_asset_traversal_rejected(self, allure_report_run: Path):
        workspace = allure_report_run
        (workspace / "secret.txt").write_text("secret", encoding="utf-8")

        response = client.get(
            f"/api/v1/runs/{uuid4()}/report/%2e%2e%2f..%2f..%2fsecret.txt"
        )
        assert response.status_code == 404

    def test_report_unavailable_returns_404(self, tmp_path: Path):
        workspace = tmp_path / "empty-workspace"
        workspace.mkdir(parents=True)
        fake_service = _FakeTriggerService(workspace)
        app.dependency_overrides[get_trigger_service] = lambda: fake_service
        try:
            response = client.get(f"/api/v1/runs/{uuid4()}/report")
            assert response.status_code == 404
        finally:
            app.dependency_overrides.pop(get_trigger_service, None)

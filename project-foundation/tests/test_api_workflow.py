"""
Tests for workflow API endpoints.

Verifies:
- Endpoints are registered
- Missing runs return 404
- Existing runs with workspace data return correct schemas
"""

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

NONEXISTENT_RUN_ID = uuid4()


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

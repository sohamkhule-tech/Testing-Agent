"""
Integration Tests for Trigger API

Tests for trigger API endpoints.
"""

import pytest
from fastapi.testclient import TestClient
from uuid import UUID


class TestTriggerAPI:
    """Test trigger API endpoints."""

    @pytest.fixture
    def sample_request_data(self):
        """Create sample request data."""
        return {
            "target_application": {
                "base_url": "https://example.com",
                "environment": "staging",
            },
            "requested_by": "test@example.com",
            "execution_mode": {
                "crawl_strategy": "full",
                "test_level": "regression",
            },
            "scope": {
                "max_crawl_depth": 5,
                "max_pages": 50,
            },
        }

    @pytest.mark.integration
    def test_create_run_success(self, test_client: TestClient, sample_request_data):
        """Test creating a new run via API."""
        response = test_client.post("/api/v1/runs", json=sample_request_data)

        assert response.status_code == 202
        data = response.json()

        assert "run_id" in data
        assert "request_id" in data
        assert "status" in data
        assert data["requested_by"] == "test@example.com"

    @pytest.mark.integration
    def test_create_run_validation_error(self, test_client: TestClient):
        """Test creating run with invalid data returns validation error."""
        invalid_data = {}  # Missing required fields

        response = test_client.post("/api/v1/runs", json=invalid_data)

        assert response.status_code == 422  # Validation error

    @pytest.mark.integration
    def test_get_run_success(self, test_client: TestClient, sample_request_data):
        """Test retrieving run details."""
        # Create run first
        create_response = test_client.post("/api/v1/runs", json=sample_request_data)
        assert create_response.status_code == 202
        run_id = create_response.json()["run_id"]

        # Get run details
        response = test_client.get(f"/api/v1/runs/{run_id}")

        assert response.status_code == 200
        data = response.json()

        assert data["run_id"] == run_id
        assert "status" in data
        assert "workspace_path" in data

    @pytest.mark.integration
    def test_get_run_not_found(self, test_client: TestClient):
        """Test getting nonexistent run returns 404."""
        fake_id = "12345678-1234-1234-1234-123456789012"

        response = test_client.get(f"/api/v1/runs/{fake_id}")

        assert response.status_code == 404

    @pytest.mark.integration
    def test_get_run_status_success(self, test_client: TestClient, sample_request_data):
        """Test retrieving run status."""
        # Create run first
        create_response = test_client.post("/api/v1/runs", json=sample_request_data)
        assert create_response.status_code == 202
        run_id = create_response.json()["run_id"]

        # Get run status
        response = test_client.get(f"/api/v1/runs/{run_id}/status")

        assert response.status_code == 200
        data = response.json()

        assert data["run_id"] == run_id
        assert "status" in data
        assert "progress_percent" in data
        assert "current_stage" in data

    @pytest.mark.integration
    def test_get_run_status_not_found(self, test_client: TestClient):
        """Test getting status for nonexistent run returns 404."""
        fake_id = "12345678-1234-1234-1234-123456789012"

        response = test_client.get(f"/api/v1/runs/{fake_id}/status")

        assert response.status_code == 404

    @pytest.mark.integration
    def test_correlation_id_in_response(self, test_client: TestClient, sample_request_data):
        """Test correlation ID is added to responses."""
        response = test_client.post("/api/v1/runs", json=sample_request_data)

        assert "X-Correlation-ID" in response.headers

    @pytest.mark.integration
    def test_create_run_creates_workspace(self, test_client: TestClient, sample_request_data):
        """Test run creation creates workspace structure."""
        response = test_client.post("/api/v1/runs", json=sample_request_data)

        assert response.status_code == 202
        data = response.json()

        workspace_path = data.get("workspace_path")
        assert workspace_path is not None
        assert len(workspace_path) > 0

"""
Integration Tests for API Endpoints

Tests for FastAPI endpoints.
"""

import pytest
from fastapi.testclient import TestClient


class TestHealthEndpoints:
    """Test health check endpoints."""

    @pytest.mark.integration
    def test_health_check(self, test_client: TestClient):
        """Test basic health check."""
        response = test_client.get("/health/")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
        assert "timestamp" in data
        assert "components" in data

    @pytest.mark.integration
    def test_readiness_check(self, test_client: TestClient):
        """Test readiness endpoint."""
        response = test_client.get("/health/ready")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "ready"

    @pytest.mark.integration
    def test_liveness_check(self, test_client: TestClient):
        """Test liveness endpoint."""
        response = test_client.get("/health/live")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "live"

    @pytest.mark.integration
    def test_correlation_id_header(self, test_client: TestClient):
        """Test correlation ID is added to responses."""
        response = test_client.get("/health/")
        assert "X-Correlation-ID" in response.headers

    @pytest.mark.integration
    def test_custom_correlation_id(self, test_client: TestClient):
        """Test custom correlation ID is preserved."""
        custom_id = "test-correlation-123"
        response = test_client.get(
            "/health/", headers={"X-Correlation-ID": custom_id}
        )
        assert response.headers["X-Correlation-ID"] == custom_id

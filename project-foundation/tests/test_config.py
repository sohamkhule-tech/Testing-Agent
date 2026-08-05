"""
Unit Tests for Configuration

Tests for settings and configuration management.
"""

import pytest
from pydantic import ValidationError

from app.config import AppSettings, Settings, get_settings


class TestSettings:
    """Test configuration settings."""

    def test_get_settings_returns_singleton(self):
        """Test that get_settings returns same instance."""
        settings1 = get_settings()
        settings2 = get_settings()
        assert settings1 is settings2

    def test_settings_has_all_sections(self):
        """Test that settings contains all required sections."""
        settings = get_settings()
        assert hasattr(settings, "app")
        assert hasattr(settings, "llm")
        assert hasattr(settings, "storage")
        assert hasattr(settings, "playwright")
        assert hasattr(settings, "logging")
        assert hasattr(settings, "contract")
        assert hasattr(settings, "prompt")

    def test_app_settings_defaults(self):
        """Test app settings have correct defaults."""
        settings = get_settings()
        assert settings.app.app_name == "AI-Testing-Platform"
        assert settings.app.app_version == "1.0.0"
        assert settings.app.environment in ["development", "testing", "staging", "production"]

    def test_storage_settings_paths(self):
        """Test storage paths are configured."""
        settings = get_settings()
        assert settings.storage.storage_base_path
        assert settings.storage.artifacts_path
        assert settings.storage.logs_path

    @pytest.mark.unit
    def test_settings_validation(self):
        """Test settings validation."""
        # Valid settings should not raise
        app_settings = AppSettings(
            app_name="test-app",
            app_version="1.0.0",
            environment="testing",
        )
        assert app_settings.app_name == "test-app"

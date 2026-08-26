"""
Unit tests for PromptParser — user intent extraction from natural-language prompts.
"""

import pytest
from app.services.prompt_builder import PromptParser, AuthContext


@pytest.fixture
def parser():
    return PromptParser()


class TestHeuristicFocus:
    def test_dashboard_only(self, parser):
        intent, auth = parser.parse("test the dashboard page only by entering the credentials")
        assert intent.focus_areas == ["Dashboard"]
        assert len(intent.included_pages) > 0
        assert any("dashboard" in p.lower() for p in intent.included_pages)

    def test_dashboard_only_simple(self, parser):
        intent, auth = parser.parse("test the dashboard page only")
        assert intent.focus_areas == ["Dashboard"]
        assert len(intent.included_pages) > 0

    def test_dashboard_no_only(self, parser):
        intent, auth = parser.parse("test the dashboard page")
        assert intent.focus_areas == ["Dashboard"]
        assert intent.included_pages == []

    def test_dashboard_bare(self, parser):
        intent, auth = parser.parse("test the dashboard")
        assert intent.focus_areas == ["Dashboard"]
        assert intent.included_pages == []

    def test_multiple_focus(self, parser):
        intent, auth = parser.parse("test the reports module and the settings page")
        assert sorted(intent.focus_areas) == ["Reports", "Settings"]

    def test_custom_module_only(self, parser):
        intent, auth = parser.parse("focus on user management module only")
        assert intent.focus_areas == ["User Management"]
        assert len(intent.included_pages) > 0

    def test_login_page_only(self, parser):
        intent, auth = parser.parse("generate tests for login page only")
        assert intent.focus_areas == ["Login"]
        assert len(intent.included_pages) > 0

    def test_profile_page(self, parser):
        intent, auth = parser.parse("test the profile page")
        assert intent.focus_areas == ["Profile"]

    def test_compound_phrase(self, parser):
        intent, auth = parser.parse("enter username and password and test dashboard")
        assert intent.focus_areas == ["Dashboard"]
        assert intent.included_pages == []

    def test_empty_prompt(self, parser):
        intent, auth = parser.parse("")
        assert intent.focus_areas == []
        assert intent.included_pages == []


class TestCredentials:
    def test_explicit_credentials(self, parser):
        intent, auth = parser.parse("username: admin@test.com, password: secret123")
        assert auth.username == "admin@test.com"
        assert auth.password == "secret123"
        assert intent.has_credentials is True

    def test_no_credentials_in_phrase(self, parser):
        intent, auth = parser.parse("test the dashboard page only by entering the credentials")
        assert intent.has_credentials is False
        assert not auth.is_populated()

    def test_redaction(self, parser):
        intent, auth = parser.parse("username: admin@test.com password: p@ssw0rd")
        assert "[CREDENTIAL REDACTED]" in intent.raw_text
        assert "admin@test.com" not in intent.raw_text
        assert "p@ssw0rd" not in intent.raw_text


class TestScopeRestriction:
    def test_only_constraint_sets_includes(self, parser):
        intent, auth = parser.parse("test the dashboard page only")
        assert len(intent.included_pages) > 0

    def test_no_only_no_includes(self, parser):
        intent, auth = parser.parse("test the dashboard page")
        assert intent.included_pages == []

    def test_just_constraint(self, parser):
        intent, auth = parser.parse("just test the settings page")
        assert intent.focus_areas == ["Settings"]
        assert len(intent.included_pages) > 0


class TestSectionHeaders:
    def test_focus_section(self, parser):
        intent, auth = parser.parse("## Focus\nDashboard\nReports\n\n## Exclude\nAdmin")
        assert sorted(intent.focus_areas) == ["Dashboard", "Reports"]
        assert intent.excluded_modules == ["Admin"]

    def test_coverage_section(self, parser):
        intent, auth = parser.parse("## Coverage\nnegative\nsecurity\nboundary")
        assert sorted(intent.coverage_preferences) == ["boundary", "negative", "security"]

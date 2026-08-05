import pytest
from pathlib import Path

from app.execution.failure_analyzer import FailureAnalyzer
from app.schemas.execution import FailureType


@pytest.mark.unit
class TestFailureAnalyzer:
    def test_analyze_failure_locator(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Test login",
            error_message="locator not found for button#submit",
            error_stack=None,
        )

        assert result.failure_type == FailureType.LOCATOR_NOT_FOUND
        assert not result.is_flaky
        assert result.affected_test == "Test login"

    def test_analyze_failure_timeout(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Test timeout",
            error_message="Timeout 30000ms exceeded",
            error_stack="waiting for selector",
        )

        assert result.failure_type == FailureType.TIMEOUT
        assert result.severity == "medium"

    def test_analyze_failure_assertion(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Test assertion",
            error_message="expected 'Hello' to be 'World'",
            error_stack=None,
        )

        assert result.failure_type == FailureType.ASSERTION_FAILED
        assert result.severity == "low"

    def test_analyze_failure_network(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Network test",
            error_message="net::ERR_CONNECTION_REFUSED",
            error_stack=None,
        )

        assert result.failure_type == FailureType.NETWORK_ERROR
        assert result.severity == "medium"

    def test_analyze_failure_auth(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Auth test",
            error_message="401 Unauthorized",
            error_stack=None,
        )

        assert result.failure_type == FailureType.AUTH_FAILED
        assert result.severity == "high"

    def test_analyze_failure_browser_crash(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Crash test",
            error_message="browser crashed unexpectedly",
            error_stack=None,
        )

        assert result.failure_type == FailureType.BROWSER_CRASH
        assert result.severity == "high"

    def test_analyze_failure_navigation(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Nav test",
            error_message="page.navigate: navigation failed",
            error_stack=None,
        )

        assert result.failure_type == FailureType.NAVIGATION_ERROR
        assert result.severity == "medium"

    def test_analyze_failure_dialog(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Dialog test",
            error_message="unexpected dialog appeared",
            error_stack=None,
        )

        assert result.failure_type == FailureType.UNEXPECTED_DIALOG
        assert result.severity == "medium"

    def test_analyze_failure_environment(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Env test",
            error_message="configuration error: missing required option",
            error_stack=None,
        )

        assert result.failure_type == FailureType.ENVIRONMENT_ERROR
        assert result.severity == "high"

    def test_analyze_failure_missing_element(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Missing element",
            error_message="element is not visible",
            error_stack=None,
        )

        assert result.failure_type == FailureType.MISSING_ELEMENT

    def test_analyze_failure_unknown(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Unknown",
            error_message=None,
            error_stack=None,
        )

        assert result.failure_type == FailureType.UNKNOWN
        assert "No error information" in result.root_cause

    def test_analyze_failure_flaky_after_retry(self):
        analyzer = FailureAnalyzer()
        result = analyzer.analyze_failure(
            test_title="Flaky test",
            error_message="Timeout exceeded",
            error_stack=None,
            retry_count=2,
        )

        assert result.is_flaky is True

    def test_analyze_batch(self):
        analyzer = FailureAnalyzer()
        test_results = [
            {"title": "Passing test", "status": "passed"},
            {"title": "Failing test", "status": "failed", "error_message": "Timeout exceeded"},
            {"title": "Another fail", "status": "failed", "error_message": "locator not found"},
        ]

        result = analyzer.analyze_batch(test_results)

        assert result.total_failures == 2
        assert len(result.failure_analyses) == 2
        assert FailureType.TIMEOUT.value in result.failure_type_counts
        assert FailureType.LOCATOR_NOT_FOUND.value in result.failure_type_counts

    def test_generate_failure_report(self, temp_dir: Path):
        analyzer = FailureAnalyzer()
        test_results = [
            {"title": "Test 1", "status": "failed", "error_message": "Timeout"},
        ]
        summary = analyzer.analyze_batch(test_results)

        report_path = analyzer.generate_failure_report(summary, temp_dir)
        assert report_path.exists()
        assert "failure-analysis.json" in str(report_path)

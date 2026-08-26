import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.execution import FailureAnalysis, FailureSummary, FailureType


class FailureAnalyzer(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def analyze_failure(
        self,
        test_title: str,
        error_message: str | None,
        error_stack: str | None,
        retry_count: int = 0,
        test_file: str | None = None,
    ) -> FailureAnalysis:
        if not error_message and not error_stack:
            return FailureAnalysis(
                failure_type=FailureType.UNKNOWN,
                root_cause="No error information available",
                severity="medium",
                recommendation="Review test logs for more information",
                affected_test=test_title,
                affected_page=test_file,
                is_flaky=retry_count > 0,
            )

        error_text = f"{error_message or ''}\n{error_stack or ''}".lower()

        failure_type = self._classify_failure(error_text)
        root_cause = self._extract_root_cause(failure_type, error_message, error_stack)
        severity = self._determine_severity(failure_type, error_text)
        recommendation = self._generate_recommendation(failure_type, error_text)
        is_flaky = self._is_likely_flaky(failure_type, error_text, retry_count)

        analysis = FailureAnalysis(
            failure_type=failure_type,
            root_cause=root_cause,
            severity=severity,
            recommendation=recommendation,
            affected_test=test_title,
            affected_page=test_file,
            is_flaky=is_flaky,
        )

        self.logger.debug(
            "failure_analyzed",
            test=test_title,
            type=failure_type.value,
            severity=severity,
            is_flaky=is_flaky,
        )

        return analysis

    def _classify_failure(self, error_text: str) -> FailureType:
        if "unexpected dialog" in error_text or ("dialog" in error_text and ("alert" in error_text or "confirm" in error_text or "prompt" in error_text)):
            return FailureType.UNEXPECTED_DIALOG

        if "timeout" in error_text or "timed out" in error_text:
            return FailureType.TIMEOUT

        if "locator" in error_text and ("not found" in error_text or "found" in error_text):
            return FailureType.LOCATOR_NOT_FOUND

        if "strict mode violation" in error_text:
            return FailureType.LOCATOR_NOT_FOUND

        if "browser closed" in error_text or "browser disconnected" in error_text or "browser crashed" in error_text:
            return FailureType.BROWSER_CRASH

        if "net::" in error_text or "econnrefused" in error_text or "connection refused" in error_text:
            return FailureType.NETWORK_ERROR

        if "exceeded" in error_text and "waiting for" in error_text:
            return FailureType.TIMEOUT

        if "navigation" in error_text or "page.navigate" in error_text or "page did not" in error_text:
            return FailureType.NAVIGATION_ERROR

        if "401" in error_text or "403" in error_text or "unauthorized" in error_text or "authentication" in error_text:
            return FailureType.AUTH_FAILED

        if "config" in error_text and ("invalid" in error_text or "missing" in error_text):
            return FailureType.ENVIRONMENT_ERROR

        if "expect(" in error_text or ".tobe(" in error_text or ".tohave" in error_text or ".tocontain" in error_text:
            return FailureType.ASSERTION_FAILED

        crash_general = ["page closed", "context closed", "target crashed", "protocol error", "session deleted"]
        if any(p in error_text for p in crash_general):
            return FailureType.BROWSER_CRASH

        locator_general = ["no element matches", "unable to find element", "selector" in error_text and "not found" in error_text]
        if any(p in error_text for p in ["no element matches", "unable to find element"]):
            return FailureType.LOCATOR_NOT_FOUND

        if "selector" in error_text and "not found" in error_text:
            return FailureType.LOCATOR_NOT_FOUND

        assert_words = ["assertion", "expected", "assert"]
        if any(p in error_text for p in assert_words):
            return FailureType.ASSERTION_FAILED

        if "network" in error_text or "fetch failed" in error_text:
            return FailureType.NETWORK_ERROR

        missing = ["not visible", "hidden", "not found in the page"]
        if any(p in error_text for p in missing):
            return FailureType.MISSING_ELEMENT

        return FailureType.UNKNOWN

    def _extract_root_cause(
        self,
        failure_type: FailureType,
        error_message: str | None,
        error_stack: str | None,
    ) -> str:
        if error_message:
            lines = error_message.split("\n")
            first_line = lines[0].strip()
            if len(first_line) > 300:
                first_line = first_line[:300] + "..."
            return first_line

        if error_stack:
            lines = error_stack.split("\n")
            for line in lines:
                line = line.strip()
                if line and not line.startswith("at "):
                    return line[:300]

        return f"{failure_type.value} occurred"

    def _determine_severity(
        self,
        failure_type: FailureType,
        error_text: str,
    ) -> str:
        high_severity = {
            FailureType.BROWSER_CRASH,
            FailureType.ENVIRONMENT_ERROR,
            FailureType.AUTH_FAILED,
        }
        medium_severity = {
            FailureType.NETWORK_ERROR,
            FailureType.NAVIGATION_ERROR,
            FailureType.TIMEOUT,
            FailureType.UNEXPECTED_DIALOG,
        }

        if failure_type in high_severity:
            return "high"
        if failure_type in medium_severity:
            return "medium"
        return "low"

    def _generate_recommendation(
        self,
        failure_type: FailureType,
        error_text: str,
    ) -> str:
        recommendations = {
            FailureType.LOCATOR_NOT_FOUND: (
                "1. Verify element exists on the page\n"
                "2. Check if element is in iframe/shadow DOM\n"
                "3. Wait for element to appear before interacting\n"
                "4. Update locator strategy (prefer data-testid over CSS/XPath)\n"
                "5. Check if page fully loaded before interaction"
            ),
            FailureType.TIMEOUT: (
                "1. Increase timeout value in config or per-test\n"
                "2. Verify page loads completely before assertions\n"
                "3. Check for slow network/API responses\n"
                "4. Add explicit waits for dynamic content\n"
                "5. Consider reducing parallel workers"
            ),
            FailureType.ASSERTION_FAILED: (
                "1. Verify expected values are correct\n"
                "2. Check if element state changed between actions\n"
                "3. Review test data and fixtures\n"
                "4. Update assertion to match actual behavior\n"
                "5. Check for race conditions in async operations"
            ),
            FailureType.NETWORK_ERROR: (
                "1. Verify application is running and accessible\n"
                "2. Check network connectivity and DNS resolution\n"
                "3. Review CORS configuration if cross-origin\n"
                "4. Check API endpoints are accessible\n"
                "5. Verify base URL configuration"
            ),
            FailureType.NAVIGATION_ERROR: (
                "1. Verify the URL is correct\n"
                "2. Check if page requires authentication\n"
                "3. Review navigation timeout settings\n"
                "4. Check for redirect loops\n"
                "5. Verify server is responding correctly"
            ),
            FailureType.AUTH_FAILED: (
                "1. Verify credentials are correct\n"
                "2. Check authentication token/session management\n"
                "3. Review test user permissions\n"
                "4. Check if auth state is properly set up\n"
                "5. Verify storage state file is valid"
            ),
            FailureType.UNEXPECTED_DIALOG: (
                "1. Handle dialog events in test\n"
                "2. Add page.on('dialog') listener\n"
                "3. Decide if dialog should be accepted/dismissed\n"
                "4. Check for unexpected popups/alerts"
            ),
            FailureType.BROWSER_CRASH: (
                "1. Update browser to latest version\n"
                "2. Reduce number of parallel workers\n"
                "3. Increase system memory/resources\n"
                "4. Check for memory leaks in tests\n"
                "5. Disable hardware acceleration"
            ),
            FailureType.ENVIRONMENT_ERROR: (
                "1. Review playwright.config.ts\n"
                "2. Verify Node.js and npm versions\n"
                "3. Check environment variables are set\n"
                "4. Verify project dependencies installed\n"
                "5. Check browser binaries are installed"
            ),
            FailureType.MISSING_ELEMENT: (
                "1. Ensure element exists in DOM\n"
                "2. Check if element is visible (not hidden)\n"
                "3. Wait for element to be visible\n"
                "4. Check if element is in a different frame\n"
                "5. Verify test is on the correct page"
            ),
            FailureType.UNKNOWN: (
                "1. Review complete error message and stack trace\n"
                "2. Check test logs for additional context\n"
                "3. Enable tracing for detailed debugging\n"
                "4. Run test in headed mode to observe behavior\n"
                "5. Check Playwright and browser versions"
            ),
        }

        return recommendations.get(failure_type, "Review error details and test implementation")

    def _is_likely_flaky(
        self,
        failure_type: FailureType,
        error_text: str,
        retry_count: int,
    ) -> bool:
        if retry_count > 0:
            return True

        if failure_type in {FailureType.TIMEOUT, FailureType.NETWORK_ERROR, FailureType.BROWSER_CRASH}:
            return True

        flaky_indicators = [
            "intermittent", "sometimes", "occasionally",
            "race condition", "unstable", "sporadic",
        ]
        return any(indicator in error_text for indicator in flaky_indicators)

    def analyze_batch(
        self,
        test_results: list[dict[str, Any]]
    ) -> FailureSummary:
        analyses = []
        failure_counts: dict[str, int] = {}
        flaky_tests: list[str] = []

        for test in test_results:
            if test.get("status") == "failed":
                analysis = self.analyze_failure(
                    test_title=test.get("title", "Unknown"),
                    error_message=test.get("error_message"),
                    error_stack=test.get("error_stack"),
                    retry_count=test.get("retry_count", 0),
                    test_file=test.get("file"),
                )

                analyses.append({
                    "test_title": test.get("title"),
                    "analysis": analysis.model_dump(),
                })

                failure_type = analysis.failure_type.value
                failure_counts[failure_type] = failure_counts.get(failure_type, 0) + 1

                if analysis.is_flaky:
                    flaky_tests.append(test.get("title"))

        failure_summary = FailureSummary(
            total_failures=len(analyses),
            failure_analyses=analyses,
            failure_type_counts=failure_counts,
            flaky_test_count=len(flaky_tests),
            flaky_tests=flaky_tests,
        )

        self.logger.info(
            "batch_analysis_complete",
            total_failures=failure_summary.total_failures,
            flaky_count=failure_summary.flaky_test_count,
            failure_types=failure_counts,
        )

        return failure_summary

    def generate_failure_report(
        self,
        failure_summary: FailureSummary,
        output_path: Path,
    ) -> Path:
        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_failures": failure_summary.total_failures,
            "failure_type_counts": failure_summary.failure_type_counts,
            "flaky_test_count": failure_summary.flaky_test_count,
            "flaky_tests": failure_summary.flaky_tests,
            "analyses": failure_summary.failure_analyses,
        }

        report_path = output_path / "failure-analysis" / "failure-analysis.json"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")

        self.logger.info("failure_report_generated", path=str(report_path))
        return report_path

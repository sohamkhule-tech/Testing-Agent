import pytest
from app.schemas.execution import (
    ExecutionConfig,
    ExecutionSummary,
    ExecutionMetrics,
    TestResult,
    FailureAnalysis,
    FailureSummary,
    FailureType,
    ArtifactSummary,
    RetryInfo,
    RetrySummary,
    TestStatus,
)


@pytest.mark.unit
class TestExecutionSchemas:
    def test_execution_config_defaults(self):
        config = ExecutionConfig()
        assert config.retries == 0
        assert config.headless is True
        assert config.timeout_ms == 60000
        assert config.screenshot_on_failure is True

    def test_execution_config_custom(self):
        config = ExecutionConfig(
            retries=3,
            headless=False,
            timeout_ms=120000,
            grep="@smoke",
        )
        assert config.retries == 3
        assert config.headless is False
        assert config.timeout_ms == 120000
        assert config.grep == "@smoke"

    def test_test_result_defaults(self):
        tr = TestResult(title="Test 1", status="passed", duration_ms=100)
        assert tr.file is None
        assert tr.error_message is None
        assert tr.is_flaky is False
        assert tr.was_retried is False
        assert tr.screenshots == []

    def test_test_result_full(self):
        tr = TestResult(
            title="Full test",
            file="tests/test.spec.ts",
            status="failed",
            duration_ms=500,
            error_message="Timeout",
            is_flaky=True,
            was_retried=True,
            browser="chromium",
        )
        assert tr.title == "Full test"
        assert tr.status == "failed"
        assert tr.is_flaky is True
        assert tr.browser == "chromium"

    def test_execution_metrics_empty(self):
        metrics = ExecutionMetrics()
        assert metrics.total_tests == 0
        assert metrics.pass_rate == 0.0
        assert metrics.health_score == 0.0

    def test_execution_metrics_calculated(self):
        metrics = ExecutionMetrics(
            total_tests=10,
            tests_passed=8,
            tests_failed=2,
            pass_rate=80.0,
            total_duration_seconds=60.0,
        )
        assert metrics.total_tests == 10
        assert metrics.pass_rate == 80.0
        assert metrics.health_status == "unknown"

    def test_failure_analysis_defaults(self):
        fa = FailureAnalysis(
            failure_type=FailureType.TIMEOUT,
            root_cause="Timeout exceeded",
            affected_test="Test login",
        )
        assert fa.failure_type == FailureType.TIMEOUT
        assert fa.severity == "medium"
        assert fa.recommendation == ""

    def test_failure_summary(self):
        fs = FailureSummary(
            total_failures=2,
            failure_type_counts={"timeout": 1, "assertion": 1},
            flaky_tests=["Flaky test"],
        )
        assert fs.total_failures == 2
        assert len(fs.flaky_tests) == 1

    def test_retry_info(self):
        ri = RetryInfo(
            test_title="Test",
            attempt_number=1,
            max_retries=3,
            status=TestStatus.PASSED,
        )
        assert ri.test_title == "Test"
        assert ri.max_retries == 3

    def test_retry_summary(self):
        rs = RetrySummary(
            total_retries=2,
            tests_retried=2,
            passed_after_retry=1,
            failed_after_retry=1,
            retry_success_rate=50.0,
        )
        assert rs.retry_success_rate == 50.0

    def test_artifact_summary(self):
        as_ = ArtifactSummary(
            screenshots_count=5,
            videos_count=2,
            traces_count=1,
            logs_count=10,
            total_size_bytes=2048,
        )
        assert as_.screenshots_count == 5
        assert as_.total_size_bytes == 2048

    def test_execution_summary(self):
        summary = ExecutionSummary(execution_id="test-001")
        assert summary.execution_id == "test-001"
        assert summary.status.value == "pending"
        assert summary.test_results == []
        assert summary.metrics.total_tests == 0

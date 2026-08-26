import pytest
from pathlib import Path

from app.execution.retry_manager import RetryManager
from app.schemas.execution import ExecutionConfig, TestStatus


@pytest.mark.unit
class TestRetryManager:
    def test_should_not_retry_when_retries_zero(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=0)

        assert mgr.should_retry_test({"status": "failed"}, config, 0) is False

    def test_should_not_retry_passed(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=3)

        assert mgr.should_retry_test({"status": "passed"}, config, 0) is False

    def test_should_not_retry_skipped(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=3)

        assert mgr.should_retry_test({"status": "skipped"}, config, 0) is False

    def test_should_retry_failed(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=3)

        assert mgr.should_retry_test({"status": "failed"}, config, 0) is True

    def test_should_not_retry_exceeded_limit(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=2)

        assert mgr.should_retry_test({"status": "failed"}, config, 2) is False

    def test_should_retry_flaky_only_when_flaky(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=2, retry_flaky_only=True)

        assert mgr.should_retry_test(
            {"status": "failed", "failure_analysis": {"is_flaky": True}},
            config,
            0,
        ) is True

    def test_should_not_retry_flaky_only_when_not_flaky(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=2, retry_flaky_only=True)

        assert mgr.should_retry_test(
            {"status": "failed", "failure_analysis": {"is_flaky": False}},
            config,
            0,
        ) is False

    def test_get_retry_tests_all(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=2)
        results = [
            {"title": "Test 1", "status": "passed"},
            {"title": "Test 2", "status": "failed"},
            {"title": "Test 3", "status": "failed"},
        ]

        retry_tests = mgr.get_retry_tests(results, config)
        assert retry_tests == ["Test 2", "Test 3"]

    def test_get_retry_tests_flaky_only(self):
        mgr = RetryManager()
        config = ExecutionConfig(retries=2, retry_flaky_only=True)
        results = [
            {"title": "Test 1", "status": "failed", "failure_analysis": {"is_flaky": True}},
            {"title": "Test 2", "status": "failed", "failure_analysis": {"is_flaky": False}},
        ]

        retry_tests = mgr.get_retry_tests(results, config)
        assert retry_tests == ["Test 1"]

    def test_create_retry_config(self):
        mgr = RetryManager()
        base = ExecutionConfig(browser=None, retries=3, headless=True)
        retry_config = mgr.create_retry_config(base, retry_attempt=1, test_filter="@smoke")

        assert retry_config.parallel_execution is False
        assert retry_config.max_workers == 1
        assert retry_config.retries == 0
        assert retry_config.screenshot_on_failure is True
        assert retry_config.video_on_failure is True
        assert retry_config.trace_on_failure is True
        assert retry_config.grep == "@smoke"

    def test_track_retry(self):
        mgr = RetryManager()
        info = mgr.track_retry("Test 1", attempt=1, status=TestStatus.PASSED, duration_ms=500)

        assert info.test_title == "Test 1"
        assert info.attempt_number == 1
        assert info.status == TestStatus.PASSED

    def test_merge_retry_results_no_retries(self):
        mgr = RetryManager()
        original = [{"title": "Test 1", "status": "passed"}]
        retry_results: list = []

        merged = mgr.merge_retry_results(original, retry_results)
        assert len(merged) == 1
        assert merged[0]["title"] == "Test 1"

    def test_merge_retry_results_passed_after_retry(self):
        mgr = RetryManager()
        original = [{"title": "Test 1", "status": "failed"}]
        retry_results = [{"title": "Test 1", "status": "passed"}]

        merged = mgr.merge_retry_results(original, retry_results)
        assert merged[0]["was_retried"] is True
        assert merged[0]["is_flaky"] is True
        assert merged[0]["original_status"] == "failed"

    def test_merge_retry_results_failed_after_retry(self):
        mgr = RetryManager()
        original = [{"title": "Test 1", "status": "failed", "error_message": "original error"}]
        retry_results = [{"title": "Test 1", "status": "failed", "error_message": "retry error"}]

        merged = mgr.merge_retry_results(original, retry_results)
        assert merged[0]["was_retried"] is True
        assert merged[0]["retry_failed"] is True
        assert merged[0]["error_message"] == "original error"

    def test_calculate_retry_metrics(self):
        mgr = RetryManager()
        results = [
            {"title": "A", "status": "passed"},
            {"title": "B", "status": "passed", "was_retried": True},
            {"title": "C", "status": "failed", "was_retried": True, "retry_failed": True},
        ]

        metrics = mgr.calculate_retry_metrics(results)
        assert metrics["tests_retried"] == 2
        assert metrics["passed_after_retry"] == 1
        assert metrics["failed_after_retry"] == 1
        assert metrics["retry_success_rate"] == 50.0

    def test_generate_retry_summary(self, temp_dir: Path):
        mgr = RetryManager()
        results = [
            {"title": "A", "status": "passed", "was_retried": True},
            {"title": "B", "status": "failed", "was_retried": True, "retry_failed": True},
        ]

        path = mgr.generate_retry_summary(results, temp_dir)
        assert path.exists()

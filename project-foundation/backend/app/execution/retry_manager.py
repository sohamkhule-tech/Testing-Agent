import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging import LoggerMixin
from app.schemas.execution import ExecutionConfig, RetryInfo, RetrySummary, TestStatus


class RetryManager(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def should_retry_test(
        self,
        test_result: dict[str, Any],
        config: ExecutionConfig,
        retry_attempt: int,
    ) -> bool:
        if config.retries == 0:
            return False

        if retry_attempt >= config.retries:
            return False

        status = test_result.get("status")
        if status in ("passed", "skipped"):
            return False

        if status == "failed":
            if config.retry_flaky_only:
                failure_analysis = test_result.get("failure_analysis", {})
                is_flaky = failure_analysis.get("is_flaky", False)
                return is_flaky
            return True

        return False

    def get_retry_tests(
        self,
        test_results: list[dict[str, Any]],
        config: ExecutionConfig,
    ) -> list[str]:
        retry_tests: list[str] = []

        for test in test_results:
            if test.get("status") == "failed":
                if config.retry_flaky_only:
                    failure_analysis = test.get("failure_analysis", {})
                    if failure_analysis.get("is_flaky", False):
                        retry_tests.append(test.get("title", ""))
                else:
                    retry_tests.append(test.get("title", ""))

        self.logger.info(
            "retry_tests_identified",
            count=len(retry_tests),
            flaky_only=config.retry_flaky_only,
        )

        return retry_tests

    def create_retry_config(
        self,
        base_config: ExecutionConfig,
        retry_attempt: int,
        test_filter: str | None = None,
    ) -> ExecutionConfig:
        retry_config = ExecutionConfig(
            browser=base_config.browser,
            base_url=base_config.base_url,
            headless=base_config.headless,
            parallel_execution=False,
            max_workers=1,
            retries=0,
            timeout_ms=base_config.timeout_ms,
            screenshot_on_failure=True,
            video_on_failure=True,
            trace_on_failure=True,
            is_ci=base_config.is_ci,
            grep=test_filter,
        )

        self.logger.debug(
            "retry_config_created",
            attempt=retry_attempt,
            test_filter=test_filter,
        )

        return retry_config

    def track_retry(
        self,
        test_title: str,
        attempt: int,
        status: TestStatus,
        duration_ms: float = 0.0,
        error: str | None = None,
    ) -> RetryInfo:
        retry_info = RetryInfo(
            test_title=test_title,
            attempt_number=attempt,
            max_retries=attempt,
            status=status,
            duration_ms=duration_ms,
            error=error,
        )

        self.logger.debug(
            "retry_tracked",
            test=test_title,
            attempt=attempt,
            status=status.value,
        )

        return retry_info

    def merge_retry_results(
        self,
        original_results: list[dict[str, Any]],
        retry_results: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        retry_map = {
            test.get("title"): test
            for test in retry_results
        }

        merged_results: list[dict[str, Any]] = []

        for original_test in original_results:
            test_title = original_test.get("title")

            if test_title in retry_map:
                retry_test = retry_map[test_title]

                if retry_test.get("status") == "passed":
                    merged_test = retry_test.copy()
                    merged_test["was_retried"] = True
                    merged_test["original_status"] = original_test.get("status")
                    merged_test["is_flaky"] = True
                    merged_results.append(merged_test)
                else:
                    merged_test = original_test.copy()
                    merged_test["was_retried"] = True
                    merged_test["retry_failed"] = True
                    merged_results.append(merged_test)
            else:
                merged_results.append(original_test)

        self.logger.info(
            "retry_results_merged",
            total=len(merged_results),
            retried=len(retry_map),
            passed_after_retry=sum(
                1 for t in merged_results
                if t.get("was_retried") and t.get("status") == "passed"
            ),
        )

        return merged_results

    def calculate_retry_metrics(
        self,
        test_results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        total_tests = len(test_results)
        retried_tests = sum(1 for t in test_results if t.get("was_retried", False))
        passed_after_retry = sum(
            1 for t in test_results
            if t.get("was_retried") and t.get("status") == "passed"
        )
        failed_after_retry = sum(
            1 for t in test_results
            if t.get("was_retried") and t.get("retry_failed", False)
        )

        return {
            "total_tests": total_tests,
            "tests_retried": retried_tests,
            "passed_after_retry": passed_after_retry,
            "failed_after_retry": failed_after_retry,
            "retry_success_rate": (
                passed_after_retry / retried_tests * 100
                if retried_tests > 0 else 0.0
            ),
        }

    def generate_retry_summary(
        self,
        test_results: list[dict[str, Any]],
        output_path: Path,
    ) -> Path:
        retry_details: list[RetryInfo] = []
        for test in test_results:
            if test.get("was_retried", False):
                retry_details.append(RetryInfo(
                    test_title=test.get("title", ""),
                    attempt_number=1,
                    max_retries=1,
                    status=TestStatus(test.get("status", "skipped")),
                    error=test.get("error_message"),
                ))

        metrics = self.calculate_retry_metrics(test_results)

        summary = RetrySummary(
            total_retries=metrics["tests_retried"],
            tests_retried=metrics["tests_retried"],
            passed_after_retry=metrics["passed_after_retry"],
            failed_after_retry=metrics["failed_after_retry"],
            retry_success_rate=metrics["retry_success_rate"],
            retry_details=retry_details,
        )

        summary_path = output_path / "retry-summary.json"
        summary_path.write_text(json.dumps(summary.model_dump(), indent=2), encoding="utf-8")

        self.logger.info("retry_summary_generated", path=str(summary_path))
        return summary_path

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.event_bus import EventType, emit
from app.core.interfaces import IAgent
from app.exceptions import AgentExecutionError
from app.execution.allure_report_generator import AllureReportGenerator
from app.execution.artifact_collector import ArtifactCollector
from app.execution.environment_manager import EnvironmentManager
from app.execution.failure_analyzer import FailureAnalyzer
from app.execution.metrics_generator import MetricsGenerator
from app.execution.playwright_runner import PlaywrightRunner
from app.execution.report_generator import ReportGenerator
from app.execution.retry_manager import RetryManager
from app.logging import LoggerMixin
from app.schemas.execution import (
    ExecutionConfig,
    ExecutionStatus,
    ExecutionSummary,
    TestResult,
)


class ExecutionAgent(IAgent, LoggerMixin):

    def __init__(self) -> None:
        super().__init__()
        self.env_manager = EnvironmentManager()
        self.playwright_runner = PlaywrightRunner()
        self.failure_analyzer = FailureAnalyzer()
        self.retry_manager = RetryManager()
        self.artifact_collector = ArtifactCollector()
        self.metrics_generator = MetricsGenerator()
        self.report_generator = ReportGenerator()
        self.allure_generator = AllureReportGenerator()

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        start_time = datetime.now(timezone.utc)
        run_id = input_data.get("run_id")
        execution_id = input_data.get("execution_id", run_id)

        self.logger.info("execution_agent_started", run_id=run_id, execution_id=execution_id)

        try:
            project_path = Path(input_data["project_path"]).resolve()
            config = input_data.get("config")
            skip_install = input_data.get("skip_install", False)

            if not config:
                config = ExecutionConfig()
            elif isinstance(config, dict):
                config = ExecutionConfig(**config)

            env_info = await self.env_manager.setup_environment(
                project_path=project_path,
                skip_install=skip_install
            )

            execution_result = await self.playwright_runner.run_tests(
                project_path=project_path,
                config=config
            )

            test_results = self._parse_test_results(execution_result["test_results"])

            test_results = self._analyze_failures(test_results)

            retry_summary = None
            if config.retries > 0 and any(t.get("status") == "failed" for t in test_results):
                retry_results = await self._handle_retries(
                    project_path=project_path,
                    config=config,
                    test_results=test_results
                )
                test_results = retry_results["merged_results"]
                retry_summary = retry_results["retry_summary"]

            artifacts_path = project_path.parent / "execution-artifacts"
            artifact_summary = self.artifact_collector.collect_artifacts(
                project_path=project_path,
                output_path=artifacts_path
            )

            self.artifact_collector.collect_execution_metadata(
                project_path=project_path,
                output_path=artifacts_path,
                execution_result=execution_result,
            )

            self.artifact_collector.create_artifact_index(
                artifacts_path=artifacts_path,
                test_results=test_results,
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            metrics = self.metrics_generator.generate_metrics(
                test_results=test_results,
                total_duration=duration
            )

            self.metrics_generator.generate_metrics_file(metrics, artifacts_path)

            test_result_models = [
                TestResult(
                    title=t["title"],
                    status=t.get("status", "skipped"),
                    duration_ms=t.get("duration_ms", 0),
                    file=t.get("file", ""),
                    line=t.get("line", 0),
                    error_message=t.get("error_message"),
                    error_stack=t.get("error_stack"),
                    retry_count=t.get("retry_count", 0),
                    failure_analysis=t.get("failure_analysis"),
                    is_flaky=t.get("is_flaky", False),
                    was_retried=t.get("was_retried", False),
                    retry_failed=t.get("retry_failed", False),
                    browser=t.get("browser"),
                )
                for t in test_results
            ]

            failure_batch = self.failure_analyzer.analyze_batch(test_results)

            self.failure_analyzer.generate_failure_report(failure_batch, artifacts_path)

            # Determine execution status based on actual execution results
            # CRITICAL: Infrastructure failures must mark the execution as FAILED,
            # not COMPLETED. Status is driven by the classification (root cause),
            # never by a bare return code: a wall-clock kill that still produced
            # complete results is a completed-with-failures run, not a timeout.
            classification = execution_result.get("classification", "test_execution_completed_with_failures")

            if classification in ("infrastructure_failure", "execution_timeout", "command_failure"):
                # Playwright failed to start/complete or was killed with no usable results
                execution_summary_status = ExecutionStatus.FAILED
            elif metrics.total_tests == 0:
                # No tests were executed (even if return code was 0)
                execution_summary_status = ExecutionStatus.FAILED
            elif metrics.tests_failed == 0:
                # Tests ran and all passed
                execution_summary_status = ExecutionStatus.COMPLETED
            else:
                # Tests ran but some failed
                execution_summary_status = ExecutionStatus.COMPLETED_WITH_FAILURES

            execution_summary = ExecutionSummary(
                execution_id=execution_id,
                status=execution_summary_status,
                start_time=start_time.isoformat(),
                end_time=datetime.now(timezone.utc).isoformat(),
                duration_seconds=duration,
                config=config,
                test_results=test_result_models,
                metrics=metrics,
                failure_summary=failure_batch,
                retry_summary=retry_summary,
                artifacts=artifact_summary,
                environment=env_info,
            )

            reports_path = artifacts_path / "reports"
            report_paths = self.report_generator.generate_reports(
                execution_summary=execution_summary,
                output_path=reports_path
            )

            execution_summary.report_paths = {
                k: str(v) for k, v in report_paths.items()
            }

            allure_results_dir = Path(project_path) / "allure-results"
            allure_report_path = reports_path / "allure-report"
            allure_environment = {
                "Base URL": config.base_url or "",
                "Browser": config.browser.value if config.browser else "all",
                "Node Version": env_info.get("node_version", ""),
                "npm Version": env_info.get("npm_version", ""),
            }
            event_run_id = str(run_id or execution_id)
            await emit(event_run_id, EventType.REPORT_GENERATION_STARTED, {
                "report_type": "allure",
                "results_path": str(allure_results_dir),
            })
            fallback_tests = test_results
            if not fallback_tests:
                try:
                    from app.api.routes.workflow import _parse_test_results_from_folders
                    test_results_dir = Path(project_path) / "test-results"
                    fallback_tests = _parse_test_results_from_folders(test_results_dir, Path(project_path))
                except Exception:
                    pass

            allure_report = self.allure_generator.generate(
                results_dir=allure_results_dir,
                output_path=allure_report_path,
                project_path=Path(project_path),
                environment=allure_environment,
                fallback_test_results=fallback_tests,
            )
            if allure_report["status"] == "generated":
                report_paths["allure-report"] = str(allure_report_path)
                await emit(event_run_id, EventType.REPORT_GENERATION_COMPLETED, {
                    "report_type": "allure",
                    "report_path": str(allure_report_path),
                })
                await emit(event_run_id, EventType.REPORT_AVAILABLE, {
                    "report_type": "allure",
                    "report_path": str(allure_report_path),
                })
            else:
                await emit(event_run_id, EventType.REPORT_GENERATION_FAILED, {
                    "report_type": "allure",
                    "status": allure_report["status"],
                    "error": allure_report.get("error"),
                })

            await self.env_manager.cleanup_environment(project_path)

            result: dict[str, Any] = {
                "run_id": run_id,
                "execution_id": execution_id,
                "status": execution_summary_status.value,
                "execution_summary": execution_summary.model_dump(),
                "project_path": str(project_path),
                "artifacts_path": str(artifacts_path),
                "reports_path": str(reports_path),
                "report_files": {k: str(v) for k, v in report_paths.items()},
                "duration_seconds": duration,
                "metrics": metrics.model_dump(),
                # Distinguish test failures vs process timeout vs command/env
                # failures so the UI can show a meaningful reason.
                "classification": execution_result.get(
                    "classification", "test_execution_completed_with_failures"
                ),
                "failure_summary": failure_batch.model_dump() if failure_batch else None,
                "retry_summary": retry_summary.model_dump() if retry_summary else None,
                "playwright_exit_code": execution_result.get("return_code"),
                "allure_report": allure_report,
                "execution_logs": {
                    "stdout": execution_result.get("stdout", ""),
                    "stderr": execution_result.get("stderr", ""),
                },
            }

            self.logger.info(
                "execution_agent_completed",
                run_id=run_id,
                status=execution_summary_status.value,
                duration=duration,
                tests_passed=metrics.tests_passed,
                tests_failed=metrics.tests_failed,
            )

            return result

        except Exception as e:
            self.logger.error("execution_agent_failed", run_id=run_id, error=str(e))
            raise AgentExecutionError(f"Execution failed: {str(e)}") from e

    def _parse_test_results(
        self,
        playwright_results: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return playwright_results.get("tests", [])

    def _analyze_failures(
        self,
        test_results: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        for test in test_results:
            if test.get("status") == "failed":
                analysis = self.failure_analyzer.analyze_failure(
                    test_title=test.get("title", "Unknown"),
                    error_message=test.get("error_message"),
                    error_stack=test.get("error_stack"),
                    retry_count=test.get("retry_count", 0),
                    test_file=test.get("file"),
                )
                test["failure_analysis"] = analysis.model_dump()
                test["is_flaky"] = analysis.is_flaky
        return test_results

    async def _handle_retries(
        self,
        project_path: Path,
        config: ExecutionConfig,
        test_results: list[dict[str, Any]],
    ) -> dict:
        retry_tests = self.retry_manager.get_retry_tests(test_results, config)

        if not retry_tests:
            self.logger.info("no_tests_to_retry")
            return {"merged_results": test_results, "retry_summary": None}

        self.logger.info("retrying_tests", count=len(retry_tests))

        retry_config = self.retry_manager.create_retry_config(
            base_config=config,
            retry_attempt=1,
            test_filter="|".join(retry_tests),
        )

        retry_execution = await self.playwright_runner.run_tests(
            project_path=project_path,
            config=retry_config
        )

        retry_results = self._parse_test_results(retry_execution["test_results"])

        merged_results = self.retry_manager.merge_retry_results(
            original_results=test_results,
            retry_results=retry_results
        )

        merged_results = self._analyze_failures(merged_results)

        retry_artifacts_path = project_path.parent / "execution-artifacts-retry"
        retry_artifacts_path.mkdir(parents=True, exist_ok=True)
        retry_summary_path = self.retry_manager.generate_retry_summary(
            merged_results, retry_artifacts_path
        )

        retry_metrics = self.retry_manager.calculate_retry_metrics(merged_results)
        from app.schemas.execution import RetrySummary, RetryInfo, TestStatus
        retry_info_list = []
        for t in merged_results:
            if t.get("was_retried", False):
                retry_info_list.append(
                    RetryInfo(
                        test_title=t.get("title", ""),
                        attempt_number=1,
                        max_retries=config.retries,
                        status=TestStatus(t.get("status", "skipped")),
                        error=t.get("error_message"),
                    )
                )
        rs = RetrySummary(
            total_retries=retry_metrics["tests_retried"],
            tests_retried=retry_metrics["tests_retried"],
            passed_after_retry=retry_metrics["passed_after_retry"],
            failed_after_retry=retry_metrics["failed_after_retry"],
            retry_success_rate=retry_metrics["retry_success_rate"],
            retry_details=retry_info_list,
        )

        return {"merged_results": merged_results, "retry_summary": rs}

    def get_system_prompt(self) -> str:
        return "Execution Agent - Orchestrates test execution pipeline"

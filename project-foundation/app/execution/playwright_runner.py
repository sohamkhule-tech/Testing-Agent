import json
import os as os_module
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.exceptions import ExecutionError
from app.logging import LoggerMixin
from app.schemas.execution import BrowserType, ExecutionConfig


class PlaywrightRunner(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    async def run_tests(
        self,
        project_path: Path,
        config: ExecutionConfig
    ) -> dict[str, Any]:
        start_time = datetime.now(timezone.utc)

        self.logger.info(
            "starting_playwright_execution",
            project_path=str(project_path),
            browser=config.browser.value if config.browser else "all"
        )

        try:
            command = self._build_command(config)

            env = self._prepare_environment(project_path, config)

            timeout = config.timeout_ms // 1000 + 300 if config.timeout_ms else 1800

            result = await self._execute_command(
                command=command,
                cwd=project_path,
                env=env,
                timeout=timeout
            )

            test_results = await self._parse_results(project_path)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            execution_result = {
                "start_time": start_time.isoformat(),
                "end_time": datetime.now(timezone.utc).isoformat(),
                "duration_seconds": duration,
                "command": " ".join(command) if isinstance(command, list) else command,
                "return_code": result["return_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "test_results": test_results,
                "browser": config.browser.value if config.browser else "all",
                "results_file": str(project_path / "test-results" / "results.json"),
                "playwright_report_path": str(project_path / "playwright-report"),
            }

            self.logger.info(
                "playwright_execution_complete",
                duration=duration,
                return_code=result["return_code"],
                tests_run=len(test_results.get("tests", [])),
            )

            return execution_result

        except Exception as e:
            self.logger.error("playwright_execution_failed", error=str(e))
            raise ExecutionError(f"Test execution failed: {str(e)}") from e

    def _build_command(self, config: ExecutionConfig) -> list[str]:
        command = ["npx", "playwright", "test"]

        if config.browser and config.browser != BrowserType.ALL:
            command.extend(["--project", config.browser.value])

        if config.parallel_execution and config.max_workers:
            command.extend(["--workers", str(config.max_workers)])
        elif not config.parallel_execution:
            command.extend(["--workers", "1"])

        if config.retries > 0:
            command.extend(["--retries", str(config.retries)])

        if not config.headless:
            command.append("--headed")

        command.extend(["--reporter", "html,junit"])

        # JSON reporter output is captured via PLAYWRIGHT_JSON_OUTPUT_NAME env var
        # (set in _prepare_environment) so results are always written to disk

        if config.grep:
            command.extend(["--grep", config.grep])

        if config.test_file:
            command.append(config.test_file)

        if config.is_ci:
            command.append("--forbid-only")

        command.extend(["--output", "test-results"])

        self.logger.debug("built_command", command=" ".join(command))
        return command

    def _prepare_environment(
        self,
        project_path: Path,
        config: ExecutionConfig
    ) -> dict[str, str]:
        env = os_module.environ.copy()

        if config.base_url:
            env["BASE_URL"] = config.base_url

        env["HEADLESS"] = "true" if config.headless else "false"
        env["CI"] = "true" if config.is_ci else "false"
        env["PLAYWRIGHT_HTML_REPORT"] = str(project_path / "playwright-report")
        env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(project_path / "test-results" / "results.json")
        env["PLAYWRIGHT_JUNIT_OUTPUT_NAME"] = str(project_path / "test-results" / "junit.xml")

        if config.screenshot_on_failure:
            env["SCREENSHOT_ON_FAILURE"] = "true"

        if config.video_on_failure:
            env["VIDEO_ON_FAILURE"] = "true"

        if config.trace_on_failure:
            env["TRACE_ON_FAILURE"] = "true"

        return env

    async def _execute_command(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int
    ) -> dict[str, Any]:
        try:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                shell=True,
            )

            return {
                "return_code": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired as e:
            self.logger.error("execution_timeout", timeout=timeout)
            return {
                "return_code": -1,
                "stdout": e.stdout.decode() if e.stdout else "",
                "stderr": f"Execution timed out after {timeout} seconds",
            }

        except Exception as e:
            self.logger.error("execution_error", error=str(e))
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
            }

    async def _parse_results(self, project_path: Path) -> dict[str, Any]:
        results_file = project_path / "test-results" / "results.json"

        if not results_file.exists():
            self.logger.warning("results_file_not_found", path=str(results_file))
            return {
                "tests": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
            }

        try:
            with open(results_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            tests = []
            summary = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "flaky": 0}

            for suite in data.get("suites", []):
                for spec in suite.get("specs", []):
                    for test in spec.get("tests", []):
                        test_info = self._parse_test_result(test)
                        tests.append(test_info)
                        summary["total"] += 1
                        status = test_info["status"]
                        if status == "passed":
                            summary["passed"] += 1
                        elif status == "failed":
                            summary["failed"] += 1
                        elif status == "skipped":
                            summary["skipped"] += 1

            return {"tests": tests, "summary": summary, "raw_data": data}

        except Exception as e:
            self.logger.error("failed_to_parse_results", error=str(e))
            return {
                "tests": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "parse_error": str(e),
            }

    def _parse_test_result(self, test_data: dict[str, Any]) -> dict[str, Any]:
        results = test_data.get("results", [])
        status = "skipped"

        if results:
            last_result = results[-1]
            status_map = {
                "passed": "passed",
                "failed": "failed",
                "timedOut": "failed",
                "skipped": "skipped",
                "interrupted": "failed",
            }
            status = status_map.get(last_result.get("status", "skipped"), "skipped")

        error_message = None
        error_stack = None

        if status == "failed" and results:
            last_result = results[-1]
            error = last_result.get("error", {})
            error_message = error.get("message")
            error_stack = error.get("stack")

        return {
            "title": test_data.get("title", "Unknown"),
            "file": test_data.get("file", ""),
            "line": test_data.get("line", 0),
            "status": status,
            "duration_ms": sum(r.get("duration", 0) for r in results),
            "retry_count": max(0, len(results) - 1),
            "error_message": error_message,
            "error_stack": error_stack,
            "annotations": test_data.get("annotations", []),
            "browser": test_data.get("projectName"),
        }

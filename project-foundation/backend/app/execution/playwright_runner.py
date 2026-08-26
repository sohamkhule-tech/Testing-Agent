import asyncio
import json
import os
import shutil
import signal
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.exceptions import ExecutionError
from app.logging import LoggerMixin
from app.schemas.execution import BrowserType, ExecutionConfig


def _coerce_output(value: Any) -> str:
    """Normalize captured subprocess/timeout output to text.

    ``subprocess.run(..., text=True, encoding=...)`` yields ``str`` output;
    without text mode the captured value is ``bytes`` (and may be ``None`` when
    nothing was captured). Normalizing here prevents
    ``AttributeError: 'str' object has no attribute 'decode'`` when handling a
    ``TimeoutExpired`` on a text-mode subprocess (observed on Windows).
    """
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


class PlaywrightRunner(LoggerMixin):

    # Classification values returned on every execution result so callers/UI
    # can distinguish root cause instead of a generic "Test Execution Failed".
    CLASSIFICATION_PASSED = "passed"
    CLASSIFICATION_TEST_FAILURES = "test_failures"
    CLASSIFICATION_PLAYWRIGHT_TIMEOUT = "playwright_timeout"
    CLASSIFICATION_COMMAND_FAILURE = "command_failure"
    CLASSIFICATION_INFRASTRUCTURE_ERROR = "infrastructure_error"

    def __init__(self) -> None:
        super().__init__()

    async def run_tests(
        self,
        project_path: Path,
        config: ExecutionConfig
    ) -> dict[str, Any]:
        start_time = datetime.now(UTC)

        self.logger.info(
            "starting_playwright_execution",
            project_path=str(project_path),
            browser=config.browser.value if config.browser else "all"
        )

        try:
            command = self._build_command(config)

            env = self._prepare_environment(project_path, config)

            timeout = config.timeout_ms // 1000 + 300 if config.timeout_ms else 1800

            # Clean test-results before run to prevent Windows Node fs.rmdirSync EPERM lock errors
            test_results_dir = project_path / "test-results"
            if test_results_dir.exists():
                import shutil as _shutil
                _shutil.rmtree(test_results_dir, ignore_errors=True)

            result = await self._execute_command(
                command=command,
                cwd=project_path,
                env=env,
                timeout=timeout
            )

            test_results = await self._parse_results(project_path)

            if config.grep and not test_results.get("tests"):
                self.logger.warning("grep_returned_no_tests_retrying_unfiltered", grep=config.grep)
                fallback_config = config.model_copy(update={"grep": None})
                fallback_command = self._build_command(fallback_config)
                result = await self._execute_command(
                    command=fallback_command,
                    cwd=project_path,
                    env=env,
                    timeout=timeout,
                )
                test_results = await self._parse_results(project_path)
                if not test_results.get("tests"):
                    # The scoped + unfiltered runs both produced no parsed
                    # results file. Track this explicitly for classification.
                    result = dict(result or {})
                    result.setdefault("classification", self.CLASSIFICATION_TEST_FAILURES)

            duration = (datetime.now(UTC) - start_time).total_seconds()

            execution_result = {
                "start_time": start_time.isoformat(),
                "end_time": datetime.now(UTC).isoformat(),
                "duration_seconds": duration,
                "command": " ".join(command) if isinstance(command, list) else command,
                "return_code": result["return_code"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
                "classification": result.get("classification", self._classify_result(result["return_code"], result["stderr"], test_results)),
                "test_results": test_results,
                "browser": config.browser.value if config.browser else "all",
                "results_file": str(project_path / "test-results" / "results.json"),
                "playwright_report_path": str(project_path / "playwright-report"),
                "allure_results_path": str(project_path / "allure-results"),
            }

            self.logger.info(
                "playwright_execution_complete",
                duration=duration,
                return_code=result["return_code"],
                tests_run=len(test_results.get("tests", [])),
                classification=execution_result["classification"],
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

        # Reporters are configured authoritatively in playwright.config.ts
        # (html + json + junit + allure-playwright). Do NOT pass --reporter
        # here: the CLI flag overrides config-level reporters entirely and
        # would suppress Allure result generation.
        # JSON reporter output is captured via PLAYWRIGHT_JSON_OUTPUT_NAME env var
        # (set in _prepare_environment) so results are always written to disk

        if config.grep:
            command.extend(["--grep", config.grep])

        if config.test_file:
            command.append(config.test_file)

        if config.is_ci:
            command.append("--forbid-only")

        self.logger.debug("built_command", command=" ".join(command))
        return command

    def _prepare_environment(
        self,
        project_path: Path,
        config: ExecutionConfig
    ) -> dict[str, str]:
        env = os.environ.copy()

        if config.base_url:
            env["BASE_URL"] = config.base_url

        env["HEADLESS"] = "true" if config.headless else "false"
        env["CI"] = "true" if config.is_ci else "false"
        env["PLAYWRIGHT_HTML_REPORT"] = str(project_path / "playwright-report")
        env["PLAYWRIGHT_JSON_OUTPUT_NAME"] = str(project_path / "test-results" / "results.json")
        env["PLAYWRIGHT_JUNIT_OUTPUT_NAME"] = str(project_path / "test-results" / "junit.xml")
        env["ALLURE_RESULTS_DIR"] = str(project_path / "allure-results")

        if config.screenshot_on_failure:
            env["SCREENSHOT_ON_FAILURE"] = "true"

        if config.video_on_failure:
            env["VIDEO_ON_FAILURE"] = "true"

        if config.trace_on_failure:
            env["TRACE_ON_FAILURE"] = "true"

        return env

    @staticmethod
    def _resolve_command(command: list[str], cwd: Path) -> list[str]:
        """Resolve ``npx playwright ...`` into the project's local Playwright CLI.

        On Windows ``npx`` is a ``.cmd`` shim that cannot be run with
        ``shell=False`` (``CreateProcess`` cannot execute ``.cmd`` files).
        Running the project's installed Playwright CLI directly via ``node`` is
        cross-platform, avoids the shell entirely, and guarantees that
        ``--grep``-style regex arguments (e.g. ``login|sign_in``) are passed to
        Playwright as a SINGLE argument instead of being interpreted as shell
        pipelines by ``cmd.exe``.

        Args:
            command: The command list produced by ``_build_command``.
            cwd: The generated Playwright project root.

        Returns:
            A shell-safe command list that executes Playwright without a shell.

        Raises:
            ExecutionError: When the local Playwright CLI cannot be located.
        """
        if len(command) >= 2 and command[0] == "npx" and command[1] == "playwright":
            for rel_path in (
                "node_modules/@playwright/test/cli.js",
                "node_modules/playwright/cli.js",
            ):
                candidate = Path(cwd) / rel_path
                if candidate.exists():
                    node = shutil.which("node") or "node"
                    return [node, str(candidate), *command[2:]]
            raise ExecutionError(
                "Local Playwright CLI not found in generated project. "
                "Run `npm install` before executing tests."
            )
        return list(command)

    @staticmethod
    def _classify_result(return_code: int, stderr: str, test_results: dict[str, Any]) -> str:
        """Map an execution outcome into a stable classification.

        Distinguishes test failures from process timeouts, command failures,
        and environment/infrastructure failures so callers and the UI can show
        a meaningful reason instead of a generic failure.
        """
        if return_code == -1:
            return PlaywrightRunner.CLASSIFICATION_PLAYWRIGHT_TIMEOUT
        if return_code == -127:
            return PlaywrightRunner.CLASSIFICATION_COMMAND_FAILURE
        if return_code == -128:
            return PlaywrightRunner.CLASSIFICATION_INFRASTRUCTURE_ERROR
        if return_code == 0:
            return PlaywrightRunner.CLASSIFICATION_PASSED
        return PlaywrightRunner.CLASSIFICATION_TEST_FAILURES

    @staticmethod
    async def _terminate_process_tree(proc: asyncio.subprocess.Process) -> None:
        """Kill the whole Playwright/node/browser process tree.

        On Windows an orphaned ``cmd.exe`` -> ``node`` -> browser tree is the
        reason ``subprocess.run(..., timeout=...)`` can outlive the configured
        timeout: the shell is killed but grandchildren keep the stdio pipes
        open. ``taskkill /T /F`` targets the tree; on POSIX we use the process
        group created via ``start_new_session=True``.
        """
        if proc is None or proc.returncode is not None:
            return
        try:
            pid = proc.pid
        except Exception:
            pid = None
        if pid is None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/pid", str(pid), "/T", "/F"],
                    capture_output=True,
                    timeout=10,
                )
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        else:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass

    async def _execute_command(
        self,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        timeout: int
    ) -> dict[str, Any]:
        """Execute Playwright without a shell, with deterministic timeout.

        Arguments are passed as a list to ``asyncio.create_subprocess_exec`` so
        shell metacharacters in ``--grep`` regexes can never be interpreted by
        ``cmd.exe``/```sh``. On timeout the whole process tree is terminated
        and a deterministic ``return_code == -1`` result is returned, preserving
        any partial stdout/stderr captured so far.
        """
        try:
            exec_command = self._resolve_command(command, cwd)
        except ExecutionError as e:
            return {
                "return_code": -127,
                "stdout": "",
                "stderr": str(e),
                "classification": self.CLASSIFICATION_COMMAND_FAILURE,
            }

        creationflags = 0
        start_new_session = False
        if os.name == "nt":
            creationflags = (
                getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                | getattr(subprocess, "CREATE_NO_WINDOW", 0)
            )
        else:
            start_new_session = True

        try:
            proc = await asyncio.create_subprocess_exec(
                *exec_command,
                cwd=str(cwd),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
                start_new_session=start_new_session,
            )
        except FileNotFoundError as e:
            return {
                "return_code": -127,
                "stdout": "",
                "stderr": f"Command not found: {exec_command[0]} ({e})",
                "classification": self.CLASSIFICATION_COMMAND_FAILURE,
            }
        except Exception as e:
            return {
                "return_code": -128,
                "stdout": "",
                "stderr": f"Failed to start Playwright process: {e}",
                "classification": self.CLASSIFICATION_INFRASTRUCTURE_ERROR,
            }

        try:
            stdout_raw, stderr_raw = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
            return {
                "return_code": proc.returncode if proc.returncode is not None else -128,
                "stdout": _coerce_output(stdout_raw),
                "stderr": _coerce_output(stderr_raw),
                "classification": self.CLASSIFICATION_PASSED if proc.returncode == 0 else self.CLASSIFICATION_TEST_FAILURES,
            }
        except TimeoutError:
            self.logger.error("execution_timeout", timeout=timeout)
            await self._terminate_process_tree(proc)
            stdout_raw, stderr_raw = b"", b""
            try:
                stdout_raw, stderr_raw = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=10,
                )
            except Exception:
                pass
            return {
                "return_code": -1,
                "stdout": _coerce_output(stdout_raw),
                "stderr": f"Execution timed out after {timeout} seconds",
                "classification": self.CLASSIFICATION_PLAYWRIGHT_TIMEOUT,
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
            with open(results_file, encoding="utf-8") as f:
                data = json.load(f)

            tests = []
            summary = {"total": 0, "passed": 0, "failed": 0, "skipped": 0, "flaky": 0}

            def walk_suites(suites: list[dict[str, Any]]) -> None:
                # Playwright's JSON reporter nests project suites under file
                # suites. The full test title lives on the SPEC (``spec.title``);
                # the test object itself has no ``title`` field here, so the
                # previous ``test_data.get("title")`` lookup yielded "Unknown".
                for suite in suites or []:
                    file_fallback = suite.get("file", "")
                    for spec in suite.get("specs", []):
                        spec_title = spec.get("title", "") or "Unknown"
                        spec_file = spec.get("file") or file_fallback or ""
                        spec_line = spec.get("line", 0)
                        for test in spec.get("tests", []):
                            test_info = self._parse_test_result(
                                test,
                                title=spec_title,
                                file=spec_file,
                                line=spec_line,
                            )
                            tests.append(test_info)
                            summary["total"] += 1
                            status = test_info["status"]
                            if status == "passed":
                                summary["passed"] += 1
                            elif status == "failed":
                                summary["failed"] += 1
                            elif status == "skipped":
                                summary["skipped"] += 1
                            if test_info.get("is_flaky"):
                                summary["flaky"] += 1
                    walk_suites(suite.get("suites", []))

            walk_suites(data.get("suites", []))

            return {"tests": tests, "summary": summary, "raw_data": data}

        except Exception as e:
            self.logger.error("failed_to_parse_results", error=str(e))
            return {
                "tests": [],
                "summary": {"total": 0, "passed": 0, "failed": 0, "skipped": 0},
                "parse_error": str(e),
            }

    def _parse_test_result(
        self,
        test_data: dict[str, Any],
        title: str | None = None,
        file: str = "",
        line: int = 0,
    ) -> dict[str, Any]:
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
        attachments: list[dict[str, Any]] = []

        if status == "failed" and results:
            last_result = results[-1]
            error = last_result.get("error") or {}
            if not error and last_result.get("errors"):
                error = last_result["errors"][-1] or {}
            error_message = error.get("message")
            error_stack = error.get("stack")
            attachments = last_result.get("attachments", []) or []

        file = file or test_data.get("file", "")
        line = line or test_data.get("line", 0)

        return {
            "title": test_data.get("title") or title or "Unknown",
            "file": file,
            "line": line,
            "project": test_data.get("projectName") or "unknown",
            "status": status,
            "duration_ms": sum(r.get("duration", 0) for r in results),
            "retry_count": max(0, len(results) - 1),
            "error_message": error_message,
            "error_stack": error_stack,
            "annotations": test_data.get("annotations", []),
            "browser": test_data.get("projectName"),
            "attachments": attachments,
            "is_flaky": len(results) > 1 and results[-1].get("status") == "passed",
        }

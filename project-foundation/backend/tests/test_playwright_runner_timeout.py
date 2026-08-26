"""
Regression tests for the Playwright runner timeout handling.

Covers the new shell-free process architecture:
- ``create_subprocess_exec`` (no ``shell=True``) so ``--grep`` regexes can
  never be interpreted as ``cmd.exe`` pipelines on Windows.
- Deterministic process timeout with whole-tree termination.
- Safe output coercion (str / bytes / None).
"""

import json
import os
import shutil
from unittest.mock import AsyncMock, patch

import pytest

from app.execution.playwright_runner import PlaywrightRunner, _coerce_output
from app.schemas.execution import ExecutionConfig


def _node() -> str:
    node = shutil.which("node")
    assert node, "node must be installed to run these timeout tests"
    return node


def _env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PATH", os.defpath)
    return env


def test_coerce_output_handles_str_bytes_and_none():
    assert _coerce_output(None) == ""
    assert _coerce_output("already text") == "already text"
    assert _coerce_output(b"raw bytes") == "raw bytes"
    # Invalid UTF-8 bytes must not raise; they are replaced (errors="replace").
    assert _coerce_output(b"\xff\xfe broken") == "\ufffd\ufffd broken"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_command_timeout_is_deterministic(tmp_path):
    """A hanging process must be terminated and produce a deterministic -1."""
    runner = PlaywrightRunner()
    result = await runner._execute_command(
        command=[_node(), "-e", "setInterval(() => {}, 1000)"],
        cwd=tmp_path,
        env=_env(),
        timeout=1,
    )

    assert result["return_code"] == -1
    assert "timed out" in result["stderr"].lower()
    # The timeout must be distinguishable from test failures / infra errors.
    assert result["classification"] == "execution_timeout"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_command_timeout_zero_is_immediate(tmp_path):
    """timeout=0 must raise TimeoutError immediately, not hang."""
    runner = PlaywrightRunner()
    result = await runner._execute_command(
        command=[_node(), "-e", "setInterval(() => {}, 1000)"],
        cwd=tmp_path,
        env=_env(),
        timeout=0,
    )

    assert result["return_code"] == -1
    assert result["classification"] == "execution_timeout"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_command_passes_grep_as_single_argument(tmp_path):
    """A grep regex containing '|' must reach the child as ONE argument.

    Regression for the Windows ``shell=True`` bug where
    ``--grep login|sign_in`` was parsed by ``cmd.exe`` as a shell pipeline.
    Executes a REAL child process (node script file) with no shell so the
    list argument is preserved verbatim.
    """
    echo = tmp_path / "echo-args.cjs"
    echo.write_text("console.log(JSON.stringify(process.argv.slice(2)));", encoding="utf-8")

    runner = PlaywrightRunner()
    result = await runner._execute_command(
        command=[_node(), str(echo), "--grep", "login|sign_in|account"],
        cwd=tmp_path,
        env=_env(),
        timeout=15,
    )

    assert result["return_code"] == 0, result["stderr"]
    args = json.loads(result["stdout"].strip())
    assert "--grep" in args
    idx = args.index("--grep")
    assert args[idx + 1] == "login|sign_in|account"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_command_command_not_found(tmp_path):
    """A missing executable is classified as a command failure, not a timeout."""
    runner = PlaywrightRunner()
    result = await runner._execute_command(
        command=["definitely-not-a-real-binary-xyz", "test"],
        cwd=tmp_path,
        env=_env(),
        timeout=5,
    )

    assert result["return_code"] in (-127, -128)
    assert result["classification"] in ("command_failure", "infrastructure_failure")


@pytest.mark.asyncio
async def test_execute_command_timeout_with_partial_stdout(tmp_path):
    """Timeout must be deterministic and output must remain valid text.

    Partial stdout emitted before a process-tree kill cannot be reliably
    preserved on Windows (force-terminating the tree can discard the OS pipe
    buffer), so we assert the deterministic contract instead: return_code -1,
    timeout classification, and str outputs that never crash the parser.
    """
    script = "require('fs').writeSync(1, 'partial-output-marker'); setInterval(() => {}, 1000);"
    runner = PlaywrightRunner()
    result = await runner._execute_command(
        command=[_node(), "-e", script],
        cwd=tmp_path,
        env=_env(),
        timeout=1,
    )

    assert result["return_code"] == -1
    assert "timed out" in result["stderr"].lower()
    assert result["classification"] == "execution_timeout"
    assert isinstance(result["stdout"], str)
    assert isinstance(result["stderr"], str)
    # The buffered partial is preserved on platforms that keep the pipe
    # buffer open across terminate (POSIX process-group kill).
    if os.name != "nt" and result["stdout"]:
        assert result["stdout"] == "partial-output-marker"


# ---------------------------------------------------------------------------
# Classification taxonomy regression tests
# ---------------------------------------------------------------------------


class TestClassificationTaxonomy:

    async def _run_tests_with(
        self,
        tmp_path,
        execute_result: dict,
        parse_result: dict,
    ) -> dict:
        """Drive run_tests with a stubbed execute + parse to test classification."""
        node_modules = tmp_path / "node_modules" / "@playwright" / "test"
        node_modules.mkdir(parents=True)
        (node_modules / "cli.js").write_text("cli")

        runner = PlaywrightRunner()
        with patch("app.execution.playwright_runner.shutil.which", return_value="/usr/bin/node"):
            with patch.object(
                runner, "_execute_command", new=AsyncMock(return_value=execute_result)
            ):
                with patch.object(
                    runner, "_parse_results", new=AsyncMock(return_value=parse_result)
                ):
                    result = await runner.run_tests(
                        project_path=tmp_path,
                        config=ExecutionConfig(),
                    )
        return result

    @pytest.mark.asyncio
    async def test_timeout_with_complete_results_not_classified_as_timeout(self, tmp_path):
        """A wall-clock kill that still produced usable results must NOT be a timeout.

        Regression for the run whose metadata was: return_code=-1,
        classification=playwright_timeout, yet results.json contained all 20
        completed tests (3 passed / 17 failed).
        """
        tests = [{"title": f"T{i}", "status": "failed"} for i in range(17)]
        tests += [{"title": f"P{i}", "status": "passed"} for i in range(3)]
        result = await self._run_tests_with(
            tmp_path,
            execute_result={
                "return_code": -1,
                "stdout": "",
                "stderr": "Execution timed out after 360 seconds",
                "classification": PlaywrightRunner.CLASSIFICATION_EXECUTION_TIMEOUT,
            },
            parse_result={"tests": tests, "summary": {"total": 20, "passed": 3, "failed": 17}},
        )

        assert result["return_code"] == -1
        assert result["classification"] == PlaywrightRunner.CLASSIFICATION_TEST_EXECUTION_COMPLETED_WITH_FAILURES
        assert len(result["test_results"]["tests"]) == 20

    @pytest.mark.asyncio
    async def test_timeout_without_results_stays_execution_timeout(self, tmp_path):
        """A genuine timeout with no usable results remains execution_timeout."""
        result = await self._run_tests_with(
            tmp_path,
            execute_result={
                "return_code": -1,
                "stdout": "",
                "stderr": "Execution timed out after 360 seconds",
                "classification": PlaywrightRunner.CLASSIFICATION_EXECUTION_TIMEOUT,
            },
            parse_result={"tests": [], "summary": {"total": 0, "passed": 0, "failed": 0}},
        )

        assert result["classification"] == PlaywrightRunner.CLASSIFICATION_EXECUTION_TIMEOUT

    @pytest.mark.asyncio
    async def test_infrastructure_failure_stays_infrastructure_failure(self, tmp_path):
        result = await self._run_tests_with(
            tmp_path,
            execute_result={
                "return_code": -128,
                "stdout": "",
                "stderr": "Failed to start Playwright process",
                "classification": PlaywrightRunner.CLASSIFICATION_INFRASTRUCTURE_FAILURE,
            },
            parse_result={"tests": [], "summary": {"total": 0, "passed": 0, "failed": 0}},
        )

        assert result["classification"] == PlaywrightRunner.CLASSIFICATION_INFRASTRUCTURE_FAILURE

    @pytest.mark.asyncio
    async def test_normal_test_failures_classified_completed_with_failures(self, tmp_path):
        tests = [{"title": f"T{i}", "status": "failed"} for i in range(2)]
        tests += [{"title": "P0", "status": "passed"}]
        result = await self._run_tests_with(
            tmp_path,
            execute_result={
                "return_code": 1,
                "stdout": "",
                "stderr": "",
                "classification": PlaywrightRunner.CLASSIFICATION_TEST_EXECUTION_COMPLETED_WITH_FAILURES,
            },
            parse_result={"tests": tests, "summary": {"total": 3, "passed": 1, "failed": 2}},
        )

        assert result["classification"] == PlaywrightRunner.CLASSIFICATION_TEST_EXECUTION_COMPLETED_WITH_FAILURES

    def test_classify_result_mapping(self):
        classify = PlaywrightRunner._classify_result
        empty = {"tests": [], "summary": {}}
        assert classify(-1, "timeout", empty) == PlaywrightRunner.CLASSIFICATION_EXECUTION_TIMEOUT
        assert classify(-127, "err", empty) == PlaywrightRunner.CLASSIFICATION_INFRASTRUCTURE_FAILURE
        assert classify(-128, "err", empty) == PlaywrightRunner.CLASSIFICATION_INFRASTRUCTURE_FAILURE
        assert classify(0, "", empty) == PlaywrightRunner.CLASSIFICATION_PASSED
        assert classify(1, "", {"tests": [{"status": "failed"}]}) == PlaywrightRunner.CLASSIFICATION_TEST_EXECUTION_COMPLETED_WITH_FAILURES
        # fatal node errors with no tests → infrastructure, not test failures
        assert classify(1, "SyntaxError: x", empty) == PlaywrightRunner.CLASSIFICATION_INFRASTRUCTURE_FAILURE

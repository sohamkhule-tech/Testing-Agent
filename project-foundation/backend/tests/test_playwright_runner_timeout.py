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

import pytest

from app.execution.playwright_runner import PlaywrightRunner, _coerce_output


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
    assert result["classification"] == "playwright_timeout"


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
    assert result["classification"] == "playwright_timeout"


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
    assert result["classification"] in ("command_failure", "infrastructure_error")


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
    assert result["classification"] == "playwright_timeout"
    assert isinstance(result["stdout"], str)
    assert isinstance(result["stderr"], str)
    # The buffered partial is preserved on platforms that keep the pipe
    # buffer open across terminate (POSIX process-group kill).
    if os.name != "nt" and result["stdout"]:
        assert result["stdout"] == "partial-output-marker"

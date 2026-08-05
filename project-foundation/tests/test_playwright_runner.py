import json
import pytest
from pathlib import Path

from app.execution.playwright_runner import PlaywrightRunner
from app.schemas.execution import BrowserType, ExecutionConfig
from app.exceptions import ExecutionError


@pytest.mark.unit
class TestPlaywrightRunner:
    def test_build_command_default(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig()
        cmd = runner._build_command(config)

        assert "npx" in cmd
        assert "playwright" in cmd
        assert "test" in cmd
        assert "--reporter" in cmd
        assert "json,html,junit" in cmd
        assert "--headed" not in cmd
        assert "--workers" in cmd

    def test_build_command_with_browser(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(browser=BrowserType.FIREFOX)
        cmd = runner._build_command(config)

        assert "--project" in cmd
        assert "firefox" in cmd

    def test_build_command_headed(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(headless=False)
        cmd = runner._build_command(config)

        assert "--headed" in cmd

    def test_build_command_no_parallel(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(parallel_execution=False)
        cmd = runner._build_command(config)

        idx = cmd.index("--workers")
        assert cmd[idx + 1] == "1"

    def test_build_command_with_retries(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(retries=3)
        cmd = runner._build_command(config)

        idx = cmd.index("--retries")
        assert cmd[idx + 1] == "3"

    def test_build_command_with_grep(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(grep="@smoke")
        cmd = runner._build_command(config)

        idx = cmd.index("--grep")
        assert cmd[idx + 1] == "@smoke"

    def test_build_command_ci_mode(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(is_ci=True)
        cmd = runner._build_command(config)

        assert "--forbid-only" in cmd

    def test_prepare_environment_defaults(self, temp_dir: Path):
        runner = PlaywrightRunner()
        config = ExecutionConfig()
        env = runner._prepare_environment(temp_dir, config)

        assert "HEADLESS" in env
        assert env["HEADLESS"] == "true"
        assert "CI" in env
        assert env["CI"] == "false"
        assert "PLAYWRIGHT_HTML_REPORT" in env
        assert "PLAYWRIGHT_JUNIT_OUTPUT_NAME" in env

    def test_prepare_environment_base_url(self, temp_dir: Path):
        runner = PlaywrightRunner()
        config = ExecutionConfig(base_url="http://test.com")
        env = runner._prepare_environment(temp_dir, config)

        assert env["BASE_URL"] == "http://test.com"

    def test_parse_test_result_passed(self):
        runner = PlaywrightRunner()
        test_data = {
            "title": "Test 1",
            "file": "tests/test.spec.ts",
            "line": 10,
            "results": [{"status": "passed", "duration": 1500}],
            "annotations": [],
        }
        result = runner._parse_test_result(test_data)

        assert result["title"] == "Test 1"
        assert result["file"] == "tests/test.spec.ts"
        assert result["status"] == "passed"
        assert result["duration_ms"] == 1500
        assert result["retry_count"] == 0

    def test_parse_test_result_failed(self):
        runner = PlaywrightRunner()
        test_data = {
            "title": "Failing Test",
            "file": "tests/fail.spec.ts",
            "line": 20,
            "results": [{
                "status": "failed",
                "duration": 500,
                "error": {"message": "Expected true to be false", "stack": "at line 20"}
            }],
            "annotations": [],
        }
        result = runner._parse_test_result(test_data)

        assert result["status"] == "failed"
        assert result["error_message"] == "Expected true to be false"
        assert result["error_stack"] == "at line 20"

    def test_parse_test_result_retried(self):
        runner = PlaywrightRunner()
        test_data = {
            "title": "Flaky Test",
            "file": "tests/flaky.spec.ts",
            "line": 15,
            "results": [
                {"status": "failed", "duration": 100, "error": {"message": "fail 1"}},
                {"status": "passed", "duration": 200},
            ],
            "annotations": [],
        }
        result = runner._parse_test_result(test_data)

        assert result["status"] == "passed"
        assert result["retry_count"] == 1
        assert result["duration_ms"] == 300

    async def test_parse_results_no_file(self, temp_dir: Path):
        runner = PlaywrightRunner()
        result = await runner._parse_results(temp_dir)

        assert result["tests"] == []
        assert result["summary"]["total"] == 0

    async def test_parse_results_with_file(self, temp_dir: Path):
        results_dir = temp_dir / "test-results"
        results_dir.mkdir(parents=True)
        results_file = results_dir / "results.json"

        playwright_data = {
            "suites": [{
                "specs": [{
                    "tests": [{
                        "title": "Test 1",
                        "results": [{"status": "passed", "duration": 100}]
                    }]
                }]
            }]
        }
        results_file.write_text(json.dumps(playwright_data))

        runner = PlaywrightRunner()
        result = await runner._parse_results(temp_dir)

        assert result["summary"]["total"] == 1
        assert result["summary"]["passed"] == 1
        assert len(result["tests"]) == 1
        assert result["tests"][0]["title"] == "Test 1"

    async def test_execute_command_timeout(self):
        runner = PlaywrightRunner()
        result = await runner._execute_command(
            command=["cmd", "/c", "timeout", "/t", "1"],
            cwd=Path("."),
            env={},
            timeout=0,
        )

        assert result["return_code"] == -1
        assert "timed out" in result["stderr"].lower()

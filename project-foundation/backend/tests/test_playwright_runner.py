import json
from pathlib import Path

import pytest

from app.exceptions import ExecutionError
from app.execution.playwright_runner import PlaywrightRunner
from app.schemas.execution import BrowserType, ExecutionConfig


@pytest.mark.unit
class TestPlaywrightRunner:
    def test_build_command_default(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig()
        cmd = runner._build_command(config)

        assert "npx" in cmd
        assert "playwright" in cmd
        assert "test" in cmd
        # Reporters must come from playwright.config.ts; the CLI must not
        # override them (a --reporter flag would suppress allure-playwright).
        assert "--reporter" not in cmd
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
        assert "ALLURE_RESULTS_DIR" in env
        assert env["ALLURE_RESULTS_DIR"] == str(temp_dir / "allure-results")

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
        import os as _os
        import shutil as _shutil
        node = _shutil.which("node")
        if not node:
            pytest.skip("node is required for timeout test")
        env = _os.environ.copy()
        runner = PlaywrightRunner()
        result = await runner._execute_command(
            command=[node, "-e", "setInterval(() => {}, 1000)"],
            cwd=Path("."),
            env=env,
            timeout=0,
        )

        assert result["return_code"] == -1
        assert "timed out" in result["stderr"].lower()
        assert result["classification"] == "playwright_timeout"

    def test_build_command_grep_is_single_argument_with_pipes(self):
        runner = PlaywrightRunner()
        config = ExecutionConfig(grep="login|sign_in|account")
        cmd = runner._build_command(config)

        idx = cmd.index("--grep")
        assert cmd[idx + 1] == "login|sign_in|account"
        # Pipes must live inside ONE argument, never as separate shell tokens.
        assert any(part == "login|sign_in|account" for part in cmd)
        assert "sign_in" not in cmd[idx + 2:]

    def test_resolve_command_uses_local_playwright_cli(self, temp_dir: Path):
        import shutil as _shutil
        (temp_dir / "node_modules" / "@playwright" / "test").mkdir(parents=True)
        (temp_dir / "node_modules" / "@playwright" / "test" / "cli.js").write_text("")
        runner = PlaywrightRunner()
        resolved = runner._resolve_command(
            ["npx", "playwright", "test", "--grep", "login|sign_in|account"],
            temp_dir,
        )

        node = _shutil.which("node") or "node"
        assert resolved[0] == node
        assert resolved[1] == str(temp_dir / "node_modules" / "@playwright" / "test" / "cli.js")
        assert resolved[2:] == ["test", "--grep", "login|sign_in|account"]

    def test_resolve_command_preserves_grep_as_single_argument(self, temp_dir: Path):
        (temp_dir / "node_modules" / "playwright").mkdir(parents=True)
        (temp_dir / "node_modules" / "playwright" / "cli.js").write_text("")
        runner = PlaywrightRunner()
        resolved = runner._resolve_command(
            ["npx", "playwright", "test", "--grep", "login|sign_in"],
            temp_dir,
        )
        idx = resolved.index("--grep")
        assert resolved[idx + 1] == "login|sign_in"

    def test_resolve_command_falls_back_to_playwright_cli(self, temp_dir: Path):
        (temp_dir / "node_modules" / "playwright").mkdir(parents=True)
        (temp_dir / "node_modules" / "playwright" / "cli.js").write_text("")
        runner = PlaywrightRunner()
        resolved = runner._resolve_command(["npx", "playwright", "test"], temp_dir)
        assert resolved[1] == str(temp_dir / "node_modules" / "playwright" / "cli.js")

    def test_resolve_command_raises_when_no_local_cli(self, temp_dir: Path):
        runner = PlaywrightRunner()
        with pytest.raises(ExecutionError):
            runner._resolve_command(["npx", "playwright", "test"], temp_dir)

    def test_resolve_command_passthrough_for_non_npx(self, temp_dir: Path):
        runner = PlaywrightRunner()
        assert runner._resolve_command(["node", "--version"], temp_dir) == ["node", "--version"]

    def test_classify_result(self):
        runner = PlaywrightRunner()
        cases = [
            (-1, runner.CLASSIFICATION_PLAYWRIGHT_TIMEOUT),
            (-127, runner.CLASSIFICATION_COMMAND_FAILURE),
            (-128, runner.CLASSIFICATION_INFRASTRUCTURE_ERROR),
            (0, runner.CLASSIFICATION_PASSED),
            (1, runner.CLASSIFICATION_TEST_FAILURES),
            (2, runner.CLASSIFICATION_TEST_FAILURES),
        ]
        for rc, expected in cases:
            assert runner._classify_result(rc, "", {"tests": []}) == expected

    def test_parse_test_result_playwright_real_schema(self):
        """The actual Playwright JSON reporter has NO 'title' on the test node."""
        runner = PlaywrightRunner()
        test_data = {
            "timeout": 30000,
            "annotations": [],
            "expectedStatus": "passed",
            "projectId": "chromium",
            "projectName": "chromium",
            "status": "failed",
            "results": [{
                "workerIndex": 1,
                "status": "timedOut",
                "duration": 32000,
                "error": {"message": "Test timeout of 30000ms exceeded.", "location": {"file": "tests/login.spec.ts", "line": 24}},
                "startTime": "2026-08-25T10:27:08.482Z",
                "retry": 0,
                "attachments": [{"name": "trace", "contentType": "application/zip", "path": "artifact.zip"}],
            }],
        }
        result = runner._parse_test_result(
            test_data,
            title="Login with Valid Credentials @happy_path",
            file="tests/login.spec.ts",
            line=24,
        )

        assert result["title"] == "Login with Valid Credentials @happy_path"
        assert result["status"] == "failed"
        assert result["browser"] == "chromium"
        assert result["project"] == "chromium"
        assert result["file"] == "tests/login.spec.ts"
        assert result["line"] == 24
        assert result["error_message"] == "Test timeout of 30000ms exceeded."
        assert result["retry_count"] == 0
        assert result["attachments"] == [{"name": "trace", "contentType": "application/zip", "path": "artifact.zip"}]

    async def test_parse_results_real_playwright_schema(self, temp_dir: Path):
        """Nested suites: title comes from spec.title, never 'Unknown'."""
        results_dir = temp_dir / "test-results"
        results_dir.mkdir(parents=True)
        results_file = results_dir / "results.json"

        playwright_data = {
            "suites": [{
                "title": "login-module.spec.ts",
                "file": "login-module.spec.ts",
                "specs": [],
                "suites": [{
                    "title": "Login Module",
                    "specs": [{
                        "title": "Login Page Smoke Test @smoke @critical",
                        "file": "login-module.spec.ts",
                        "line": 11,
                        "tests": [{
                            "projectName": "chromium",
                            "status": "failed",
                            "results": [{"status": "timedOut", "duration": 32000, "error": {"message": "boom"}}],
                        }],
                    }],
                }],
            }]
        }
        results_file.write_text(json.dumps(playwright_data))

        runner = PlaywrightRunner()
        result = await runner._parse_results(temp_dir)

        assert result["summary"]["total"] == 1
        assert result["summary"]["failed"] == 1
        assert result["tests"][0]["title"] == "Login Page Smoke Test @smoke @critical"
        assert result["tests"][0]["title"] != "Unknown"
        assert result["tests"][0]["status"] == "failed"
        assert result["tests"][0]["error_message"] == "boom"

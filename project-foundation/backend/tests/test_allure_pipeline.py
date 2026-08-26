"""Focused regression tests for the Allure reporting pipeline.

Covers the root cause fixed after run f92b88fd-e635-41ce-99f4-5b46e3da3c30:
the IR-driven generator produced projects without allure-playwright /
allure-commandline, and the runner's hardcoded --reporter flag suppressed
config-level reporters entirely.
"""

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agents.execution_agent import ExecutionAgent
from app.execution.allure_report_generator import AllureReportGenerator
from app.execution.playwright_runner import PlaywrightRunner
from app.generators.template_engine import TemplateEngine
from app.schemas.execution import ExecutionConfig


def _fake_ir() -> SimpleNamespace:
    return SimpleNamespace(
        environment=SimpleNamespace(browsers=["chromium"], base_url="https://example.com")
    )


@pytest.mark.unit
class TestGeneratedProjectAllureConfig:
    """Phases 1-2: generated project must ship Allure tooling."""

    def test_package_json_contains_allure_playwright(self, temp_dir: Path):
        engine = TemplateEngine(run_id="allure-test")
        path = engine._generate_package_json(_fake_ir(), temp_dir)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert "allure-playwright" in data["devDependencies"]
        assert "allure-commandline" in data["devDependencies"]

    def test_package_json_preserves_playwright_dependencies(self, temp_dir: Path):
        engine = TemplateEngine(run_id="allure-test")
        path = engine._generate_package_json(_fake_ir(), temp_dir)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert "@playwright/test" in data["devDependencies"]
        assert "typescript" in data["devDependencies"]
        assert "dotenv" in data["devDependencies"]

    def test_package_json_has_allure_scripts(self, temp_dir: Path):
        engine = TemplateEngine(run_id="allure-test")
        path = engine._generate_package_json(_fake_ir(), temp_dir)
        data = json.loads(path.read_text(encoding="utf-8"))

        assert "allure:generate" in data["scripts"]
        assert "allure:open" in data["scripts"]

    def test_config_registers_allure_reporter(self, temp_dir: Path):
        engine = TemplateEngine(run_id="allure-test")
        path = engine._generate_playwright_config(_fake_ir(), temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "'allure-playwright'" in content
        # Existing required reporters preserved
        assert "'html'" in content
        assert "'json'" in content
        assert "'junit'" in content
        # No duplicate reporter entries
        assert content.count("'html'") == 1
        assert content.count("'json'") == 1
        assert content.count("'junit'") == 1
        assert content.count("'allure-playwright'") == 1

    def test_config_allure_reporter_uses_allure_results_dir(self, temp_dir: Path):
        engine = TemplateEngine(run_id="allure-test")
        path = engine._generate_playwright_config(_fake_ir(), temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "process.env.ALLURE_RESULTS_DIR || 'allure-results'" in content


@pytest.mark.unit
class TestRunnerReporterConfiguration:
    """Phase 3: runner must not override config-level reporters."""

    def test_build_command_does_not_override_reporters(self):
        cmd = PlaywrightRunner()._build_command(ExecutionConfig())

        assert "--reporter" not in cmd

    def test_build_command_still_runs_playwright_test(self):
        cmd = PlaywrightRunner()._build_command(ExecutionConfig())

        assert cmd[:3] == ["npx", "playwright", "test"]

    def test_allure_results_dir_is_run_specific(self, temp_dir: Path):
        env = PlaywrightRunner()._prepare_environment(temp_dir, ExecutionConfig())

        assert env["ALLURE_RESULTS_DIR"] == str(temp_dir / "allure-results")

    def test_allure_results_dir_differs_per_run(self, tmp_path: Path):
        run_a = tmp_path / "run-a" / "playwright"
        run_b = tmp_path / "run-b" / "playwright"
        run_a.mkdir(parents=True)
        run_b.mkdir(parents=True)

        env_a = PlaywrightRunner()._prepare_environment(run_a, ExecutionConfig())
        env_b = PlaywrightRunner()._prepare_environment(run_b, ExecutionConfig())

        assert env_a["ALLURE_RESULTS_DIR"] != env_b["ALLURE_RESULTS_DIR"]
        assert env_a["ALLURE_RESULTS_DIR"] == str(run_a / "allure-results")
        assert env_b["ALLURE_RESULTS_DIR"] == str(run_b / "allure-results")


@pytest.mark.unit
class TestExecutionAgentAllureIntegration:
    """Phases 5-6: agent wiring, event semantics, and state separation."""

    @pytest.fixture
    def agent(self):
        return ExecutionAgent()

    @pytest.fixture
    def sample_project(self, temp_dir: Path) -> Path:
        project = temp_dir / "run-x" / "playwright"
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}")
        (project / "playwright.config.ts").write_text("")
        (project / "tests").mkdir()
        (project / "tests" / "test.spec.ts").write_text("")
        (project / "pages").mkdir()
        return project

    def _mock_execution(self, agent, monkeypatch, sample_project: Path):
        async def mock_setup(*a, **kw):
            return {"environment_valid": True, "node_version": "v20", "npm_version": "10"}

        async def mock_run(*a, **kw):
            return {
                "start_time": "2024-01-01T00:00:00",
                "end_time": "2024-01-01T00:00:10",
                "duration_seconds": 10.0,
                "return_code": 0,
                "command": "npx playwright test",
                "stdout": "",
                "stderr": "",
                "test_results": {
                    "tests": [
                        {"title": "T1", "file": "tests/test.spec.ts", "status": "passed",
                         "duration_ms": 100, "retry_count": 0, "annotations": []},
                    ],
                    "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
                },
                "browser": "chromium",
            }

        monkeypatch.setattr(agent.env_manager, "setup_environment", mock_setup)
        monkeypatch.setattr(agent.playwright_runner, "run_tests", mock_run)
        monkeypatch.setattr(agent.env_manager, "cleanup_environment", AsyncMock())

    async def test_report_generated_when_allure_results_exist(
        self, agent, sample_project, monkeypatch
    ):
        self._mock_execution(agent, monkeypatch, sample_project)

        results_dir = sample_project / "allure-results"
        results_dir.mkdir()
        (results_dir / "result.json").write_text("{}", encoding="utf-8")

        # Stub only the external Allure CLI; everything else runs for real.
        def fake_cli(results_dir, output_path, project_path, timeout):
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return 0, "", ""

        monkeypatch.setattr(agent.allure_generator, "_run_allure_command", fake_cli)

        events: list[tuple[str, dict]] = []

        async def capture_emit(run_id, event_type, data=None):
            events.append((event_type, data or {}))

        monkeypatch.setattr("app.agents.execution_agent.emit", capture_emit)

        result = await agent.execute({
            "run_id": "run-allure-ok",
            "execution_id": "run-allure-ok",
            "project_path": str(sample_project),
            "config": ExecutionConfig(),
            "skip_install": True,
        })

        expected_report = (
            sample_project.parent / "execution-artifacts" / "reports" / "allure-report"
        )
        assert result["allure_report"]["status"] == "generated"
        assert result["report_files"].get("allure-report") == str(expected_report)
        assert (expected_report / "index.html").exists()

        event_types = [e[0] for e in events]
        assert "report_generation_started" in event_types
        assert "report_generation_completed" in event_types
        assert "report_available" in event_types
        assert "report_generation_failed" not in event_types
        # Ordering
        assert event_types.index("report_generation_started") < \
            event_types.index("report_generation_completed") < \
            event_types.index("report_available")

    async def test_report_generated_from_playwright_fallback_results(
        self, agent, sample_project, monkeypatch
    ):
        self._mock_execution(agent, monkeypatch, sample_project)
        # No allure-results directory at all; the generator falls back to the
        # parsed Playwright JSON summary and still builds an Allure report.
        def fake_cli(results_dir, output_path, project_path, timeout):
            output_path.mkdir(parents=True, exist_ok=True)
            (output_path / "index.html").write_text("<html></html>", encoding="utf-8")
            return 0, "", ""

        monkeypatch.setattr(agent.allure_generator, "_run_allure_command", fake_cli)

        events: list[tuple[str, dict]] = []

        async def capture_emit(run_id, event_type, data=None):
            events.append((event_type, data or {}))

        monkeypatch.setattr("app.agents.execution_agent.emit", capture_emit)

        result = await agent.execute({
            "run_id": "run-allure-missing",
            "execution_id": "run-allure-missing",
            "project_path": str(sample_project),
            "config": ExecutionConfig(),
            "skip_install": True,
        })

        # Execution itself still completes...
        assert result["status"] == "completed"
        assert result["allure_report"]["status"] == "generated"
        assert "allure-report" in result["report_files"]
        assert (
            sample_project.parent / "execution-artifacts" / "reports" / "allure-report" / "index.html"
        ).exists()
        assert list((sample_project / "allure-results").glob("*-result.json"))

        event_types = [e[0] for e in events]
        assert "report_generation_started" in event_types
        assert "report_generation_completed" in event_types
        assert "report_available" in event_types
        assert "report_generation_failed" not in event_types


@pytest.mark.unit
class TestAllureGeneratorContract:
    """Phase 5: generator receives correct dirs and stays partial-safe."""

    def test_generate_returns_generated_with_index_html(self, temp_dir: Path):
        results_dir = temp_dir / "allure-results"
        results_dir.mkdir()
        (results_dir / "result.json").write_text("{}", encoding="utf-8")
        output = temp_dir / "reports" / "allure-report"

        generator = AllureReportGenerator()

        captured: dict = {}

        def fake_run(results_dir, output_path, project_path, timeout):
            captured["results_dir"] = results_dir
            captured["output_path"] = output_path
            output.mkdir(parents=True)
            (output / "index.html").write_text("<html></html>", encoding="utf-8")
            return 0, "", ""

        generator._run_allure_command = fake_run  # type: ignore[method-assign]

        result = generator.generate(
            results_dir=results_dir,
            output_path=output,
            project_path=temp_dir,
        )

        assert result["status"] == "generated"
        assert captured["results_dir"] == results_dir
        assert captured["output_path"] == output
        assert (output / "index.html").exists()

    def test_generate_unavailable_without_results(self, temp_dir: Path):
        generator = AllureReportGenerator()
        result = generator.generate(
            results_dir=temp_dir / "allure-results",
            output_path=temp_dir / "reports" / "allure-report",
        )

        assert result["status"] == "unavailable"
        assert "No Allure results found" in result["error"]

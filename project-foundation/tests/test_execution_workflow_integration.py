import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from app.agents.execution_agent import ExecutionAgent
from app.execution.environment_manager import EnvironmentManager
from app.execution.playwright_runner import PlaywrightRunner
from app.execution.failure_analyzer import FailureAnalyzer
from app.execution.retry_manager import RetryManager
from app.execution.artifact_collector import ArtifactCollector
from app.execution.metrics_generator import MetricsGenerator
from app.execution.report_generator import ReportGenerator
from app.schemas.execution import ExecutionConfig


@pytest.mark.integration
class TestExecutionWorkflowIntegration:
    async def test_full_execution_pipeline(self, temp_dir: Path, monkeypatch):
        project = temp_dir / "generated-playwright-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text('{"name": "test", "dependencies": {"@playwright/test": "^1.40.0"}}')
        (project / "playwright.config.ts").write_text("module.exports = {};")
        (project / "tests").mkdir()
        (project / "tests" / "example.spec.ts").write_text("")
        (project / "pages").mkdir()
        (project / "pages" / "home.ts").write_text("")

        env_mgr = EnvironmentManager()
        pw_runner = PlaywrightRunner()
        failure_analyzer = FailureAnalyzer()
        retry_mgr = RetryManager()
        artifact_collector = ArtifactCollector()
        metrics_gen = MetricsGenerator()
        report_gen = ReportGenerator()

        env_report = await env_mgr.generate_environment_report()
        assert env_report is not None
        assert "os_platform" in env_report

        validation_result = await env_mgr._validate_environment(project)
        assert "valid" in validation_result

        config = ExecutionConfig()
        cmd = pw_runner._build_command(config)
        assert "npx" in cmd
        assert "playwright" in cmd

        test_results = [
            {"title": "Login Test", "file": "tests/login.spec.ts", "status": "passed",
             "duration_ms": 500, "retry_count": 0, "annotations": []},
            {"title": "Form Test", "file": "tests/form.spec.ts", "status": "failed",
             "duration_ms": 300, "retry_count": 0, "annotations": [],
             "error_message": "Timeout waiting for element"},
            {"title": "Nav Test", "file": "tests/nav.spec.ts", "status": "passed",
             "duration_ms": 200, "retry_count": 0, "annotations": []},
        ]

        analyzed = []
        for t in test_results:
            if t["status"] == "failed":
                analysis = failure_analyzer.analyze_failure(
                    test_title=t["title"],
                    error_message=t.get("error_message"),
                    error_stack=t.get("error_stack"),
                    retry_count=t.get("retry_count", 0),
                    test_file=t.get("file"),
                )
                t["failure_analysis"] = analysis.model_dump()
                t["is_flaky"] = analysis.is_flaky
            analyzed.append(t)

        failure_summary = failure_analyzer.analyze_batch(analyzed)
        assert failure_summary.total_failures == 1
        assert len(failure_summary.failure_type_counts) > 0

        retry_tests = retry_mgr.get_retry_tests(
            analyzed, ExecutionConfig(retries=2)
        )
        assert len(retry_tests) == 1
        assert retry_tests[0] == "Form Test"

        output_dir = temp_dir / "artifacts"
        artifact_summary = artifact_collector.collect_artifacts(project, output_dir)
        assert artifact_summary.artifacts_path is not None

        artifact_collector.create_artifact_index(output_dir, analyzed)

        artifact_collector.collect_execution_metadata(project, output_dir, {
            "command": "npx playwright test",
            "return_code": 0,
            "duration_seconds": 10.0,
            "browser": "chromium",
            "start_time": "2024-01-01T00:00:00",
            "end_time": "2024-01-01T00:00:10",
        })

        metrics = metrics_gen.generate_metrics(analyzed, total_duration=30.0)
        assert metrics.total_tests == 3
        assert metrics.tests_passed == 2
        assert metrics.tests_failed == 1
        assert metrics.pass_rate == pytest.approx(66.67, rel=0.1)

        metrics_gen.generate_metrics_file(metrics, output_dir)

        health = metrics_gen.calculate_test_health(analyzed)
        assert health["health_score"] > 0

        from app.schemas.execution import ExecutionSummary, ExecutionStatus, TestResult

        test_result_models = [
            TestResult(
                title=t["title"],
                status=t["status"],
                duration_ms=t["duration_ms"],
                file=t["file"],
                error_message=t.get("error_message"),
                failure_analysis=t.get("failure_analysis"),
                is_flaky=t.get("is_flaky", False),
            )
            for t in analyzed
        ]

        exec_summary = ExecutionSummary(
            execution_id="e2e-test",
            status=ExecutionStatus.COMPLETED if metrics.tests_failed == 0 else ExecutionStatus.COMPLETED_WITH_FAILURES,
            start_time="2024-01-01T00:00:00",
            end_time="2024-01-01T00:00:30",
            duration_seconds=30.0,
            config=config,
            test_results=test_result_models,
            metrics=metrics,
            failure_summary=failure_summary,
            artifacts=artifact_summary,
            environment=env_report,
        )

        reports_dir = output_dir / "reports"
        report_paths = report_gen.generate_reports(exec_summary, reports_dir)

        assert "execution-summary.json" in report_paths
        assert "execution-summary.md" in report_paths
        assert "junit.xml" in report_paths
        assert "dashboard.html" in report_paths
        assert "failure-report.json" in report_paths
        assert "metrics-report.json" in report_paths

        for name, path in report_paths.items():
            assert path.exists(), f"Report {name} not generated at {path}"

        md_content = report_paths["execution-summary.md"].read_text()
        assert "Test Execution Report" in md_content
        assert "3" in md_content
        assert "2" in md_content
        assert "Form Test" in failure_summary.failure_analyses[0]["test_title"]

    async def test_execution_agent_pipeline(self, temp_dir: Path, monkeypatch):
        project = temp_dir / "pw-agent-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}")
        (project / "playwright.config.ts").write_text("")
        (project / "tests").mkdir()
        (project / "tests" / "example.spec.ts").write_text("")
        (project / "pages").mkdir()

        agent = ExecutionAgent()

        async def mock_setup(*a, **kw):
            return {"environment_valid": True, "node_version": "v18.0.0"}

        async def mock_run(*a, **kw):
            return {
                "start_time": "2024-01-01T00:00:00",
                "end_time": "2024-01-01T00:00:15",
                "duration_seconds": 15.0,
                "return_code": 0,
                "command": "npx playwright test",
                "stdout": "All tests passed",
                "stderr": "",
                "test_results": {
                    "tests": [
                        {"title": "Login Test", "file": "tests/login.spec.ts",
                         "status": "passed", "duration_ms": 500, "retry_count": 0,
                         "line": 1, "annotations": []},
                        {"title": "Form Test", "file": "tests/form.spec.ts",
                         "status": "passed", "duration_ms": 300, "retry_count": 0,
                         "line": 1, "annotations": []},
                    ],
                    "summary": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
                },
                "browser": "chromium",
            }

        monkeypatch.setattr(agent.env_manager, "setup_environment", mock_setup)
        monkeypatch.setattr(agent.playwright_runner, "run_tests", mock_run)
        monkeypatch.setattr(agent.env_manager, "cleanup_environment", AsyncMock())

        result = await agent.execute({
            "run_id": str(uuid4()),
            "execution_id": "e2e-agent",
            "project_path": str(project),
            "config": ExecutionConfig(skip_install=True),
            "skip_install": True,
        })

        assert result["status"] == "completed"
        assert result["metrics"]["total_tests"] == 2
        assert result["metrics"]["tests_passed"] == 2
        assert result["execution_summary"] is not None
        assert "report_files" in result
        assert "execution-summary.json" in result["report_files"]
        assert "dashboard.html" in result["report_files"]

    async def test_retry_integration(self, temp_dir: Path, monkeypatch):
        project = temp_dir / "retry-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}")
        (project / "playwright.config.ts").write_text("")
        (project / "tests").mkdir()
        (project / "tests" / "test.spec.ts").write_text("")
        (project / "pages").mkdir()

        agent = ExecutionAgent()

        call_count = 0

        async def mock_run(*a, **kw):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "start_time": "2024-01-01T00:00:00",
                    "end_time": "2024-01-01T00:00:10",
                    "duration_seconds": 10.0,
                    "return_code": 1,
                    "command": "npx playwright test",
                    "stdout": "",
                    "stderr": "Test failed",
                    "test_results": {
                        "tests": [
                            {"title": "Flaky Test", "file": "tests/test.spec.ts",
                             "status": "failed", "duration_ms": 200, "retry_count": 0,
                             "line": 1, "annotations": [],
                             "error_message": "Timeout exceeded"},
                        ],
                        "summary": {"total": 1, "passed": 0, "failed": 1, "skipped": 0},
                    },
                    "browser": "chromium",
                }
            else:
                return {
                    "start_time": "2024-01-01T00:00:10",
                    "end_time": "2024-01-01T00:00:15",
                    "duration_seconds": 5.0,
                    "return_code": 0,
                    "command": "npx playwright test",
                    "stdout": "All passed",
                    "stderr": "",
                    "test_results": {
                        "tests": [
                            {"title": "Flaky Test", "file": "tests/test.spec.ts",
                             "status": "passed", "duration_ms": 150, "retry_count": 1,
                             "line": 1, "annotations": []},
                        ],
                        "summary": {"total": 1, "passed": 1, "failed": 0, "skipped": 0},
                    },
                    "browser": "chromium",
                }

        monkeypatch.setattr(agent.env_manager, "setup_environment", AsyncMock(
            return_value={"environment_valid": True}
        ))
        monkeypatch.setattr(agent.playwright_runner, "run_tests", mock_run)
        monkeypatch.setattr(agent.env_manager, "cleanup_environment", AsyncMock())

        result = await agent.execute({
            "run_id": str(uuid4()),
            "execution_id": "retry-test",
            "project_path": str(project),
            "config": ExecutionConfig(retries=1, skip_install=True),
            "skip_install": True,
        })

        assert result["status"] == "completed"
        assert call_count == 2
        assert result["retry_summary"] is not None
        assert result["retry_summary"]["tests_retried"] >= 1

import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from app.agents.execution_agent import ExecutionAgent
from app.exceptions import AgentExecutionError
from app.schemas.execution import ExecutionConfig


@pytest.mark.unit
class TestExecutionAgent:
    @pytest.fixture
    def agent(self):
        return ExecutionAgent()

    @pytest.fixture
    def sample_project(self, temp_dir: Path) -> Path:
        project = temp_dir / "test-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}")
        (project / "playwright.config.ts").write_text("")
        (project / "tests").mkdir()
        (project / "tests" / "test.spec.ts").write_text("")
        (project / "pages").mkdir()
        (project / "pages" / "home.ts").write_text("")
        return project

    async def test_execute_requires_project_path(self, agent):
        with pytest.raises((KeyError, AgentExecutionError)):
            await agent.execute({})

    async def test_basic_execution_pipeline(self, agent, sample_project, monkeypatch):
        async def mock_setup(*a, **kw):
            return {"environment_valid": True, "node_version": "v18.0.0", "npm_version": "9.0.0"}

        async def mock_run(*a, **kw):
            return {
                "start_time": "2024-01-01T00:00:00",
                "end_time": "2024-01-01T00:00:10",
                "duration_seconds": 10.0,
                "return_code": 0,
                "command": "npx playwright test",
                "stdout": "All tests passed",
                "stderr": "",
                "test_results": {
                    "tests": [
                        {"title": "Test 1", "file": "tests/test.spec.ts", "status": "passed",
                         "duration_ms": 100, "retry_count": 0, "annotations": []},
                        {"title": "Test 2", "file": "tests/test.spec.ts", "status": "passed",
                         "duration_ms": 200, "retry_count": 0, "annotations": []},
                    ],
                    "summary": {"total": 2, "passed": 2, "failed": 0, "skipped": 0},
                },
                "browser": "chromium",
            }

        monkeypatch.setattr(agent.env_manager, "setup_environment", mock_setup)
        monkeypatch.setattr(agent.playwright_runner, "run_tests", mock_run)
        monkeypatch.setattr(agent.env_manager, "cleanup_environment", AsyncMock())

        input_data = {
            "run_id": "test-run-001",
            "execution_id": "exec-001",
            "project_path": str(sample_project),
            "config": ExecutionConfig(),
            "skip_install": True,
        }

        result = await agent.execute(input_data)

        assert result["status"] == "completed"
        assert result["run_id"] == "test-run-001"
        assert result["execution_id"] == "exec-001"
        assert result["metrics"]["total_tests"] == 2
        assert result["metrics"]["tests_passed"] == 2
        assert result["metrics"]["tests_failed"] == 0
        assert result["project_path"] == str(sample_project)
        assert "execution_summary" in result
        assert "report_files" in result

    async def test_execution_with_failures(self, agent, sample_project, monkeypatch):
        async def mock_setup(*a, **kw):
            return {"environment_valid": True}

        async def mock_run(*a, **kw):
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
                        {"title": "Test 1", "file": "tests/test.spec.ts", "status": "passed",
                         "duration_ms": 100, "retry_count": 0, "annotations": []},
                        {"title": "Test 2", "file": "tests/test.spec.ts", "status": "failed",
                         "duration_ms": 200, "retry_count": 0, "annotations": [],
                         "error_message": "Timeout exceeded"},
                    ],
                    "summary": {"total": 2, "passed": 1, "failed": 1, "skipped": 0},
                },
                "browser": "chromium",
            }

        monkeypatch.setattr(agent.env_manager, "setup_environment", mock_setup)
        monkeypatch.setattr(agent.playwright_runner, "run_tests", mock_run)
        monkeypatch.setattr(agent.env_manager, "cleanup_environment", AsyncMock())

        input_data = {
            "run_id": "test-run-002",
            "execution_id": "exec-002",
            "project_path": str(sample_project),
            "config": ExecutionConfig(retries=1),
            "skip_install": True,
        }

        result = await agent.execute(input_data)

        assert result["status"] == "completed_with_failures"
        assert result["metrics"]["tests_failed"] == 1
        assert result["failure_summary"] is not None
        assert result["failure_summary"]["total_failures"] == 1

    async def test_parse_test_results(self, agent):
        results = {"tests": [{"title": "A", "status": "passed"}]}
        parsed = agent._parse_test_results(results)
        assert len(parsed) == 1
        assert parsed[0]["title"] == "A"

    def test_get_system_prompt(self, agent):
        prompt = agent.get_system_prompt()
        assert "Execution Agent" in prompt

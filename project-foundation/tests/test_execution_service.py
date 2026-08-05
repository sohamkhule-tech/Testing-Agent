import pytest
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

from app.services.execution_service import ExecutionService
from app.schemas.execution import ExecutionConfig, ExecutionRequest
from app.exceptions import ValidationError


@pytest.mark.unit
class TestExecutionService:
    async def test_initialize(self):
        service = ExecutionService()
        assert service.agent is None

        await service.initialize()
        assert service.agent is not None

    async def test_execute_tests_validates_project_path(self):
        service = ExecutionService()
        with pytest.raises(ValidationError, match="Project not found"):
            await service.execute_tests(
                run_id=str(uuid4()),
                project_path="/nonexistent/path",
            )

    async def test_execute_tests_missing_files(self, temp_dir: Path):
        project = temp_dir / "incomplete"
        project.mkdir()

        service = ExecutionService()
        with pytest.raises(ValidationError, match="Missing required file"):
            await service.execute_tests(
                run_id=str(uuid4()),
                project_path=str(project),
            )

    async def test_execute_tests_valid_project(self, temp_dir: Path):
        project = temp_dir / "valid-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}")
        (project / "playwright.config.ts").write_text("")
        (project / "tests").mkdir()
        (project / "pages").mkdir()

        service = ExecutionService()
        await service.initialize()

        result = await service.execute_tests(
            run_id=str(uuid4()),
            project_path=str(project),
            config=ExecutionConfig(browser=None, timeout_ms=5000),
            skip_install=True,
        )

        assert result["status"] is not None
        assert result["project_path"] == str(project)

    async def test_execute_from_request(self, temp_dir: Path):
        project = temp_dir / "req-project"
        project.mkdir(parents=True)
        (project / "package.json").write_text("{}")
        (project / "playwright.config.ts").write_text("")
        (project / "tests").mkdir()
        (project / "pages").mkdir()

        request = ExecutionRequest(
            run_id=str(uuid4()),
            workspace_path=str(temp_dir),
            project_path=str(project),
            config=ExecutionConfig(browser=None, timeout_ms=5000),
        )

        service = ExecutionService()
        await service.initialize()

        result = await service.execute_from_request(request)

        assert result.status is not None

    async def test_shutdown(self):
        service = ExecutionService()
        await service.shutdown()

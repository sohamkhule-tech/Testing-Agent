import pytest
from pathlib import Path

from app.execution.environment_manager import EnvironmentManager
from app.exceptions import ExecutionError


@pytest.mark.unit
class TestEnvironmentManager:
    async def test_setup_environment_valid_project(self, temp_dir: Path):
        project_path = temp_dir / "test-project"
        project_path.mkdir(parents=True)
        (project_path / "package.json").write_text("{}")
        (project_path / "playwright.config.ts").write_text("")
        (project_path / "tests").mkdir()
        (project_path / "pages").mkdir()

        mgr = EnvironmentManager()
        result = await mgr.setup_environment(project_path, skip_install=True)

        assert result["project_path"] == str(project_path)
        assert result["dependencies_installed"] is False
        assert result["browsers_installed"] is False

    async def test_setup_environment_missing_files(self, temp_dir: Path):
        project_path = temp_dir / "bad-project"
        project_path.mkdir()

        mgr = EnvironmentManager()
        with pytest.raises(ExecutionError, match="Missing required file"):
            await mgr.setup_environment(project_path, skip_install=True)

    async def test_setup_environment_missing_dirs(self, temp_dir: Path):
        project_path = temp_dir / "bad-project"
        project_path.mkdir()
        (project_path / "package.json").write_text("{}")
        (project_path / "playwright.config.ts").write_text("")

        mgr = EnvironmentManager()
        with pytest.raises(ExecutionError, match="Missing required directory"):
            await mgr.setup_environment(project_path, skip_install=True)

    async def test_generate_environment_report(self):
        mgr = EnvironmentManager()
        report = await mgr.generate_environment_report()

        assert "os_platform" in report
        assert "python_version" in report
        assert "path_separator" in report
        assert "current_directory" in report

    async def test_validate_project_structure(self, temp_dir: Path):
        project_path = temp_dir / "valid"
        project_path.mkdir()
        (project_path / "package.json").write_text("{}")
        (project_path / "playwright.config.ts").write_text("")
        (project_path / "tests").mkdir()
        (project_path / "pages").mkdir()

        mgr = EnvironmentManager()
        mgr._validate_project_structure(project_path)

    def test_load_environment_variables(self, temp_dir: Path):
        project_path = temp_dir / "env-test"
        project_path.mkdir()
        env_file = project_path / ".env"
        env_file.write_text("KEY1=value1\nKEY2=value2\n# comment\n")

        mgr = EnvironmentManager()
        env_vars = mgr.load_environment_variables(project_path)

        assert env_vars["KEY1"] == "value1"
        assert env_vars["KEY2"] == "value2"
        assert len(env_vars) == 2

    def test_load_environment_variables_no_file(self, temp_dir: Path):
        project_path = temp_dir / "no-env"
        project_path.mkdir()

        mgr = EnvironmentManager()
        env_vars = mgr.load_environment_variables(project_path)
        assert env_vars == {}

    async def test_cleanup_environment(self, temp_dir: Path):
        project_path = temp_dir / "cleanup"
        project_path.mkdir()
        cache_dir = project_path / ".cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "test.txt").write_text("test")

        mgr = EnvironmentManager()
        await mgr.cleanup_environment(project_path)

        assert not cache_dir.exists()

    async def test_validate_environment_detects_missing_node(self, temp_dir: Path):
        project_path = temp_dir / "validate"
        project_path.mkdir()

        mgr = EnvironmentManager()
        validation = await mgr._validate_environment(project_path)

        assert "valid" in validation
        assert "checks" in validation

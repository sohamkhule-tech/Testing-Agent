import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.exceptions import ExecutionError
from app.logging import LoggerMixin


class EnvironmentManager(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    async def setup_environment(
        self,
        project_path: Path,
        skip_install: bool = False
    ) -> dict[str, Any]:
        self.logger.info("setting_up_environment", project_path=str(project_path))

        try:
            self._validate_project_structure(project_path)

            env_report = await self._detect_system_environment()

            if not skip_install:
                await self._install_dependencies(project_path)
                await self._install_browsers(project_path)

            env_vars = self.load_environment_variables(project_path)

            validation = await self._validate_environment(project_path)

            self._prepare_workspace(project_path)

            setup_info = {
                "project_path": str(project_path),
                "dependencies_installed": not skip_install,
                "browsers_installed": not skip_install,
                "environment_valid": validation["valid"],
                "node_version": env_report.get("node_version"),
                "npm_version": env_report.get("npm_version"),
                "playwright_version": env_report.get("playwright_version"),
                "playwright_installed": validation.get("playwright_installed", False),
                "browsers_available": env_report.get("browsers_available", []),
                "env_vars_loaded": len(env_vars),
                "os_platform": env_report.get("os_platform"),
                "python_version": env_report.get("python_version"),
            }

            self.logger.info("environment_setup_complete", **setup_info)
            return setup_info

        except Exception as e:
            self.logger.error("environment_setup_failed", error=str(e))
            raise ExecutionError(f"Environment setup failed: {str(e)}") from e

    async def generate_environment_report(self) -> dict[str, Any]:
        try:
            report = await self._detect_system_environment()
            report["path_separator"] = os.sep
            report["current_directory"] = str(Path.cwd())
            report["home_directory"] = str(Path.home())
            report["path"] = os.environ.get("PATH", "")
            return report
        except Exception as e:
            self.logger.error("environment_report_failed", error=str(e))
            return {"error": str(e)}

    async def _detect_system_environment(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "os_platform": os.name,
            "python_version": os.sys.version,
        }

        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
            )
            report["node_version"] = result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            report["node_version"] = None

        try:
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
            )
            report["npm_version"] = result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            report["npm_version"] = None

        try:
            result = subprocess.run(
                ["npx", "playwright", "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
            )
            report["playwright_version"] = result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            report["playwright_version"] = None

        browsers = []
        for browser in ["chromium", "firefox", "webkit"]:
            try:
                result = subprocess.run(
                    ["npx", "playwright", "install", "--dry-run", browser],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
                )
                browsers.append(browser)
            except Exception:
                pass
        report["browsers_available"] = browsers

        return report

    def _validate_project_structure(self, project_path: Path) -> None:
        required_files = ["package.json", "playwright.config.ts"]
        for file in required_files:
            if not (project_path / file).exists():
                raise ExecutionError(f"Missing required file: {file}")

        required_dirs = ["tests", "pages"]
        for dir_name in required_dirs:
            if not (project_path / dir_name).exists():
                raise ExecutionError(f"Missing required directory: {dir_name}")

        self.logger.info("project_structure_validated")

    async def _install_dependencies(self, project_path: Path) -> None:
        self.logger.info("installing_npm_dependencies")

        try:
            result = subprocess.run(
                ["npm", "install"],
                cwd=project_path,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, shell=True,
            )

            if result.returncode != 0:
                raise ExecutionError(f"npm install failed: {result.stderr}")

            self.logger.info("npm_dependencies_installed")

        except subprocess.TimeoutExpired:
            raise ExecutionError("npm install timed out after 5 minutes")
        except Exception as e:
            raise ExecutionError(f"Failed to install dependencies: {str(e)}") from e

    async def _install_browsers(self, project_path: Path) -> None:
        self.logger.info("installing_playwright_browsers")

        try:
            result = subprocess.run(
                ["npx", "playwright", "install"],
                cwd=project_path,
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600, shell=True,
            )

            if result.returncode != 0:
                self.logger.warning(
                    "browser_installation_warning",
                    stderr=result.stderr
                )

            self.logger.info("playwright_browsers_installed")

        except subprocess.TimeoutExpired:
            raise ExecutionError("Browser installation timed out after 10 minutes")
        except Exception as e:
            self.logger.warning(f"Browser installation issue: {str(e)}")

    async def _validate_environment(self, project_path: Path) -> dict[str, Any]:
        validation: dict[str, Any] = {"valid": True, "checks": []}

        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
            )
            node_ok = result.returncode == 0
            validation["node_version"] = result.stdout.strip() if node_ok else None
            if not node_ok:
                validation["valid"] = False
                validation["checks"].append("node_missing")
        except Exception:
            validation["valid"] = False
            validation["checks"].append("node_error")
            validation["node_version"] = None

        try:
            result = subprocess.run(
                ["npm", "--version"],
                capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True,
            )
            npm_ok = result.returncode == 0
            validation["npm_version"] = result.stdout.strip() if npm_ok else None
            if not npm_ok:
                validation["valid"] = False
                validation["checks"].append("npm_missing")
        except Exception:
            validation["valid"] = False
            validation["checks"].append("npm_error")
            validation["npm_version"] = None

        node_modules = project_path / "node_modules" / "@playwright" / "test"
        validation["playwright_installed"] = node_modules.exists()
        if not validation["playwright_installed"]:
            validation["valid"] = False
            validation["checks"].append("playwright_not_installed")

        return validation

    def _prepare_workspace(self, project_path: Path) -> None:
        for d in ["test-results", "playwright-report"]:
            (project_path / d).mkdir(parents=True, exist_ok=True)
        self.logger.info("workspace_prepared")

    def load_environment_variables(self, project_path: Path) -> dict[str, str]:
        env_file = project_path / ".env"
        env_vars: dict[str, str] = {}

        if not env_file.exists():
            self.logger.warning("env_file_not_found", path=str(env_file))
            return env_vars

        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        key, value = line.split("=", 1)
                        env_vars[key.strip()] = value.strip()

            self.logger.info("environment_variables_loaded", count=len(env_vars))
            return env_vars

        except Exception as e:
            self.logger.error("failed_to_load_env_vars", error=str(e))
            return {}

    async def cleanup_environment(self, project_path: Path) -> None:
        self.logger.info("cleaning_up_environment", project_path=str(project_path))

        temp_dirs = [
            project_path / ".cache",
            project_path / "playwright" / ".cache",
        ]

        for temp_dir in temp_dirs:
            if temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                    self.logger.debug("removed_temp_dir", path=str(temp_dir))
                except Exception as e:
                    self.logger.warning("cleanup_warning", path=str(temp_dir), error=str(e))

        self.logger.info("environment_cleanup_complete")

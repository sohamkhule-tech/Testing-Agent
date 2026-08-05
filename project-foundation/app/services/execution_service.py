from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.agents.execution_agent import ExecutionAgent
from app.core.interfaces import IService
from app.exceptions import ValidationError
from app.logging import LoggerMixin
from app.schemas.execution import ExecutionConfig, ExecutionRequest, ExecutionResult


class ExecutionService(IService, LoggerMixin):

    def __init__(self) -> None:
        super().__init__()
        self.agent: ExecutionAgent | None = None

    async def initialize(self) -> None:
        self.logger.info("execution_service_initializing")
        self.agent = ExecutionAgent()
        self.logger.info("execution_service_initialized")

    async def execute_tests(
        self,
        run_id: UUID | str,
        project_path: str,
        config: ExecutionConfig | None = None,
        skip_install: bool = False,
    ) -> dict[str, Any]:
        start_time = datetime.now(timezone.utc)
        run_id_str = str(run_id) if isinstance(run_id, UUID) else run_id

        self.logger.info("execution_started", run_id=run_id_str, project_path=project_path)

        try:
            project = Path(project_path)
            if not project.exists():
                raise ValidationError(f"Project not found: {project_path}")

            required_files = ["package.json", "playwright.config.ts"]
            for file in required_files:
                if not (project / file).exists():
                    raise ValidationError(f"Missing required file: {file}")

            self.logger.info("project_validated", path=str(project))

            if not self.agent:
                await self.initialize()

            if not config:
                config = ExecutionConfig()

            input_data = {
                "run_id": run_id_str,
                "execution_id": run_id_str,
                "project_path": str(project),
                "config": config,
                "skip_install": skip_install,
            }

            result = await self.agent.execute(input_data)

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            summary = {
                "run_id": run_id_str,
                "status": result["status"],
                "project_path": result["project_path"],
                "artifacts_path": result["artifacts_path"],
                "reports_path": result["reports_path"],
                "report_files": result["report_files"],
                "metrics": result["metrics"],
                "duration_seconds": duration,
                "execution_summary": result.get("execution_summary"),
                "failure_summary": result.get("failure_summary"),
                "retry_summary": result.get("retry_summary"),
                "playwright_exit_code": result.get("playwright_exit_code"),
            }

            self.logger.info(
                "execution_completed",
                run_id=run_id_str,
                status=summary["status"],
                duration=duration,
            )

            return summary

        except Exception as e:
            self.logger.error("execution_failed", run_id=run_id_str, error=str(e))
            raise

    async def execute_from_request(self, request: ExecutionRequest) -> ExecutionResult:
        start_time = datetime.now(timezone.utc)

        try:
            result_data = await self.execute_tests(
                run_id=request.run_id,
                project_path=request.project_path,
                config=request.config,
                skip_install=False,
            )

            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            result = ExecutionResult(
                status=result_data["status"],
                project_path=result_data["project_path"],
                reports_path=result_data["reports_path"],
                metrics=result_data["metrics"],
                duration_seconds=duration,
            )

            return result

        except Exception as e:
            return ExecutionResult(
                status="failed",
                error_message=str(e),
                duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
            )

    async def shutdown(self) -> None:
        self.logger.info("execution_service_shutdown")

    async def cleanup(self) -> None:
        self.logger.info("execution_service_cleanup")
        self.agent = None

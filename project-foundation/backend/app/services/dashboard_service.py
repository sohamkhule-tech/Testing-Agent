from datetime import datetime, timedelta

from app.constants import RunStatus
from app.core.interfaces import IService
from app.logging import LoggerMixin
from app.repositories.project_repository import ProjectRepository
from app.repositories.run_repository import RunRepository
from app.schemas.project import DashboardStats, ProjectResponse, TestRunResponse


class DashboardService(IService, LoggerMixin):
    def __init__(
        self,
        project_repository: ProjectRepository,
        run_repository: RunRepository,
    ) -> None:
        super().__init__()
        self.project_repo = project_repository
        self.run_repo = run_repository

    async def initialize(self) -> None:
        self.logger.info("dashboard_service_initialized")

    async def cleanup(self) -> None:
        self.logger.info("dashboard_service_cleanup")

    async def get_stats(self) -> DashboardStats:
        projects = await self.project_repo.list_all()
        runs = await self.run_repo.list_all()
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        total_projects = len(projects)
        total_runs = len(runs)
        active_runs = sum(1 for r in runs if r.status in (RunStatus.RUNNING, RunStatus.PENDING))
        pending_reviews = sum(p.pending_reviews for p in projects)
        completed_today = sum(
            1 for r in runs
            if r.status == RunStatus.COMPLETED and r.created_at >= today_start
        )
        completed = sum(1 for r in runs if r.status == RunStatus.COMPLETED)
        success_rate = (completed / total_runs * 100) if total_runs > 0 else 0.0
        return DashboardStats(
            total_projects=total_projects,
            total_runs=total_runs,
            active_runs=active_runs,
            pending_reviews=pending_reviews,
            completed_today=completed_today,
            success_rate=round(success_rate, 1),
        )

    async def get_recent_runs(self, limit: int = 10) -> list[TestRunResponse]:
        runs = await self.run_repo.list_recent(limit=limit)
        return [self._run_to_response(r) for r in runs]

    async def get_recent_projects(self, limit: int = 5) -> list[ProjectResponse]:
        projects = await self.project_repo.list_recent(limit=limit)
        return [self._project_to_response(p) for p in projects]

    def _run_to_response(self, entity) -> TestRunResponse:
        from app.services.project_service import determine_run_stage
        test_run_request = getattr(entity, 'test_run_request', {}) or {}
        config = test_run_request if isinstance(test_run_request, dict) else {}
        target = config.get("target_application", {}) or {}
        scope = config.get("scope", {}) or {}
        started_at = getattr(entity, 'created_at', None)
        ws_path = getattr(entity, 'workspace_path', None)
        real_stage = determine_run_stage(ws_path, getattr(entity, 'current_stage', None))
        return TestRunResponse(
            run_id=getattr(entity, 'run_id', getattr(entity, 'id', None)),
            request_id=getattr(entity, 'request_id', None),
            project_id=getattr(entity, 'project_id', None),
            status=getattr(entity, 'status', RunStatus.PENDING),
            current_phase=real_stage,
            started_at=started_at,
            completed_at=getattr(entity, 'completed_at', None),
            duration_seconds=getattr(entity, 'duration_seconds', None),
            requested_by=getattr(entity, 'requested_by', None),
            workspace_path=getattr(entity, 'workspace_path', None),
            pages_visited=scope.get("max_pages") if isinstance(scope, dict) else None,
            scenarios_generated=None,
            review_status=None,
            error_message=getattr(entity, 'error', None),
        )

    def _project_to_response(self, entity) -> ProjectResponse:
        return ProjectResponse(
            id=entity.id,
            name=entity.name,
            description=entity.description,
            application_url=entity.application_url,
            auth_type=entity.auth_type,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            total_runs=entity.total_runs,
            last_run_at=entity.last_run_at,
            last_run_status=entity.last_run_status,
            pending_reviews=entity.pending_reviews,
            tags=entity.tags,
        )

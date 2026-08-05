from datetime import datetime
from uuid import UUID

from app.constants import RunStatus
from app.core.interfaces import IService
from app.domain.project import ProjectEntity
from app.exceptions import NotFoundError, StorageError, ValidationError
from app.logging import LoggerMixin
from app.repositories.project_repository import ProjectRepository
from app.repositories.run_repository import RunRepository
from app.schemas.project import CreateProjectRequest, ProjectResponse, ProjectStats, RunListResponse, TestRunResponse
from app.utils import generate_uuid


class ProjectService(IService, LoggerMixin):
    def __init__(
        self,
        project_repository: ProjectRepository,
        run_repository: RunRepository,
    ) -> None:
        super().__init__()
        self.project_repo = project_repository
        self.run_repo = run_repository

    async def initialize(self) -> None:
        self.logger.info("project_service_initialized")

    async def cleanup(self) -> None:
        self.logger.info("project_service_cleanup")

    async def create_project(self, request: CreateProjectRequest) -> ProjectResponse:
        try:
            project_id = UUID(generate_uuid())
            now = datetime.utcnow()
            entity = ProjectEntity(
                id=project_id,
                name=request.name,
                description=request.description,
                application_url=request.application_url,
                auth_type=request.auth_type,
                tags=request.tags or [],
                total_runs=0,
                pending_reviews=0,
                created_at=now,
                updated_at=now,
            )
            await self.project_repo.create(entity)
            self.logger.info("project_created", project_id=str(project_id), name=request.name)
            return self._entity_to_response(entity)
        except StorageError:
            raise
        except Exception as e:
            self.logger.error("project_creation_failed", error=str(e))
            raise ValidationError(f"Failed to create project: {str(e)}")

    async def get_project(self, project_id: UUID) -> ProjectResponse:
        entity = await self.project_repo.get_by_id(project_id)
        if not entity:
            raise NotFoundError(f"Project not found: {project_id}", resource_id=str(project_id))
        return self._entity_to_response(entity)

    async def update_project(self, project_id: UUID, data: dict) -> ProjectResponse:
        entity = await self.project_repo.get_by_id(project_id)
        if not entity:
            raise NotFoundError(f"Project not found: {project_id}", resource_id=str(project_id))
        for key, value in data.items():
            if hasattr(entity, key) and value is not None:
                setattr(entity, key, value)
        entity.updated_at = datetime.utcnow()
        await self.project_repo.update(entity)
        return self._entity_to_response(entity)

    async def delete_project(self, project_id: UUID) -> bool:
        if not await self.project_repo.exists(project_id):
            raise NotFoundError(f"Project not found: {project_id}", resource_id=str(project_id))
        return await self.project_repo.delete(project_id)

    async def list_projects(self) -> list[ProjectResponse]:
        entities = await self.project_repo.list_all()
        return [self._entity_to_response(e) for e in entities]

    async def get_project_stats(self, project_id: UUID) -> ProjectStats:
        entity = await self.project_repo.get_by_id(project_id)
        if not entity:
            raise NotFoundError(f"Project not found: {project_id}", resource_id=str(project_id))
        project_runs = await self._get_project_runs(project_id, entity)
        total = len(project_runs)
        successful = sum(1 for r in project_runs if r.status == RunStatus.COMPLETED)
        failed = sum(1 for r in project_runs if r.status == RunStatus.FAILED)
        return ProjectStats(
            total_runs=total,
            successful_runs=successful,
            failed_runs=failed,
            average_duration_seconds=0.0,
        )

    async def get_project_runs_paginated(
        self, project_id: UUID, page: int = 1, page_size: int = 20
    ) -> RunListResponse:
        entity = await self.project_repo.get_by_id(project_id)
        if not entity:
            raise NotFoundError(f"Project not found: {project_id}", resource_id=str(project_id))
        project_runs = await self._get_project_runs(project_id, entity)
        total = len(project_runs)
        start = (page - 1) * page_size
        end = start + page_size
        page_runs = project_runs[start:end]
        runs = []
        for r in page_runs:
            ws_path = getattr(r, 'workspace_path', None)
            real_stage = determine_run_stage(ws_path, getattr(r, 'current_stage', None))
            runs.append(TestRunResponse(
                run_id=r.run_id,
                request_id=r.request_id,
                project_id=project_id,
                status=r.status,
                current_phase=real_stage,
                started_at=r.created_at,
                completed_at=None,
                duration_seconds=None,
                requested_by=r.requested_by,
                workspace_path=r.workspace_path,
                error_message=r.error,
            ))
        return RunListResponse(runs=runs, total=total, page=page, page_size=page_size)

    async def _get_project_runs(self, project_id: UUID, project: ProjectResponse | ProjectEntity):
        all_runs = await self.run_repo.list_all()
        matched = []
        for r in all_runs:
            rid = getattr(r, 'project_id', None)
            if rid is not None and rid == project_id:
                matched.append(r)
        return matched

    def _entity_to_response(self, entity: ProjectEntity) -> ProjectResponse:
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


def determine_run_stage(workspace_path_str: str | None, default_stage: str | None = None) -> str:
    from pathlib import Path
    clean_default = _clean_stage_name(default_stage)
    if not workspace_path_str:
        return clean_default
    try:
        ws = Path(workspace_path_str)
        if ws.exists():
            if (ws / "artifacts" / "test-execution-results.json").exists():
                return "execution"
            if (ws / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json").exists():
                return "code_generation"
            if (ws / "contracts" / "approved-test-plan.json").exists():
                return "code_generation"
            if (ws / "contracts" / "test-plan.json").exists():
                return "test_design"
            if (ws / "contracts" / "inventory.json").exists():
                return "test_design"
            if (ws / "contracts" / "crawl-package.json").exists():
                return "inventory"
    except Exception:
        pass
    return clean_default

def _clean_stage_name(stage: str | None) -> str:
    if not stage:
        return "trigger"
    s = str(stage).lower().replace("-", "_")
    if s in ("awaiting_review", "paused"):
        return "test_design"
    if s in ("initialization", "init", "setup"):
        return "trigger"
    return s

"""
Trigger Service

Business logic for test run initialization.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.constants import RunStatus
from app.core.interfaces import IService
from app.domain import RunContext, RunEntity, RunMetadata
from app.exceptions import NotFoundError, ValidationError
from app.infrastructure import WorkspaceManager
from app.logging import LoggerMixin
from app.repositories import RunRepository
from app.schemas import CreateRunRequest, TestRunRequest
from app.utils import generate_correlation_id, generate_uuid, save_file


class TriggerService(IService, LoggerMixin):
    """
    Service for test run initialization.

    Orchestrates run creation, validation, and workspace setup.
    """

    def __init__(
        self,
        repository: RunRepository,
        workspace_manager: WorkspaceManager,
    ) -> None:
        """
        Initialize trigger service.

        Args:
            repository: Run repository
            workspace_manager: Workspace manager
        """
        super().__init__()
        self.repository = repository
        self.workspace_manager = workspace_manager
        self.settings = get_settings()

    async def initialize(self) -> None:
        """Initialize service resources."""
        self.logger.info("trigger_service_initialized")

    async def cleanup(self) -> None:
        """Cleanup service resources."""
        self.logger.info("trigger_service_cleanup")

    async def create_run(
        self, request: CreateRunRequest, requested_by: str | None = None
    ) -> tuple[RunEntity, RunContext]:
        """
        Create new test run.

        Args:
            request: Run creation request
            requested_by: Optional principal identifier

        Returns:
            Tuple of (run entity, run context)

        Raises:
            ValidationError: If request validation fails
        """
        try:
            # Generate IDs
            run_id = UUID(generate_uuid())
            request_id = request.request_id or UUID(generate_uuid())
            correlation_id = generate_correlation_id()

            # Determine requested_by
            principal = requested_by or request.requested_by or "system"

            self.logger.info(
                "creating_run",
                run_id=str(run_id),
                request_id=str(request_id),
                principal=principal,
            )

            # Create workspace
            context = await self.workspace_manager.create_workspace(
                run_id=run_id,
                request_id=request_id,
                correlation_id=correlation_id,
            )

            # Create canonical test run request
            test_run_request = TestRunRequest(
                run_id=run_id,
                request_id=request_id,
                created_at=datetime.utcnow(),
                requested_by=principal,
                target_application=request.target_application,
                execution_mode=request.execution_mode,
                authentication=request.authentication,
                scope=request.scope,
                ai=request.ai,
                execution=request.execution,
                output=request.output,
                metadata=request.metadata,
            )

            # Save test-run-request.json
            await self._save_test_run_request(context, test_run_request)

            # Create run entity
            entity = RunEntity(
                run_id=run_id,
                request_id=request_id,
                requested_by=principal,
                workspace_path=str(context.workspace_root),
                status=RunStatus.PENDING,
                current_stage="initialization",
                progress_percent=0,
                message="Run initialized",
                test_run_request=test_run_request.model_dump(mode="json"),
            )

            # Persist entity
            await self.repository.create(entity)

            # Save metadata
            await self._save_metadata(context, entity)

            self.logger.info(
                "run_created",
                run_id=str(run_id),
                workspace=str(context.workspace_root),
            )

            return entity, context

        except Exception as e:
            self.logger.error("run_creation_failed", error=str(e))
            raise ValidationError(f"Failed to create run: {str(e)}")

    async def get_run(self, run_id: UUID) -> RunEntity:
        """
        Get run by ID.

        Args:
            run_id: Run identifier

        Returns:
            Run entity

        Raises:
            NotFoundError: If run not found
        """
        entity = await self.repository.get_by_id(run_id)
        if not entity:
            raise NotFoundError(
                f"Run not found: {run_id}",
                resource_id=str(run_id),
            )
        return entity

    async def get_metadata(self, run_id: UUID) -> RunMetadata:
        """
        Get run metadata.

        Args:
            run_id: Run identifier

        Returns:
            Run metadata

        Raises:
            NotFoundError: If run not found
        """
        metadata = await self.repository.get_metadata(run_id)
        if not metadata:
            raise NotFoundError(
                f"Run not found: {run_id}",
                resource_id=str(run_id),
            )
        return metadata

    async def update_status(
        self,
        run_id: UUID,
        status: RunStatus,
        stage: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> bool:
        """
        Update run status.

        Args:
            run_id: Run identifier
            status: New status
            stage: Optional stage
            progress: Optional progress
            message: Optional message
            error: Optional error

        Returns:
            True if updated
        """
        return await self.repository.update_status(
            run_id=run_id,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            error=error,
        )

    async def _save_test_run_request(
        self, context: RunContext, request: TestRunRequest
    ) -> None:
        """Save test-run-request.json contract."""
        file_path = context.contracts_dir / "test-run-request.json"
        data = request.model_dump(mode="json")
        await save_file(file_path, data, indent=True)

        self.logger.info(
            "test_run_request_saved",
            run_id=str(request.run_id),
            path=str(file_path),
        )

    async def _save_metadata(self, context: RunContext, entity: RunEntity) -> None:
        """Save execution metadata."""
        metadata_file = context.metadata_dir / "execution.json"
        metadata = {
            "runId": str(entity.run_id),
            "requestId": str(entity.request_id),
            "requestedBy": entity.requested_by,
            "createdAt": entity.created_at.isoformat(),
            "updatedAt": entity.updated_at.isoformat(),
            "status": entity.status.value if hasattr(entity.status, "value") else entity.status,
            "workspacePath": entity.workspace_path,
            "currentStage": entity.current_stage,
            "progressPercent": entity.progress_percent,
            "message": entity.message,
        }
        await save_file(metadata_file, metadata, indent=True)

        self.logger.info(
            "metadata_saved",
            run_id=str(entity.run_id),
            path=str(metadata_file),
        )

"""
Workspace Manager

Manages creation and organization of run workspaces.
"""

from pathlib import Path
from uuid import UUID

from app.config import get_settings
from app.domain import RunContext
from app.exceptions import StorageError
from app.logging import LoggerMixin
from app.utils import ensure_directory


class WorkspaceManager(LoggerMixin):
    """
    Manages run workspace creation and organization.

    Creates directory structure for each test run.
    """

    def __init__(self) -> None:
        """Initialize workspace manager."""
        super().__init__()
        settings = get_settings()
        self.base_workspace = Path(settings.storage.storage_base_path)
        ensure_directory(self.base_workspace)

    async def create_workspace(
        self, run_id: UUID, request_id: UUID, correlation_id: str
    ) -> RunContext:
        """
        Create complete workspace structure for a run.

        Args:
            run_id: Run identifier
            request_id: Request correlation ID
            correlation_id: Trace correlation ID

        Returns:
            Run context with created directories

        Raises:
            StorageError: If workspace creation fails
        """
        try:
            # Create run context
            context = RunContext.create(
                run_id=run_id,
                request_id=request_id,
                correlation_id=correlation_id,
                base_workspace=self.base_workspace,
            )

            # Create all directories
            directories = [
                context.workspace_root,
                context.artifacts_dir,
                context.logs_dir,
                context.reports_dir,
                context.metadata_dir,
                context.contracts_dir,
                context.screenshots_dir,
            ]

            for directory in directories:
                ensure_directory(directory)

            self.logger.info(
                "workspace_created",
                run_id=str(run_id),
                workspace=str(context.workspace_root),
            )

            return context

        except Exception as e:
            self.logger.error(
                "workspace_creation_failed",
                run_id=str(run_id),
                error=str(e),
            )
            raise StorageError(f"Failed to create workspace: {str(e)}")

    async def cleanup_workspace(self, run_id: UUID) -> bool:
        """
        Clean up run workspace.

        Args:
            run_id: Run identifier

        Returns:
            True if cleanup succeeded
        """
        try:
            workspace_path = self.base_workspace / "runs" / str(run_id)
            if workspace_path.exists():
                import shutil

                shutil.rmtree(workspace_path)
                self.logger.info("workspace_cleaned", run_id=str(run_id))
                return True
            return False

        except Exception as e:
            self.logger.error(
                "workspace_cleanup_failed",
                run_id=str(run_id),
                error=str(e),
            )
            return False

    def get_workspace_path(self, run_id: UUID) -> Path:
        """Get workspace path for a run."""
        return self.base_workspace / "runs" / str(run_id)

    def workspace_exists(self, run_id: UUID) -> bool:
        """Check if workspace exists for run."""
        return self.get_workspace_path(run_id).exists()

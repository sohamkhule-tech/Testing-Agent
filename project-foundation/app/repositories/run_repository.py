"""
Run Repository

Data access layer for test run persistence.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict
from uuid import UUID

from app.constants import RunStatus
from app.core.interfaces import IRepository
from app.domain import RunEntity, RunMetadata
from app.exceptions import NotFoundError, StorageError
from app.logging import LoggerMixin
from app.utils import dumps, load_file, loads, save_file


class RunRepository(IRepository[RunEntity, UUID], LoggerMixin):
    """
    Repository for run persistence using JSON file storage.

    In-memory cache with file-based persistence for Phase 1.
    """

    def __init__(self, storage_dir: Path) -> None:
        """
        Initialize run repository.

        Args:
            storage_dir: Directory for run metadata storage
        """
        super().__init__()
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[UUID, RunEntity] = {}

    def _get_run_file(self, run_id: UUID) -> Path:
        """Get file path for run metadata."""
        return self.storage_dir / f"{run_id}.json"

    async def create(self, entity: RunEntity) -> RunEntity:
        """
        Create new run entity.

        Args:
            entity: Run entity to create

        Returns:
            Created entity

        Raises:
            StorageError: If creation fails
        """
        try:
            # Store in cache
            self._cache[entity.run_id] = entity

            # Persist to file
            file_path = self._get_run_file(entity.run_id)
            data = entity.model_dump(mode="json")
            await save_file(file_path, data)

            self.logger.info("run_created", run_id=str(entity.run_id))

            return entity

        except Exception as e:
            self.logger.error(
                "run_create_failed",
                run_id=str(entity.run_id),
                error=str(e),
            )
            raise StorageError(f"Failed to create run: {str(e)}")

    async def get_by_id(self, entity_id: UUID) -> RunEntity | None:
        """
        Get run by ID.

        Args:
            entity_id: Run ID

        Returns:
            Run entity or None
        """
        # Check cache first
        if entity_id in self._cache:
            return self._cache[entity_id]

        # Load from file
        try:
            file_path = self._get_run_file(entity_id)
            if not file_path.exists():
                return None

            data = await load_file(file_path)
            entity = RunEntity(**data)

            # Update cache
            self._cache[entity_id] = entity

            return entity

        except Exception as e:
            self.logger.error(
                "run_load_failed",
                run_id=str(entity_id),
                error=str(e),
            )
            return None

    async def update(self, entity: RunEntity) -> RunEntity:
        """
        Update run entity.

        Args:
            entity: Updated entity

        Returns:
            Updated entity

        Raises:
            NotFoundError: If run doesn't exist
            StorageError: If update fails
        """
        try:
            # Check existence
            if not await self.exists(entity.run_id):
                raise NotFoundError(
                    f"Run not found: {entity.run_id}",
                    resource_id=str(entity.run_id),
                )

            # Update timestamp
            entity.updated_at = datetime.utcnow()

            # Update cache
            self._cache[entity.run_id] = entity

            # Persist to file
            file_path = self._get_run_file(entity.run_id)
            data = entity.model_dump(mode="json")
            await save_file(file_path, data)

            self.logger.info("run_updated", run_id=str(entity.run_id))

            return entity

        except NotFoundError:
            raise
        except Exception as e:
            self.logger.error(
                "run_update_failed",
                run_id=str(entity.run_id),
                error=str(e),
            )
            raise StorageError(f"Failed to update run: {str(e)}")

    async def delete(self, entity_id: UUID) -> bool:
        """
        Delete run.

        Args:
            entity_id: Run ID

        Returns:
            True if deleted
        """
        try:
            # Remove from cache
            if entity_id in self._cache:
                del self._cache[entity_id]

            # Delete file
            file_path = self._get_run_file(entity_id)
            if file_path.exists():
                file_path.unlink()
                self.logger.info("run_deleted", run_id=str(entity_id))
                return True

            return False

        except Exception as e:
            self.logger.error(
                "run_delete_failed",
                run_id=str(entity_id),
                error=str(e),
            )
            return False

    async def exists(self, entity_id: UUID) -> bool:
        """Check if run exists."""
        if entity_id in self._cache:
            return True
        return self._get_run_file(entity_id).exists()

    async def get_metadata(self, run_id: UUID) -> RunMetadata | None:
        """
        Get run metadata.

        Args:
            run_id: Run identifier

        Returns:
            Run metadata or None
        """
        entity = await self.get_by_id(run_id)
        if not entity:
            return None

        return RunMetadata(
            run_id=entity.run_id,
            request_id=entity.request_id,
            requested_by=entity.requested_by,
            workspace_path=entity.workspace_path,
            created_at=entity.created_at,
            updated_at=entity.updated_at,
            status=entity.status,
            current_stage=entity.current_stage,
            progress_percent=entity.progress_percent,
            message=entity.message,
            error=entity.error,
        )

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
            stage: Optional stage update
            progress: Optional progress update
            message: Optional message update
            error: Optional error update

        Returns:
            True if updated successfully
        """
        try:
            entity = await self.get_by_id(run_id)
            if not entity:
                return False

            entity.status = status
            entity.updated_at = datetime.utcnow()

            if stage is not None:
                entity.current_stage = stage
            if progress is not None:
                entity.progress_percent = progress
            if message is not None:
                entity.message = message
            if error is not None:
                entity.error = error

            await self.update(entity)
            return True

        except Exception as e:
            self.logger.error(
                "status_update_failed",
                run_id=str(run_id),
                error=str(e),
            )
            return False

    async def list_all(self) -> list[RunEntity]:
        """List all runs, sorted by creation time descending."""
        try:
            entities = []
            for file_path in self.storage_dir.glob("*.json"):
                data = await load_file(file_path)
                entity = RunEntity(**data)
                self._cache[entity.run_id] = entity
                entities.append(entity)
            entities.sort(key=lambda r: r.created_at, reverse=True)
            return entities
        except Exception as e:
            self.logger.error("run_list_all_failed", error=str(e))
            return list(self._cache.values())

    async def list_recent(self, limit: int = 20) -> list[RunEntity]:
        """List most recent runs."""
        all_runs = await self.list_all()
        return all_runs[:limit]

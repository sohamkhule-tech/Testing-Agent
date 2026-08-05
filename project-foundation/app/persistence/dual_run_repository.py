"""
DualRunRepository

Wraps the file-based ``RunRepository`` (authoritative) and the
PostgreSQL ``PgRunRepository`` (secondary).  When dual-write is
enabled, every write goes to filesystem first, then PostgreSQL.

Filesystem is always the source of truth.  PostgreSQL failures
are logged and never propagated to the caller.
"""

from __future__ import annotations

from uuid import UUID

from app.core.interfaces import IRepository
from app.domain.run import RunEntity
from app.persistence.config import PersistenceConfig
from app.persistence.dual_base import BaseDualRepository
from app.repositories.pg_run_repository import RunRepository as PgRunRepository
from app.repositories.run_repository import RunRepository as FsRunRepository


class DualRunRepository(BaseDualRepository):
    """Dual-write repository for Run.

    Write order: filesystem → PostgreSQL.
    Failure isolation: PG failures are logged, never raised.
    """

    def __init__(
        self,
        fs_repo: FsRunRepository,
        pg_repo: PgRunRepository,
        config: PersistenceConfig | None = None,
    ) -> None:
        super().__init__(config)
        self._fs_repo = fs_repo
        self._pg_repo = pg_repo

    @property
    def fs_repo(self) -> IRepository:
        return self._fs_repo

    @property
    def pg_repo(self) -> IRepository:
        return self._pg_repo

    # ------------------------------------------------------------------
    # Write operations — filesystem first, PostgreSQL second
    # ------------------------------------------------------------------

    async def create(self, entity: RunEntity) -> RunEntity:
        result = await self._fs_create(entity)
        await self._pg_create(entity, entity_id=entity.run_id)
        return result

    async def update(self, entity: RunEntity) -> RunEntity:
        result = await self._fs_update(entity)
        await self._pg_update(entity, entity_id=entity.run_id)
        return result

    async def delete(self, entity_id: UUID) -> bool:
        result = await self._fs_delete(entity_id)
        if result:
            await self._pg_delete(entity_id)
        return result

    # ------------------------------------------------------------------
    # Read — respects ``database_read_enabled`` flag
    # ------------------------------------------------------------------

    async def get_by_id(self, entity_id: UUID) -> RunEntity | None:
        return await self._read(entity_id)

    async def exists(self, entity_id: UUID) -> bool:
        if self._cfg.database_read_enabled and self._cfg.postgres_enabled:
            return await self._pg_repo.exists(entity_id)
        return await self._fs_repo.exists(entity_id)

    # ------------------------------------------------------------------
    # Domain-specific methods — delegate to appropriate backend
    # ------------------------------------------------------------------

    async def get_by_run_id(self, run_id: UUID) -> RunEntity | None:
        if self._cfg.database_read_enabled and self._cfg.postgres_enabled:
            pg_run = await self._pg_repo.get_by_run_id(run_id)
            if pg_run is not None:
                return self._to_domain(pg_run)
            return None
        return await self._fs_repo.get_by_id(run_id)

    async def update_status(
        self,
        run_id: UUID,
        status: str,
        stage: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> bool:
        fs_result = await self._fs_repo.update_status(
            run_id, status, stage=stage, progress=progress,
            message=message, error=error,
        )
        if self._cfg.postgres_enabled and self._cfg.dual_write_enabled:
            try:
                from app.models.enums import RunStatus as DbRunStatus
                pg_status = DbRunStatus(status)
                await self._pg_repo.update_status(
                    run_id, pg_status, stage=stage, progress=progress,
                    message=message, error=error,
                )
            except Exception as exc:
                self.metrics.postgres_failures += 1
                import logging
                _log = logging.getLogger("app.persistence.dual_write")
                _log.error(
                    "pg_write_failed operation=%s entity_type=%s entity_id=%s error=%s",
                    "update_status", "run", str(run_id), exc,
                )
        return fs_result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain(pg_run: Any) -> RunEntity:
        """Convert a SQLAlchemy ``Run`` ORM model to domain ``RunEntity``."""
        return RunEntity(
            run_id=pg_run.run_id,
            request_id=pg_run.request_id,
            requested_by=getattr(pg_run, "requested_by", "system"),
            workspace_path=pg_run.workspace_path,
            status=pg_run.status.value if hasattr(pg_run.status, "value") else pg_run.status,
            current_stage=pg_run.current_stage,
            progress_percent=pg_run.progress_percent,
            message=pg_run.message,
            error=pg_run.error,
            test_run_request={},
        )

    @staticmethod
    def _to_orm(pg_run: Any) -> RunEntity:
        """Passthrough — writes always use the FS entity."""
        return pg_run

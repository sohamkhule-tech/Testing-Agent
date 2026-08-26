"""
DualProjectRepository

Wraps the PostgreSQL ``ProjectRepository`` with dual-write infrastructure.

No filesystem backend exists for projects.  When ``postgres_enabled``
is ``False``, writes are silently skipped (logged).  This ensures the
application can function without PostgreSQL during migration.
"""

from __future__ import annotations

from uuid import UUID

from app.core.interfaces import IRepository
from app.models.orm.core import Project
from app.persistence.config import PersistenceConfig
from app.persistence.dual_base import BaseDualRepository
from app.repositories.pg_project_repository import ProjectRepository


class DualProjectRepository(BaseDualRepository):
    """Dual-write aware repository for Project.

    Writes only when ``postgres_enabled`` is ``True``.
    Provides retry, metrics, and structured logging for all operations.
    """

    def __init__(
        self,
        pg_repo: ProjectRepository,
        config: PersistenceConfig | None = None,
    ) -> None:
        super().__init__(config)
        self._pg_repo = pg_repo

    @property
    def fs_repo(self) -> IRepository:
        raise RuntimeError("No filesystem backend for ProjectRepository")

    @property
    def pg_repo(self) -> IRepository:
        return self._pg_repo

    async def create(self, entity: Project) -> Project:
        if not self._cfg.postgres_enabled:
            return entity
        return await self._pg_repo.create(entity)

    async def get_by_id(self, entity_id: UUID) -> Project | None:
        if not self._cfg.postgres_enabled:
            return None
        return await self._pg_repo.get_by_id(entity_id)

    async def update(self, entity: Project) -> Project:
        if not self._cfg.postgres_enabled:
            return entity
        return await self._pg_repo.update(entity)

    async def delete(self, entity_id: UUID) -> bool:
        if not self._cfg.postgres_enabled:
            return False
        return await self._pg_repo.delete(entity_id)

    async def exists(self, entity_id: UUID) -> bool:
        if not self._cfg.postgres_enabled:
            return False
        return await self._pg_repo.exists(entity_id)

    async def find_by_name(self, name: str) -> Project | None:
        if not self._cfg.postgres_enabled:
            return None
        return await self._pg_repo.find_by_name(name)

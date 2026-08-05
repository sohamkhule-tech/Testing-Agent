"""
Project Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.orm.core import Project
from app.repositories.base import BaseRepository


class ProjectRepository(BaseRepository[Project]):
    model_class = Project

    async def find_by_name(self, name: str) -> Project | None:
        stmt = select(Project).where(Project.name == name)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.deleted_at.is_(None))
            .order_by(Project.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_environment(self, environment: str) -> list[Project]:
        stmt = (
            select(Project)
            .where(Project.environment == environment)
            .order_by(Project.name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_runs(self, project_id: UUID) -> Project | None:
        stmt = (
            select(Project)
            .options(selectinload(Project.runs))
            .where(Project.id == project_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

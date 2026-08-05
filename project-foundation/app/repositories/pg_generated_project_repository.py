"""
GeneratedProject Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.generation import GeneratedProject
from app.repositories.base import BaseRepository


class GeneratedProjectRepository(BaseRepository[GeneratedProject]):
    model_class = GeneratedProject

    async def get_by_run_id(self, run_id: UUID) -> GeneratedProject | None:
        stmt = select(GeneratedProject).where(GeneratedProject.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[GeneratedProject]:
        stmt = (
            select(GeneratedProject)
            .where(GeneratedProject.deleted_at.is_(None))
            .order_by(GeneratedProject.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

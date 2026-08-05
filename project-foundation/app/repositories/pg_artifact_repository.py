"""
Artifact Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.system import Artifact
from app.repositories.base import BaseRepository


class ArtifactRepository(BaseRepository[Artifact]):
    model_class = Artifact

    async def list_by_run_id(self, run_id: UUID) -> list[Artifact]:
        stmt = (
            select(Artifact)
            .where(Artifact.run_id == run_id)
            .order_by(Artifact.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_type(self, artifact_type: str, *, offset: int = 0, limit: int = 50) -> list[Artifact]:
        stmt = (
            select(Artifact)
            .where(Artifact.artifact_type == artifact_type)
            .order_by(Artifact.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_execution_id(self, execution_id: UUID) -> list[Artifact]:
        stmt = (
            select(Artifact)
            .where(Artifact.execution_id == execution_id)
            .order_by(Artifact.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

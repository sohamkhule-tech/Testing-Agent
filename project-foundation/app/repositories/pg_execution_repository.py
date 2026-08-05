"""
Execution Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.execution import Execution
from app.repositories.base import BaseRepository


class ExecutionRepository(BaseRepository[Execution]):
    model_class = Execution

    async def get_by_run_id(self, run_id: UUID) -> Execution | None:
        stmt = select(Execution).where(Execution.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def latest_execution(self, project_id: UUID) -> Execution | None:
        stmt = (
            select(Execution)
            .where(Execution.project_id == project_id)
            .order_by(Execution.created_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_status(self, status: str, *, offset: int = 0, limit: int = 20) -> list[Execution]:
        stmt = (
            select(Execution)
            .where(Execution.status == status)
            .order_by(Execution.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, *, limit: int = 20) -> list[Execution]:
        stmt = (
            select(Execution)
            .order_by(Execution.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

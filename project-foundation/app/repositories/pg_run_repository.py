"""
Run Repository (PostgreSQL)
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.enums import RunStatus
from app.models.orm.core import Run
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[Run]):
    model_class = Run

    async def get_by_run_id(self, run_id: UUID) -> Run | None:
        stmt = select(Run).where(Run.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_status(self, status: RunStatus, *, offset: int = 0, limit: int = 20) -> list[Run]:
        stmt = (
            select(Run)
            .where(Run.status == status.value)
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_active(self, *, offset: int = 0, limit: int = 20) -> list[Run]:
        stmt = (
            select(Run)
            .where(Run.status.in_(["pending", "running"]))
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_project(
        self, project_id: UUID, *, offset: int = 0, limit: int = 20
    ) -> list[Run]:
        stmt = (
            select(Run)
            .where(Run.project_id == project_id)
            .order_by(Run.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_recent(self, *, limit: int = 20) -> list[Run]:
        stmt = (
            select(Run)
            .order_by(Run.created_at.desc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        run_id: UUID,
        status: RunStatus,
        stage: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> bool:
        values: dict = {"status": status.value, "updated_at": datetime.utcnow()}
        if stage is not None:
            values["current_stage"] = stage
        if progress is not None:
            values["progress_percent"] = progress
        if message is not None:
            values["message"] = message
        if error is not None:
            values["error"] = error
        stmt = update(Run).where(Run.id == run_id).values(**values)
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount > 0

    async def get_with_children(self, run_id: UUID) -> Run | None:
        stmt = (
            select(Run)
            .options(
                selectinload(Run.crawl_packages),
                selectinload(Run.inventories),
                selectinload(Run.test_plans),
                selectinload(Run.human_reviews),
                selectinload(Run.ir_documents),
                selectinload(Run.generated_projects),
                selectinload(Run.executions),
            )
            .where(Run.id == run_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

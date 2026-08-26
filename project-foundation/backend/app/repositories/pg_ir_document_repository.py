"""
IRDocument Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.generation import IRDocument
from app.repositories.base import BaseRepository


class IRDocumentRepository(BaseRepository[IRDocument]):
    model_class = IRDocument

    async def latest_version(self, test_plan_id: UUID) -> IRDocument | None:
        stmt = (
            select(IRDocument)
            .where(IRDocument.test_plan_id == test_plan_id)
            .where(IRDocument.is_latest.is_(True))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_run_id(self, run_id: UUID) -> list[IRDocument]:
        stmt = (
            select(IRDocument)
            .where(IRDocument.run_id == run_id)
            .order_by(IRDocument.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

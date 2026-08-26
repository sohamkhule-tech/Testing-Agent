"""
HumanReview Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.design import HumanReview
from app.repositories.base import BaseRepository


class HumanReviewRepository(BaseRepository[HumanReview]):
    model_class = HumanReview

    async def latest_review(self, run_id: UUID) -> HumanReview | None:
        stmt = (
            select(HumanReview)
            .where(HumanReview.run_id == run_id)
            .order_by(HumanReview.version.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_run_id(self, run_id: UUID) -> list[HumanReview]:
        stmt = (
            select(HumanReview)
            .where(HumanReview.run_id == run_id)
            .order_by(HumanReview.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_status(self, status: str) -> list[HumanReview]:
        stmt = (
            select(HumanReview)
            .where(HumanReview.status == status)
            .order_by(HumanReview.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

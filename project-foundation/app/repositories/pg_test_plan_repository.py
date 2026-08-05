"""
TestPlan Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.orm.design import TestPlan
from app.repositories.base import BaseRepository


class TestPlanRepository(BaseRepository[TestPlan]):
    model_class = TestPlan

    async def latest_version(self, run_id: UUID) -> TestPlan | None:
        stmt = (
            select(TestPlan)
            .where(TestPlan.run_id == run_id)
            .where(TestPlan.is_latest.is_(True))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_run_id(self, run_id: UUID) -> list[TestPlan]:
        stmt = (
            select(TestPlan)
            .where(TestPlan.run_id == run_id)
            .order_by(TestPlan.version.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_scenarios(self, plan_id: UUID) -> TestPlan | None:
        stmt = (
            select(TestPlan)
            .options(selectinload(TestPlan.scenarios))
            .where(TestPlan.id == plan_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

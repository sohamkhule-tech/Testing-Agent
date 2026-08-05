"""
TestResult Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.orm.execution import TestResult
from app.repositories.base import BaseRepository


class TestResultRepository(BaseRepository[TestResult]):
    model_class = TestResult

    async def list_by_execution_id(self, execution_id: UUID) -> list[TestResult]:
        stmt = (
            select(TestResult)
            .where(TestResult.execution_id == execution_id)
            .order_by(TestResult.title)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_failed(self, execution_id: UUID) -> list[TestResult]:
        stmt = (
            select(TestResult)
            .where(TestResult.execution_id == execution_id)
            .where(TestResult.status == "failed")
            .order_by(TestResult.duration_ms.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_flaky(self, execution_id: UUID) -> list[TestResult]:
        stmt = (
            select(TestResult)
            .where(TestResult.execution_id == execution_id)
            .where(TestResult.was_retried.is_(True))
            .order_by(TestResult.title)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

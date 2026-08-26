"""
CrawlPackage Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.discovery import CrawlPackage
from app.repositories.base import BaseRepository


class CrawlPackageRepository(BaseRepository[CrawlPackage]):
    model_class = CrawlPackage

    async def get_by_run_id(self, run_id: UUID) -> CrawlPackage | None:
        stmt = select(CrawlPackage).where(CrawlPackage.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

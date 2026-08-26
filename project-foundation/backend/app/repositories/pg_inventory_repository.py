"""
Inventory Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select

from app.models.orm.discovery import Inventory
from app.repositories.base import BaseRepository


class InventoryRepository(BaseRepository[Inventory]):
    model_class = Inventory

    async def get_by_run_id(self, run_id: UUID) -> Inventory | None:
        stmt = select(Inventory).where(Inventory.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

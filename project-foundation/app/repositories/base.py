"""
Base Repository for SQLAlchemy 2.x

Provides common CRUD operations for all domain repositories.
Each concrete repository extends this class and adds domain methods.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.interfaces import IRepository
from app.infrastructure.database import Base

T = TypeVar("T", bound=Base)


class BaseRepository(IRepository[T, UUID]):
    """Abstract base implementing CRUD for any SQLAlchemy ORM model.

    Usage::

        class UserRepository(BaseRepository[User]):
            model_class = User

            async def find_by_email(self, email: str) -> User | None:
                ...

    **Contract:**

    * Receives ``AsyncSession`` via constructor injection.
    * Never calls ``commit()``, ``rollback()``, or ``close()``.
    * Never creates its own session.
    * Raises on constraint violations — caller wraps in a transaction.
    """

    model_class: type[T]

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------
    # IRepository implementation
    # ------------------------------------------------------------------

    async def create(self, entity: T) -> T:
        """Add a new ORM entity to the session (caller must commit)."""
        self.session.add(entity)
        await self.session.flush()
        await self.session.refresh(entity)
        return entity

    async def get_by_id(self, entity_id: UUID) -> T | None:
        """Fetch an entity by UUID primary key."""
        stmt = select(self.model_class).where(self.model_class.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, entity: T) -> T:
        """Merge a detached entity into the session (caller must commit)."""
        merged = await self.session.merge(entity)
        await self.session.flush()
        return merged

    async def delete(self, entity_id: UUID) -> bool:
        """Delete by UUID primary key. Returns True if a row was removed."""
        entity = await self.get_by_id(entity_id)
        if entity is None:
            return False
        await self.session.delete(entity)
        await self.session.flush()
        return True

    async def exists(self, entity_id: UUID) -> bool:
        """Return True if a row with the given UUID exists."""
        stmt = select(self.model_class.id).where(self.model_class.id == entity_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none() is not None

    # ------------------------------------------------------------------
    # Paginated listing
    # ------------------------------------------------------------------

    async def list(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
        order_by: Any | None = None,
    ) -> list[T]:
        """Return a paginated list of all rows."""
        stmt = select(self.model_class)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        stmt = stmt.offset(offset).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

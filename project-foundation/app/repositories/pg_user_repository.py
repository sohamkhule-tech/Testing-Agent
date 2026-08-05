"""
User Repository
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.enums import UserStatus
from app.models.orm.core import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model_class = User

    async def find_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_active(self) -> list[User]:
        stmt = (
            select(User)
            .where(User.status == UserStatus.ACTIVE.value)
            .where(User.deleted_at.is_(None))
            .order_by(User.display_name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_role(self, role: str) -> list[User]:
        stmt = (
            select(User)
            .where(User.role == role)
            .order_by(User.display_name)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_with_projects(self, user_id: UUID) -> User | None:
        stmt = (
            select(User)
            .options(selectinload(User.projects_created))
            .where(User.id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

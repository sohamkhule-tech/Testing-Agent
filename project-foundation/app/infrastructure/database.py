"""
Database Infrastructure Module

Async SQLAlchemy engine, session management, health check,
DeclarativeBase with naming convention, and ORM utilities.

This module provides the foundation for PostgreSQL persistence.
No business logic, no repositories, no models.

Uses standard ``logging.getLogger`` to avoid triggering the full
FastAPI application import chain.  At runtime the structlog framework
(configured in ``app.logging.config``) automatically patches and
formats these log records as structured JSON.
"""

import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, MetaData, text
from sqlalchemy.dialects.postgresql import UUID as SA_UUID
from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

# ---------------------------------------------------------------------------
# Naming convention — applied to all constraints and indexes
# ---------------------------------------------------------------------------

CONVENTION: dict[str, str] = {
    "ix": "%(column_0_label)s_idx",
    "uq": "%(table_name)s_%(column_0_name)s_key",
    "ck": "%(table_name)s_%(constraint_name)s_check",
    "fk": "%(table_name)s_%(column_0_name)s_fkey",
    "pk": "%(table_name)s_pkey",
}

metadata = MetaData(naming_convention=CONVENTION)


# ---------------------------------------------------------------------------
# Engine (lazy singleton)
# ---------------------------------------------------------------------------

_engine: AsyncEngine | None = None
_async_session_factory: async_sessionmaker[AsyncSession] | None = None


def _mask_url(url: str) -> str:
    """Return a sanitised version of the connection URL for logging."""
    if "@" in url:
        userinfo, rest = url.split("@", 1)
        scheme, _, _ = userinfo.partition("://")
        return f"{scheme}://****:****@{rest}"
    return url


def get_engine() -> AsyncEngine:
    """Return the singleton ``AsyncEngine``, creating it if necessary."""
    global _engine
    if _engine is None:
        from app.config import get_settings as _get_settings

        settings = _get_settings().database
        _engine = create_async_engine(
            settings.url,
            pool_size=settings.pool_size,
            max_overflow=settings.max_overflow,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=settings.echo,
            connect_args={
                "timeout": settings.connect_timeout,
                "command_timeout": settings.connect_timeout,
            },
        )
    return _engine


async def close_engine() -> None:
    """Dispose of the engine and release all connections."""
    global _engine, _async_session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_factory = None


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the singleton ``async_sessionmaker``."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _async_session_factory


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


@asynccontextmanager
async def get_async_session() -> AsyncIterator[AsyncSession]:
    """Context manager yielding a session with automatic commit/rollback.

    Usage inside service layer::

        async with get_async_session() as session:
            repo = SomeRepository(session)
            entity = await repo.create(...)
            # commits on success, rolls back on exception

    Read-only transactions also go through this — the final commit is a no-op.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency — one session per request.

    Usage::

        @router.get("/runs")
        async def list_runs(db: AsyncSession = Depends(get_db_session)): ...

    The caller (service or route handler) is responsible for
    calling ``commit()`` / ``rollback()``.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------


async def check_database_health() -> dict[str, Any]:
    """Execute ``SELECT 1`` and return a status dictionary.

    Returns (not an HTTP response)::

        {
            "status": "healthy" | "unhealthy",
            "latency_ms": float,
            "error": str | None,
        }
    """
    start = time.monotonic()
    try:
        async with get_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
            elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "healthy", "latency_ms": elapsed_ms, "error": None}
    except Exception as exc:
        elapsed_ms = round((time.monotonic() - start) * 1000, 2)
        return {"status": "unhealthy", "latency_ms": elapsed_ms, "error": str(exc)}


# ---------------------------------------------------------------------------
# ORM Base
# ---------------------------------------------------------------------------


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base for all ORM models.

    Inherits ``AsyncAttrs`` for awaitable relationship access and
    applies the project-wide naming convention to all constraints.
    """

    metadata = metadata

    __allow_unmapped__ = False

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: ANN206
        """Derive table name from class name (snake_case plural).

        ``UserProfile`` → ``user_profiles``.

        Override on any model that needs a custom table name.
        """
        name = re.sub(r"(?<=[a-z])(?=[A-Z])", "_", cls.__name__).lower()
        return f"{name}s"

    type_annotation_map = {
        UUID: SA_UUID(as_uuid=True),
        datetime: DateTime(timezone=True),
    }


# ---------------------------------------------------------------------------
# Reusable mixins
# ---------------------------------------------------------------------------


class UUIDMixin:
    """Add a UUID primary key column named ``id``."""

    id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )


class TimestampMixin:
    """Add ``created_at`` and ``updated_at`` columns.

    ``updated_at`` is refreshed automatically on row update.
    """

    created_at: Mapped[datetime] = mapped_column(
        server_default=text("NOW()"),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=True,
    )

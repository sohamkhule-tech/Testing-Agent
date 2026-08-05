"""
Persistence Configuration

Single source of truth for persistence strategy decisions.
Reads feature flags from ``PersistenceSettings`` and exposes them
as a frozen configuration object.

Feature flags (all default to ``False`` — filesystem remains primary):

    filesystem_enabled
        When ``True`` the filesystem backend is active.
        Should remain ``True`` until migration is fully complete.

    postgres_enabled
        When ``True`` the PostgreSQL backend is active.
        Set to ``True`` once the database is created and repositories
        have been wired into services.

    dual_write_enabled
        When ``True`` writes go to both filesystem and PostgreSQL.
        The filesystem write is authoritative; the DB write is
        fire-and-forget (errors are logged, not raised).

    database_read_enabled
        When ``True`` read queries use PostgreSQL instead of filesystem.
        Requires ``postgres_enabled`` to also be ``True``.

Usage::

    from app.persistence import persistence_config

    if persistence_config.database_read_enabled:
        result = await db_repo.find(...)
    else:
        result = await fs_repo.find(...)
"""

from __future__ import annotations

from functools import lru_cache

from app.config import get_settings


class PersistenceConfig:
    """Central persistence configuration.

    Immutable after construction.  All attributes are plain booleans.
    """

    def __init__(self) -> None:
        settings = get_settings().persistence
        self.filesystem_enabled: bool = settings.filesystem_enabled
        self.postgres_enabled: bool = settings.postgres_enabled
        self.dual_write_enabled: bool = settings.dual_write_enabled
        self.database_read_enabled: bool = settings.database_read_enabled

    def __repr__(self) -> str:
        return (
            f"PersistenceConfig("
            f"filesystem={self.filesystem_enabled}, "
            f"postgres={self.postgres_enabled}, "
            f"dual_write={self.dual_write_enabled}, "
            f"db_read={self.database_read_enabled})"
        )


@lru_cache()
def get_persistence_config() -> PersistenceConfig:
    """Return a cached ``PersistenceConfig`` singleton."""
    return PersistenceConfig()


persistence_config = get_persistence_config()

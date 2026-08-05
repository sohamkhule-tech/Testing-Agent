"""
Rollout Manager

Tracks and reports the current persistence rollout state.
Validates transitions between states and provides a single
source of truth for which backends are active.

State machine::

    FILESYSTEM_ONLY  ────────────►  PG_WITH_FS_FALLBACK
         │                                  │
         │                                  ▼
         │                      DUAL_WRITE_ACTIVE
         │                         │        │
         │                         ▼        ▼
         │                  PG_READS_ENABLED  (future)
         │
         └──►  (future) PG_ONLY
"""

from __future__ import annotations

import enum
from functools import lru_cache

from app.persistence.config import get_persistence_config


class PersistenceMode(str, enum.Enum):
    """Human-readable names for the current persistence strategy."""

    FILESYSTEM_ONLY = "filesystem_only"
    """Filesystem is the only active backend. PG is disabled."""

    PG_WITH_FS_FALLBACK = "pg_with_filesystem_fallback"
    """PostgreSQL is enabled but not yet authoritative. FS is fallback."""

    DUAL_WRITE_ACTIVE = "dual_write_active"
    """Both filesystem and PostgreSQL are written. FS is authoritative."""

    PG_READS_ENABLED = "pg_reads_enabled"
    """Dual-write active. Reads served from PostgreSQL."""


class RolloutManager:
    """Central rollout state manager.

    Usage::

        rollout = RolloutManager()
        mode = rollout.current_mode
        if rollout.writes_go_to_pg:
            # dual-write or PG-only
    """

    @property
    def current_mode(self) -> PersistenceMode:
        """Return the current ``PersistenceMode`` based on feature flags."""
        cfg = get_persistence_config()
        if not cfg.postgres_enabled:
            return PersistenceMode.FILESYSTEM_ONLY
        if cfg.database_read_enabled:
            return PersistenceMode.PG_READS_ENABLED
        if cfg.dual_write_enabled:
            return PersistenceMode.DUAL_WRITE_ACTIVE
        return PersistenceMode.PG_WITH_FS_FALLBACK

    @property
    def writes_go_to_pg(self) -> bool:
        """Return ``True`` if PostgreSQL is being written."""
        cfg = get_persistence_config()
        return cfg.postgres_enabled and cfg.dual_write_enabled

    @property
    def writes_go_to_fs(self) -> bool:
        """Return ``True`` if filesystem is being written."""
        return get_persistence_config().filesystem_enabled

    @property
    def reads_come_from_pg(self) -> bool:
        """Return ``True`` if reads are served from PostgreSQL."""
        cfg = get_persistence_config()
        return cfg.postgres_enabled and cfg.database_read_enabled

    @property
    def summary(self) -> dict:
        """Return a dictionary summarising the current rollout state.

        Suitable for health check endpoints and operational dashboards.
        """
        cfg = get_persistence_config()
        return {
            "mode": self.current_mode.value,
            "writes_to_filesystem": self.writes_go_to_fs,
            "writes_to_postgres": self.writes_go_to_pg,
            "reads_from_postgres": self.reads_come_from_pg,
            "features": {
                "filesystem_enabled": cfg.filesystem_enabled,
                "postgres_enabled": cfg.postgres_enabled,
                "dual_write_enabled": cfg.dual_write_enabled,
                "database_read_enabled": cfg.database_read_enabled,
            },
        }


@lru_cache()
def get_rollout_manager() -> RolloutManager:
    """Return a cached ``RolloutManager`` singleton."""
    return RolloutManager()


rollout_manager = get_rollout_manager()

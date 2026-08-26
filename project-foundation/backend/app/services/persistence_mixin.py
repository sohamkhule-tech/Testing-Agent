"""
PersistenceAware Mixin

Adds persistence awareness to any service without changing its interface.

When mixed into a service, it provides:

* ``persistence_config`` — feature flags (``PersistenceConfig`` instance)
* ``dual_run_repository`` — ``DualRunRepository`` (lazy, FS + PG backends)
* ``log_persistence_status()`` — structured log of current backend selection

The mixin is additive — it does NOT change the service's constructor,
does NOT override ``self.repository``, and does NOT activate PostgreSQL.
All flags default to ``False``, preserving existing filesystem-only behavior.
"""

from __future__ import annotations

import logging
from functools import cached_property

from app.persistence.config import get_persistence_config
from app.persistence.dual_run_repository import DualRunRepository
from app.repositories.pg_run_repository import RunRepository as PgRunRepository
from app.repositories.run_repository import RunRepository as FsRunRepository

logger = logging.getLogger("app.services.persistence")


class PersistenceAware:
    """Mixin that adds persistence-awareness to a service.

    Usage::

        class TriggerService(IService, LoggerMixin, PersistenceAware):
            ...
            async def create_run(self, ...):
                self.log_persistence_status("create_run")
                # self.repository (file-based) is still the default
                # self.dual_run_repository is available when flags permit
    """

    # ------------------------------------------------------------------
    # Feature flags
    # ------------------------------------------------------------------

    @cached_property
    def persistence_config(self):
        """Return the cached ``PersistenceConfig`` singleton."""
        return get_persistence_config()

    # ------------------------------------------------------------------
    # Dual-write repository (lazy)
    # ------------------------------------------------------------------

    @cached_property
    def dual_run_repository(self) -> DualRunRepository | None:
        """Return a ``DualRunRepository`` or ``None`` if flags forbid it.

        The dual repository wraps the file-based ``RunRepository``
        (authoritative) and the PostgreSQL ``PgRunRepository``
        (secondary).  It is only created when ``postgres_enabled``
        is ``True``.
        """
        cfg = self.persistence_config
        if not cfg.postgres_enabled:
            return None
        # Build FS repo using the same storage path logic as dependencies.py
        from pathlib import Path
        from app.config import get_settings
        settings = get_settings()
        storage_dir = Path(settings.storage.storage_base_path) / "runs" / "metadata"
        storage_dir.mkdir(parents=True, exist_ok=True)
        fs_repo = FsRunRepository(storage_dir=storage_dir)

        # Build PG repo — requires a session (provided at call time)
        # For now, create a placeholder — the actual PG repo is created
        # by the caller when they have a session available.
        # The DualRunRepository handles the "no session = no PG write" case.
        pg_repo = PgRunRepository.__new__(PgRunRepository)

        return DualRunRepository(fs_repo=fs_repo, pg_repo=pg_repo, config=cfg)

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_persistence_status(self, operation: str) -> None:
        """Log the current persistence backend selection.

        Call this at the start of any service method that touches data.
        """
        cfg = self.persistence_config
        if cfg.dual_write_enabled:
            logger.info(
                "persistence dual_write operation=%s fs=%s pg=%s",
                operation, cfg.filesystem_enabled, cfg.postgres_enabled,
            )
        elif cfg.postgres_enabled:
            logger.info(
                "persistence postgres operation=%s",
                operation,
            )
        else:
            logger.debug(
                "persistence filesystem operation=%s",
                operation,
            )

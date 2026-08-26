"""
Dual-Write Base Infrastructure

Components
----------
PostgresRetryPolicy
    Retry strategy for transient PostgreSQL errors.
    Exponential backoff with jitter.  3 retries max.

DualWriteMetrics
    Thread-safe counters for monitoring dual-write health.

BaseDualRepository
    Abstract base that all dual-write repositories extend.
    Provides shared logic for:
    * Feature flag checks (filesystem_enabled, postgres_enabled, dual_write_enabled)
    * Write ordering (filesystem first, PostgreSQL second)
    * Failure isolation (PG failures never affect FS outcome)
    * Logging (structured, per-operation)
    * Metrics (counters, latency)
    * Retry (transient PG errors only)
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.core.interfaces import IRepository
from app.domain.run import RunEntity
from app.persistence.config import PersistenceConfig, get_persistence_config

logger = logging.getLogger("app.persistence.dual_write")


# ===================================================================
# Retry Policy
# ===================================================================

TRANSIENT_PG_CODES = frozenset({
    "40001",  # serialization_failure
    "40P01",  # deadlock_detected
    "08000",  # connection_exception
    "08003",  # connection_does_not_exist
    "08006",  # connection_failure
    "08001",  # sqlclient_unable_to_establish_sqlconnection
    "08004",  # sqlserver_rejected_establishment_of_sqlconnection
    "53300",  # too_many_connections
    "53400",  # configuration_limit_exceeded
    "57P03",  # cannot_connect_now
})


def _is_transient_pg_error(exc: Exception) -> bool:
    """Return ``True`` if *exc* is a transient PostgreSQL error."""
    exc_repr = f"{type(exc).__name__}: {exc}"
    for code in TRANSIENT_PG_CODES:
        if code in exc_repr:
            return True
    # Connection / timeout errors from asyncpg are also transient
    msg = str(exc).lower()
    transient_keywords = [
        "connection", "timeout", "reset", "closed", "refused",
        "temporarily", "unavailable", "too many connections",
    ]
    return any(kw in msg for kw in transient_keywords)


class PostgresRetryPolicy:
    """Exponential backoff retry for transient PostgreSQL errors.

    Args:
        max_retries: Maximum retry attempts (default 3).
        base_delay: Initial delay in seconds (default 0.1).
        max_delay: Maximum delay in seconds (default 2.0).
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 0.1,
        max_delay: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute(self, operation: str, fn: Any) -> tuple[Any, int, float]:
        """Execute *fn* with retry.

        ``fn`` must be a callable that returns a coroutine when invoked,
        e.g. ``lambda: repo.create(entity)``.  This ensures a fresh
        coroutine is created for each retry attempt.

        Returns:
            Tuple of (result, attempts_made, total_latency_ms).
        """
        last_exc: Exception | None = None
        attempts = 0
        start = time.monotonic()

        for attempt in range(1, self.max_retries + 1):
            attempts = attempt
            try:
                result = await fn()
                elapsed_ms = (time.monotonic() - start) * 1000
                return result, attempts, elapsed_ms
            except Exception as exc:
                last_exc = exc
                if not _is_transient_pg_error(exc):
                    # Non-transient — do not retry
                    elapsed_ms = (time.monotonic() - start) * 1000
                    raise

                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.05),
                        self.max_delay,
                    )
                    logger.warning(
                        "pg_retry operation=%s attempt=%s delay_ms=%s error=%s",
                        operation, attempt, round(delay * 1000), exc,
                    )
                    await asyncio.sleep(delay)

        # All retries exhausted
        elapsed_ms = (time.monotonic() - start) * 1000
        logger.error(
            "pg_retry_exhausted operation=%s attempts=%s error=%s",
            operation, attempts, last_exc,
        )
        raise last_exc  # type: ignore[misc]


# ===================================================================
# Metrics
# ===================================================================


@dataclass
class DualWriteMetrics:
    """Thread-safe counters for dual-write operations.

    Not thread-safe by default — designed for single-threaded async use.
    For multi-worker scenarios, aggregate via structured logs / metrics backend.
    """

    filesystem_writes: int = 0
    postgres_writes: int = 0
    postgres_failures: int = 0
    postgres_retries: int = 0
    total_pg_latency_ms: float = 0.0
    filesystem_failures: int = 0

    def snapshot(self) -> dict[str, Any]:
        return {
            "filesystem_writes": self.filesystem_writes,
            "postgres_writes": self.postgres_writes,
            "postgres_failures": self.postgres_failures,
            "postgres_retries": self.postgres_retries,
            "total_pg_latency_ms": round(self.total_pg_latency_ms, 2),
            "filesystem_failures": self.filesystem_failures,
        }


# ===================================================================
# Base Dual Repository
# ===================================================================


class BaseDualRepository:
    """Shared dual-write logic for aggregate-root repositories.

    Subclasses override ``_fs_repo`` and ``_pg_repo`` properties
    and implement read methods.
    """

    def __init__(
        self,
        config: PersistenceConfig | None = None,
    ) -> None:
        self._cfg = config or get_persistence_config()
        self.metrics = DualWriteMetrics()
        self._retry = PostgresRetryPolicy()

    # ------------------------------------------------------------------
    # Write helpers (used by subclasses)
    # ------------------------------------------------------------------

    async def _fs_create(self, entity: Any) -> Any:
        """Write to filesystem (authoritative). Returns result or raises."""
        try:
            result = await self.fs_repo.create(entity)
            self.metrics.filesystem_writes += 1
            return result
        except Exception:
            self.metrics.filesystem_failures += 1
            raise

    async def _pg_create(self, entity: Any, entity_id: UUID | None = None) -> Any:
        """Write to PostgreSQL (secondary). Never raises on failure."""
        if not self._cfg.postgres_enabled or not self._cfg.dual_write_enabled:
            return None
        try:
            result, attempts, latency = await self._retry.execute(
                "create", lambda: self.pg_repo.create(entity)
            )
            self.metrics.postgres_writes += 1
            self.metrics.postgres_retries += attempts - 1
            self.metrics.total_pg_latency_ms += latency
            return result
        except Exception as exc:
            self.metrics.postgres_failures += 1
            logger.error(
                "pg_write_failed operation=%s entity_type=%s entity_id=%s error=%s",
                "create", self._entity_name(),
                str(entity_id) if entity_id else "unknown", exc,
            )
            return None

    async def _fs_update(self, entity: Any) -> Any:
        try:
            result = await self.fs_repo.update(entity)
            self.metrics.filesystem_writes += 1
            return result
        except Exception:
            self.metrics.filesystem_failures += 1
            raise

    async def _pg_update(self, entity: Any, entity_id: UUID | None = None) -> Any:
        if not self._cfg.postgres_enabled or not self._cfg.dual_write_enabled:
            return None
        try:
            result, attempts, latency = await self._retry.execute(
                "update", lambda: self.pg_repo.update(entity)
            )
            self.metrics.postgres_writes += 1
            self.metrics.postgres_retries += attempts - 1
            self.metrics.total_pg_latency_ms += latency
            return result
        except Exception as exc:
            self.metrics.postgres_failures += 1
            logger.error(
                "pg_write_failed operation=%s entity_type=%s entity_id=%s error=%s",
                "update", self._entity_name(),
                str(entity_id) if entity_id else "unknown", exc,
            )
            return None

    async def _fs_delete(self, entity_id: UUID) -> bool:
        try:
            result = await self.fs_repo.delete(entity_id)
            if result:
                self.metrics.filesystem_writes += 1
            return result
        except Exception:
            self.metrics.filesystem_failures += 1
            raise

    async def _pg_delete(self, entity_id: UUID) -> None:
        if not self._cfg.postgres_enabled or not self._cfg.dual_write_enabled:
            return
        try:
            _, attempts, latency = await self._retry.execute(
                "delete", lambda: self.pg_repo.delete(entity_id)
            )
            self.metrics.postgres_writes += 1
            self.metrics.postgres_retries += attempts - 1
            self.metrics.total_pg_latency_ms += latency
        except Exception as exc:
            self.metrics.postgres_failures += 1
            logger.error(
                "pg_write_failed operation=%s entity_type=%s entity_id=%s error=%s",
                "delete", self._entity_name(), str(entity_id), exc,
            )

    # ------------------------------------------------------------------
    # Read — respects ``database_read_enabled``
    # ------------------------------------------------------------------

    async def _read(self, entity_id: UUID, *, default: Any = None) -> Any:
        """Read from FS or PG based on ``database_read_enabled`` flag."""
        if self._cfg.database_read_enabled and self._cfg.postgres_enabled:
            result = await self.pg_repo.get_by_id(entity_id)
            return result if result is not None else default
        return await self.fs_repo.get_by_id(entity_id) or default

    # ------------------------------------------------------------------
    # Abstract — subclasses must provide
    # ------------------------------------------------------------------

    @property
    def fs_repo(self) -> IRepository:
        raise NotImplementedError

    @property
    def pg_repo(self) -> IRepository:
        raise NotImplementedError

    def _entity_name(self) -> str:
        return type(self).__name__.replace("Dual", "").replace("Repository", "").lower()

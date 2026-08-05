"""
Performance benchmarks for the persistence layer.

These tests measure latency and throughput of basic operations.
They serve as baselines, not strict pass/fail gates.
"""

import asyncio
import time

import pytest
from sqlalchemy import text

from tests.helpers.persistence import make_audit_log

pytestmark = [pytest.mark.asyncio, pytest.mark.slow]


class TestBasicLatency:
    """Measure single-operation latency for key repositories."""

    @pytest.mark.parametrize("count", [10, 50])
    async def test_bulk_audit_log_insert(self, db_session, count):
        """Time inserting N audit log entries."""
        start = time.monotonic()
        for _ in range(count):
            al = make_audit_log()
            db_session.add(al)
        await db_session.flush()
        elapsed = time.monotonic() - start
        ops_per_sec = count / elapsed if elapsed > 0 else float("inf")
        print(f"\n  Audit log inserts: {count} in {elapsed:.3f}s ({ops_per_sec:.0f} ops/s)")
        # No hard threshold — just a benchmark baseline

    @pytest.mark.parametrize("count", [10, 50])
    async def test_simple_select(self, db_session, count):
        """Time repeated simple SELECT 1 queries."""
        start = time.monotonic()
        for _ in range(count):
            await db_session.execute(text("SELECT 1"))
        elapsed = time.monotonic() - start
        ops_per_sec = count / elapsed if elapsed > 0 else float("inf")
        print(f"\n  Simple SELECT: {count} in {elapsed:.3f}s ({ops_per_sec:.0f} qps)")


class TestConcurrentOperations:
    """Measure throughput under concurrent load."""

    @pytest.mark.parametrize("concurrency", [5, 10])
    async def test_concurrent_select(self, db_session, concurrency):
        """Run concurrent SELECT queries."""
        async def select_one():
            await db_session.execute(text("SELECT 1"))

        start = time.monotonic()
        tasks = [select_one() for _ in range(concurrency)]
        await asyncio.gather(*tasks)
        elapsed = time.monotonic() - start
        print(f"\n  Concurrent SELECT ({concurrency}): {elapsed:.3f}s")


class TestConnectionPool:
    """Verify connection pool does not exhaust under load."""

    async def test_pool_returns_connections(self):
        """Repeated session creation should not leak connections."""
        from app.infrastructure.database import get_session_factory
        factory = get_session_factory()

        sessions = []
        for _ in range(5):
            sess = factory()
            await sess.execute(text("SELECT 1"))
            sessions.append(sess)

        # Close all
        for s in sessions:
            await s.close()

    async def test_pool_health(self):
        """Engine pool should report healthy statistics."""
        from app.infrastructure.database import get_engine
        engine = get_engine()
        pool = engine.pool
        assert pool is not None
        # Just verify pool exists and is functioning
        assert pool.total() > 0

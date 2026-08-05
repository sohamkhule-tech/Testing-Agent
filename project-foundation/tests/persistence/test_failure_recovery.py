"""
Failure recovery tests for the persistence layer.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.asyncio


class TestDatabaseUnavailable:
    async def test_connection_refused_raises(self):
        bad_engine = create_async_engine(
            "postgresql+asyncpg://user:pass@localhost:15432/nonexistent",
            pool_size=1, max_overflow=0,
        )
        with pytest.raises(Exception):
            async with bad_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        await bad_engine.dispose()

    async def test_health_check_returns_status(self):
        from app.infrastructure.database import check_database_health
        result = await check_database_health()
        assert "status" in result
        assert "latency_ms" in result


class TestSessionCleanup:
    async def test_session_close_does_not_raise(self, db_session):
        await db_session.close()
        await db_session.close()

    async def test_session_rollback_after_error(self, db_session):
        try:
            await db_session.execute(text("INVALID SQL"))
        except Exception:
            await db_session.rollback()
        result = await db_session.execute(text("SELECT 1"))
        assert result.scalar() == 1


class TestRetryOnTransientErrors:
    async def test_retry_eventually_succeeds(self):
        from app.persistence.dual_base import PostgresRetryPolicy
        rp = PostgresRetryPolicy(max_retries=3, base_delay=0.01)
        call_count = 0

        async def fails_twice_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                raise TimeoutError("connection timeout")
            return "ok"

        result, attempts, latency = await rp.execute("test", fails_twice_then_ok)
        assert result == "ok"
        assert attempts == 3

    async def test_retry_exhaustion_raises(self):
        from app.persistence.dual_base import PostgresRetryPolicy
        rp = PostgresRetryPolicy(max_retries=2, base_delay=0.01)

        async def always_fails():
            raise ConnectionError("connection timeout")

        with pytest.raises(ConnectionError):
            await rp.execute("test", always_fails)




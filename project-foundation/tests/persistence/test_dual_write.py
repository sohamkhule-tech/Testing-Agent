"""
Dual-write validation: failure isolation, retry policy, feature flags.
"""

import asyncio
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

import pytest
from app.domain.run import RunEntity
from app.repositories.run_repository import RunRepository as FsRunRepository
from app.repositories.pg_run_repository import RunRepository as PgRunRepository
from app.persistence.dual_run_repository import DualRunRepository
from app.persistence.dual_base import (
    DualWriteMetrics,
    PostgresRetryPolicy,
    _is_transient_pg_error,
)


class TestDualWriteMetrics:
    def test_initial_values_zero(self):
        m = DualWriteMetrics()
        assert m.filesystem_writes == 0
        assert m.postgres_writes == 0
        assert m.postgres_failures == 0
        assert m.postgres_retries == 0
        assert m.total_pg_latency_ms == 0.0
        assert m.filesystem_failures == 0

    def test_snapshot_returns_dict(self):
        m = DualWriteMetrics()
        m.filesystem_writes = 5
        snap = m.snapshot()
        assert snap["filesystem_writes"] == 5
        assert isinstance(snap, dict)


class TestPostgresRetryPolicy:
    def test_config(self):
        rp = PostgresRetryPolicy(max_retries=3, base_delay=0.1, max_delay=2.0)
        assert rp.max_retries == 3
        assert rp.base_delay == 0.1

    @pytest.mark.asyncio
    async def test_no_retry_on_success(self):
        rp = PostgresRetryPolicy(max_retries=3, base_delay=0.01)
        call_count = 0

        async def success():
            nonlocal call_count
            call_count += 1
            return "ok"

        result, attempts, latency = await rp.execute("test", success)
        assert result == "ok"
        assert attempts == 1
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_no_retry_on_permanent_error(self):
        rp = PostgresRetryPolicy(max_retries=3, base_delay=0.01)
        call_count = 0

        async def perm_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("permanent")

        with pytest.raises(ValueError):
            await rp.execute("test", perm_error)
        assert call_count == 1  # no retry

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self):
        rp = PostgresRetryPolicy(max_retries=3, base_delay=0.01)
        call_count = 0

        async def transient_then_ok():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise TimeoutError("connection timeout")
            return "recovered"

        result, attempts, latency = await rp.execute("test", transient_then_ok)
        assert result == "recovered"
        assert attempts == 3
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exhaustion(self):
        rp = PostgresRetryPolicy(max_retries=2, base_delay=0.01)
        call_count = 0

        async def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("connection refused")

        with pytest.raises(ConnectionError):
            await rp.execute("test", always_fails)
        assert call_count == 2

    def test_is_transient(self):
        assert _is_transient_pg_error(TimeoutError("connection timeout"))
        assert _is_transient_pg_error(ConnectionError("connection refused"))
        assert not _is_transient_pg_error(ValueError("invalid"))


class TestDualRunRepository:
    @pytest.fixture
    def mock_fs(self):
        return MagicMock(spec=FsRunRepository)

    @pytest.fixture
    def mock_pg(self):
        pg = MagicMock(spec=PgRunRepository)
        pg.create = AsyncMock()
        pg.update = AsyncMock()
        pg.delete = AsyncMock()
        pg.exists = AsyncMock()
        pg.get_by_id = AsyncMock()
        return pg

    @pytest.fixture
    def config_all_off(self):
        cfg = MagicMock()
        cfg.filesystem_enabled = True
        cfg.postgres_enabled = False
        cfg.dual_write_enabled = False
        cfg.database_read_enabled = False
        return cfg

    @pytest.fixture
    def config_dual_on(self):
        cfg = MagicMock()
        cfg.filesystem_enabled = True
        cfg.postgres_enabled = True
        cfg.dual_write_enabled = True
        cfg.database_read_enabled = False
        return cfg

    def make_entity(self):
        return MagicMock(spec=RunEntity, run_id=uuid4())

    @pytest.mark.asyncio
    async def test_create_fs_only_when_dual_disabled(self, mock_fs, mock_pg, config_all_off):
        entity = self.make_entity()
        mock_fs.create.return_value = entity
        dual = DualRunRepository(mock_fs, mock_pg, config=config_all_off)
        result = await dual.create(entity)
        assert result is entity
        assert mock_fs.create.called
        assert not mock_pg.create.called

    @pytest.mark.asyncio
    async def test_create_fs_and_pg_when_dual_enabled(self, mock_fs, mock_pg, config_dual_on):
        entity = self.make_entity()
        mock_fs.create.return_value = entity
        mock_pg.create = AsyncMock(return_value=entity)
        dual = DualRunRepository(mock_fs, mock_pg, config=config_dual_on)
        result = await dual.create(entity)
        assert result is entity
        assert mock_fs.create.called
        assert mock_pg.create.called

    @pytest.mark.asyncio
    async def test_pg_failure_does_not_raise(self, mock_fs, mock_pg, config_dual_on):
        """PG failure should be logged, not propagated."""
        entity = self.make_entity()
        mock_fs.create.return_value = entity
        mock_pg.create = AsyncMock(side_effect=TimeoutError("PG timeout"))
        dual = DualRunRepository(mock_fs, mock_pg, config=config_dual_on)
        result = await dual.create(entity)
        assert result is entity  # FS result returned
        assert dual.metrics.postgres_failures > 0

    @pytest.mark.asyncio
    async def test_fs_failure_propagates(self, mock_fs, mock_pg, config_dual_on):
        """FS failure should propagate — PG never attempted."""
        entity = self.make_entity()
        mock_fs.create.side_effect = RuntimeError("FS full")
        dual = DualRunRepository(mock_fs, mock_pg, config=config_dual_on)
        with pytest.raises(RuntimeError):
            await dual.create(entity)
        assert dual.metrics.filesystem_failures > 0
        assert not mock_pg.create.called

    @pytest.mark.asyncio
    async def test_exists_reads_from_fs_by_default(self, mock_fs, mock_pg, config_all_off):
        mock_fs.exists = AsyncMock(return_value=True)
        dual = DualRunRepository(mock_fs, mock_pg, config=config_all_off)
        result = await dual.exists(uuid4())
        assert result is True
        assert mock_fs.exists.called
        assert not mock_pg.exists.called

    @pytest.mark.asyncio
    async def test_exists_reads_from_pg_when_db_read_enabled(self, mock_fs, mock_pg, config_dual_on):
        config_dual_on.database_read_enabled = True
        mock_pg.exists = AsyncMock(return_value=True)
        dual = DualRunRepository(mock_fs, mock_pg, config=config_dual_on)
        result = await dual.exists(uuid4())
        assert result is True
        assert mock_pg.exists.called

    @pytest.mark.asyncio
    async def test_delete_fs_only(self, mock_fs, mock_pg, config_all_off):
        mock_fs.delete = AsyncMock(return_value=True)
        dual = DualRunRepository(mock_fs, mock_pg, config=config_all_off)
        result = await dual.delete(uuid4())
        assert result is True
        assert mock_fs.delete.called
        assert not mock_pg.delete.called

    @pytest.mark.asyncio
    async def test_metrics_tracked_correctly(self, mock_fs, mock_pg, config_dual_on):
        entity = self.make_entity()
        mock_fs.create.return_value = entity
        mock_pg.create = AsyncMock(return_value=entity)
        dual = DualRunRepository(mock_fs, mock_pg, config=config_dual_on)
        await dual.create(entity)
        snap = dual.metrics.snapshot()
        assert snap["filesystem_writes"] >= 1
        assert snap["postgres_writes"] >= 1


class TestDualProjectRepository:
    @pytest.mark.asyncio
    async def test_create_noop_when_pg_disabled(self):
        from unittest.mock import MagicMock
        from app.persistence.dual_project_repository import DualProjectRepository
        from app.repositories.pg_project_repository import ProjectRepository

        cfg = MagicMock()
        cfg.postgres_enabled = False
        pg_repo = MagicMock(spec=ProjectRepository)
        dual = DualProjectRepository(pg_repo, config=cfg)
        entity = MagicMock()
        result = await dual.create(entity)
        assert result is entity
        assert not pg_repo.create.called

    @pytest.mark.asyncio
    async def test_create_calls_pg_when_enabled(self):
        from unittest.mock import MagicMock, AsyncMock
        from app.persistence.dual_project_repository import DualProjectRepository
        from app.repositories.pg_project_repository import ProjectRepository

        cfg = MagicMock()
        cfg.postgres_enabled = True
        pg_repo = MagicMock(spec=ProjectRepository)
        pg_repo.create = AsyncMock()
        dual = DualProjectRepository(pg_repo, config=cfg)
        entity = MagicMock()
        await dual.create(entity)
        assert pg_repo.create.called

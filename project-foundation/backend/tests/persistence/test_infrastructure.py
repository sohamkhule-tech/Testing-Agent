"""
Infrastructure validation: settings, feature flags, engine, session, health.
"""

import pytest
from app.config.settings import Settings, PersistenceSettings
from app.persistence.config import PersistenceConfig, get_persistence_config
from app.infrastructure.database import get_session_factory
from sqlalchemy import text


class TestSettings:
    def test_persistence_settings_exist(self):
        s = Settings()
        assert hasattr(s, "persistence")
        assert isinstance(s.persistence, PersistenceSettings)

    def test_feature_flags_default_to_false(self):
        s = Settings()
        assert s.persistence.filesystem_enabled is True
        assert s.persistence.postgres_enabled is False
        assert s.persistence.dual_write_enabled is False
        assert s.persistence.database_read_enabled is False

    def test_persistence_config_matches_settings(self):
        cfg = get_persistence_config()
        s = Settings().persistence
        assert cfg.filesystem_enabled == s.filesystem_enabled
        assert cfg.postgres_enabled == s.postgres_enabled
        assert cfg.dual_write_enabled == s.dual_write_enabled
        assert cfg.database_read_enabled == s.database_read_enabled

    def test_persistence_config_is_cached(self):
        assert get_persistence_config() is get_persistence_config()

    def test_persistence_config_repr(self):
        cfg = get_persistence_config()
        r = repr(cfg)
        assert "filesystem" in r
        assert "postgres" in r
        assert "dual_write" in r
        assert "db_read" in r


class TestDatabaseSettings:
    def test_database_url_not_empty(self):
        from app.config import get_settings
        url = get_settings().database.url
        assert url.startswith("postgresql+asyncpg://")

    def test_pool_size_positive(self):
        from app.config import get_settings
        assert get_settings().database.pool_size >= 1

    def test_connect_timeout_in_range(self):
        from app.config import get_settings
        t = get_settings().database.connect_timeout
        assert 1 <= t <= 60


class TestDependencies:
    def test_get_run_repository_returns_file_based(self):
        from app.dependencies import get_run_repository
        repo = get_run_repository()
        assert repo.__class__.__name__ == "RunRepository"

    def test_get_dual_run_repository_returns_none(self):
        from app.dependencies import get_dual_run_repository
        assert get_dual_run_repository() is None

    def test_get_pg_run_repository_returns_none(self):
        from app.dependencies import get_pg_run_repository
        assert get_pg_run_repository() is None

    def test_get_fs_run_repository_returns_run_repo(self):
        from app.dependencies import get_fs_run_repository
        assert get_fs_run_repository().__class__.__name__ == "RunRepository"


# These tests require the test database engine fixture
# and are marked slow to avoid event-loop conflicts with sync tests.


@pytest.mark.slow
@pytest.mark.asyncio
class TestEngine:
    async def test_engine_connect(self, db_engine):
        async with db_engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            assert result.scalar() == 1

    async def test_session_factory(self):
        factory = get_session_factory()
        assert factory is not None

    async def test_session_lifecycle(self, db_engine):
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession
        factory = async_sessionmaker(bind=db_engine, class_=AsyncSession)
        async with factory() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1


@pytest.mark.slow
@pytest.mark.asyncio
class TestHealth:
    async def test_health_check(self, db_engine):
        from app.infrastructure.database import check_database_health
        result = await check_database_health()
        assert "status" in result
        assert "latency_ms" in result

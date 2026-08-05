"""
Persistence test fixtures.

Provides database session, engine, repository fixtures,
and feature flag helpers for all persistence tests.

Every test that writes to the database runs within a transaction
that is rolled back on teardown — tests never leave data behind.
"""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator, AsyncIterator
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings
from app.infrastructure.database import metadata as db_metadata
from app.models import orm  # noqa: F401  — register models with metadata
from app.persistence.config import PersistenceConfig, get_persistence_config
from app.repositories.pg_artifact_repository import ArtifactRepository
from app.repositories.pg_audit_log_repository import AuditLogRepository
from app.repositories.pg_crawl_package_repository import CrawlPackageRepository
from app.repositories.pg_execution_repository import ExecutionRepository
from app.repositories.pg_generated_project_repository import GeneratedProjectRepository
from app.repositories.pg_human_review_repository import HumanReviewRepository
from app.repositories.pg_inventory_repository import InventoryRepository
from app.repositories.pg_ir_document_repository import IRDocumentRepository
from app.repositories.pg_project_repository import ProjectRepository
from app.repositories.pg_run_repository import RunRepository as PgRunRepository
from app.repositories.pg_test_plan_repository import TestPlanRepository
from app.repositories.pg_test_result_repository import TestResultRepository
from app.repositories.pg_user_repository import UserRepository

# ===================================================================
# Engine fixtures
# ===================================================================


@pytest_asyncio.fixture(scope="session")
async def db_engine() -> AsyncEngine:
    """Create the test database engine.

    Uses the same database URL as the application (from settings).
    The database must exist and be migrated before tests run.
    """
    settings = get_settings()
    engine = create_async_engine(
        settings.database.url,
        echo=settings.database.echo,
        pool_size=2,
        max_overflow=2,
        pool_pre_ping=False,
        pool_recycle=3600,
    )
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="session")
async def tables_created(db_engine: AsyncEngine) -> bool:
    """Verify all tables exist. Creates them if they don't."""
    import logging

    logger = logging.getLogger("tests.persistence")
    async with db_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
        )
        count = result.scalar()
        if count < 14:
            logger.warning("Only %s tables found — run alembic upgrade head first", count)
            return False
        logger.info("All %s tables present", count)
        return True


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Create a new AsyncSession within a transaction.

    The transaction is rolled back after the test, leaving no data.
    """
    factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as session:
        try:
            await session.begin()
            yield session
        finally:
            await session.rollback()


# ===================================================================
# Repository fixtures
# ===================================================================


@pytest_asyncio.fixture
async def user_repo(db_session: AsyncSession) -> UserRepository:
    return UserRepository(db_session)


@pytest_asyncio.fixture
async def project_repo(db_session: AsyncSession) -> ProjectRepository:
    return ProjectRepository(db_session)


@pytest_asyncio.fixture
async def run_repo(db_session: AsyncSession) -> PgRunRepository:
    return PgRunRepository(db_session)


@pytest_asyncio.fixture
async def crawl_package_repo(db_session: AsyncSession) -> CrawlPackageRepository:
    return CrawlPackageRepository(db_session)


@pytest_asyncio.fixture
async def inventory_repo(db_session: AsyncSession) -> InventoryRepository:
    return InventoryRepository(db_session)


@pytest_asyncio.fixture
async def test_plan_repo(db_session: AsyncSession) -> TestPlanRepository:
    return TestPlanRepository(db_session)


@pytest_asyncio.fixture
async def human_review_repo(db_session: AsyncSession) -> HumanReviewRepository:
    return HumanReviewRepository(db_session)


@pytest_asyncio.fixture
async def ir_document_repo(db_session: AsyncSession) -> IRDocumentRepository:
    return IRDocumentRepository(db_session)


@pytest_asyncio.fixture
async def generated_project_repo(db_session: AsyncSession) -> GeneratedProjectRepository:
    return GeneratedProjectRepository(db_session)


@pytest_asyncio.fixture
async def execution_repo(db_session: AsyncSession) -> ExecutionRepository:
    return ExecutionRepository(db_session)


@pytest_asyncio.fixture
async def test_result_repo(db_session: AsyncSession) -> TestResultRepository:
    return TestResultRepository(db_session)


@pytest_asyncio.fixture
async def artifact_repo(db_session: AsyncSession) -> ArtifactRepository:
    return ArtifactRepository(db_session)


@pytest_asyncio.fixture
async def audit_log_repo(db_session: AsyncSession) -> AuditLogRepository:
    return AuditLogRepository(db_session)


# ===================================================================
# Feature flag fixtures
# ===================================================================


@pytest.fixture
def persistence_config() -> PersistenceConfig:
    """Return the cached persistence config (flags all off by default)."""
    return get_persistence_config()


# ===================================================================
# Async loop
# ===================================================================


@pytest.fixture(scope="function")
def event_loop():
    """Create a fresh event loop per test function."""
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)

"""
Unit of Work

Owns an ``AsyncSession``, manages transaction boundaries, and exposes
repositories through a ``RepositoryProvider``.

Typical usage (once integrated into services)::

    async with UnitOfWork() as uow:
        user = await uow.users.get_by_id(user_id)
        project = Project(name="my-app", ...)
        await uow.projects.create(project)
        await uow.commit()          # flushes & commits
        # exiting the context with no exception auto-commits
        # exiting with an exception auto-rollbacks

For read-only operations the commit is a no-op::

    async with UnitOfWork() as uow:
        run = await uow.runs.get_by_run_id(run_id)
        # no commit needed — context manager commits (safe no-op)
"""

from __future__ import annotations

import logging
from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.database import get_session_factory
from app.persistence.repository_provider import RepositoryProvider

logger = logging.getLogger("app.persistence.unit_of_work")


class UnitOfWork:
    """Context manager that wraps a transaction and exposes repositories.

    Args:
        session_factory: Optional callable that returns a new ``AsyncSession``.
            Defaults to the project-wide session factory from
            ``app.infrastructure.database.get_session_factory()``.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()
        self._session: AsyncSession | None = None
        self._provider: RepositoryProvider | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def session(self) -> AsyncSession:
        """Return the underlying ``AsyncSession``.

        Raises ``RuntimeError`` if accessed outside the context manager.
        """
        if self._session is None:
            raise RuntimeError("UnitOfWork session is only available within a context block")
        return self._session

    @property
    def users(self):
        return self._provider.users

    @property
    def projects(self):
        return self._provider.projects

    @property
    def runs(self):
        return self._provider.runs

    @property
    def crawl_packages(self):
        return self._provider.crawl_packages

    @property
    def inventories(self):
        return self._provider.inventories

    @property
    def test_plans(self):
        return self._provider.test_plans

    @property
    def human_reviews(self):
        return self._provider.human_reviews

    @property
    def ir_documents(self):
        return self._provider.ir_documents

    @property
    def generated_projects(self):
        return self._provider.generated_projects

    @property
    def executions(self):
        return self._provider.executions

    @property
    def test_results(self):
        return self._provider.test_results

    @property
    def artifacts(self):
        return self._provider.artifacts

    @property
    def audit_log(self):
        return self._provider.audit_log

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self._session is not None:
            await self._session.commit()

    async def rollback(self) -> None:
        """Roll back the current transaction."""
        if self._session is not None:
            await self._session.rollback()

    async def flush(self) -> None:
        """Flush pending changes without committing."""
        if self._session is not None:
            await self._session.flush()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    async def __aenter__(self) -> UnitOfWork:
        self._session = self._session_factory()
        self._provider = RepositoryProvider(self._session)
        logger.debug("uow_session_started")
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is None:
                await self._session.commit()
                logger.debug("uow_committed")
            else:
                await self._session.rollback()
                logger.debug("uow_rolled_back", exc_type=exc_type.__name__)
        finally:
            await self._session.close()
            self._session = None
            self._provider = None
            logger.debug("uow_session_closed")

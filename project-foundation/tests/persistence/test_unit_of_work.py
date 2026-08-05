"""
Unit of Work validation: commit, rollback, isolation, session management.
"""

import pytest
from app.persistence.unit_of_work import UnitOfWork
from app.infrastructure.database import get_session_factory

pytestmark = pytest.mark.asyncio


class TestUnitOfWork:
    @pytest.mark.slow
    async def test_uow_commit_persists_data(self):
        factory = get_session_factory()
        from tests.helpers.persistence import make_audit_log

        async with UnitOfWork(session_factory=factory) as uow:
            al = make_audit_log(action="uow.test.commit")
            uow.session.add(al)
            await uow.commit()

        async with factory() as session:
            from sqlalchemy import text, select
            result = await session.execute(
                text("SELECT count(*) FROM audit_log WHERE action = 'uow.test.commit'")
            )
            assert result.scalar() >= 1

    @pytest.mark.slow
    async def test_uow_rollback_clears_data(self):
        factory = get_session_factory()
        from uuid import uuid4
        from tests.helpers.persistence import make_audit_log

        action_name = f"uow.test.rollback.{uuid4().hex[:8]}"
        async with UnitOfWork(session_factory=factory) as uow:
            al = make_audit_log(action=action_name)
            uow.session.add(al)
            await uow.rollback()

        from sqlalchemy import text
        async with factory() as session:
            result = await session.execute(
                text("SELECT count(*) FROM audit_log WHERE action = :action"),
                {"action": action_name},
            )
            assert result.scalar() == 0

    @pytest.mark.slow
    async def test_uow_rollback_on_exception(self):
        factory = get_session_factory()
        from uuid import uuid4
        from tests.helpers.persistence import make_audit_log

        action_name = f"uow.test.exception.{uuid4().hex[:8]}"
        try:
            async with UnitOfWork(session_factory=factory) as uow:
                al = make_audit_log(action=action_name)
                uow.session.add(al)
                raise ValueError("Simulated failure")
        except ValueError:
            pass

        from sqlalchemy import text
        async with factory() as session:
            result = await session.execute(
                text("SELECT count(*) FROM audit_log WHERE action = :action"),
                {"action": action_name},
            )
            assert result.scalar() == 0

    async def test_uow_provides_repository_provider(self):
        factory = get_session_factory()
        async with UnitOfWork(session_factory=factory) as uow:
            assert hasattr(uow, "users")
            assert hasattr(uow, "runs")
            assert hasattr(uow, "projects")
            assert hasattr(uow, "audit_log")
            assert hasattr(uow, "session")

    async def test_uow_session_unavailable_outside_context(self):
        uow = UnitOfWork()
        with pytest.raises(RuntimeError):
            _ = uow.session

    @pytest.mark.slow
    async def test_uow_flush(self):
        factory = get_session_factory()
        from uuid import uuid4
        from tests.helpers.persistence import make_audit_log

        action_name = f"uow.test.flush.{uuid4().hex[:8]}"
        async with UnitOfWork(session_factory=factory) as uow:
            al = make_audit_log(action=action_name)
            uow.session.add(al)
            await uow.flush()

            from sqlalchemy import text
            result = await uow.session.execute(
                text("SELECT count(*) FROM audit_log WHERE action = :action"),
                {"action": action_name},
            )
            assert result.scalar() >= 1
            await uow.rollback()

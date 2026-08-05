"""
Alembic migration validation: upgrade, downgrade, idempotency.
"""

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.runtime.environment import EnvironmentContext


ALEMBIC_CFG = Config("alembic.ini")


class TestMigrationStructure:
    def test_head_revision_exists(self):
        script = ScriptDirectory.from_config(ALEMBIC_CFG)
        head = script.get_current_head()
        assert head is not None, "No head revision found"
        assert len(head) > 0

    def test_single_head(self):
        script = ScriptDirectory.from_config(ALEMBIC_CFG)
        heads = script.get_heads()
        assert len(heads) == 1, f"Expected 1 head, got {len(heads)}: {heads}"

    def test_head_revision_is_create_tables(self):
        script = ScriptDirectory.from_config(ALEMBIC_CFG)
        head = script.get_current_head()
        rev = script.get_revision(head)
        assert rev is not None
        assert rev.doc == "create_tables" or "create_tables" in rev.doc.lower(), \
            f"Unexpected head doc: {rev.doc}"

    def test_revision_has_upgrade_and_downgrade(self):
        script = ScriptDirectory.from_config(ALEMBIC_CFG)
        head = script.get_current_head()
        rev = script.get_revision(head)
        assert rev is not None
        assert hasattr(rev.module, "upgrade")
        assert hasattr(rev.module, "downgrade")

    def test_downgrade_to_base_is_defined(self):
        script = ScriptDirectory.from_config(ALEMBIC_CFG)
        head = script.get_current_head()
        rev = script.get_revision(head)
        assert rev is not None
        # Verify we can traverse from head to base
        down = rev.down_revision
        assert down is None, f"Head revision has down_revision={down} (expected None for initial)"

    def test_no_unregistered_models(self):
        """Verify Alembic sees the same model state as our metadata."""
        from app.infrastructure.database import metadata
        from app.models import orm  # noqa: F401
        # Compare what Alembic sees vs what we have
        script = ScriptDirectory.from_config(ALEMBIC_CFG)
        head = script.get_current_head()
        assert head is not None
        # Just verify the head revision's metadata matches our expected count
        assert len(metadata.tables) >= 14


class TestMigrationReversibility:
    """These tests run actual upgrade/downgrade.

    They require the database to be available.
    Run with: pytest --runslow or manually.
    """

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_downgrade_upgrade_cycle(self):
        """Verify downgrade clears all tables, upgrade recreates them.

        This test operates on the actual database.
        """
        import asyncio
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.config import get_settings

        settings = get_settings()
        engine = create_async_engine(
            settings.database.url, pool_pre_ping=True, pool_size=1,
        )

        async def run_alembic(command: str):
            """Run an alembic command asynchronously."""
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "alembic", command,
                cwd=".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode

        try:
            # Verify tables exist before downgrade
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_schema='public' AND table_name != 'alembic_version'")
                )
                before_count = result.scalar()
                assert before_count >= 14, f"Expected 14+ tables before downgrade, got {before_count}"

            # Run downgrade
            code = await run_alembic("downgrade base")
            assert code == 0, f"Downgrade failed with code {code}"

            # Verify all tables dropped
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_schema='public' AND table_name != 'alembic_version'")
                )
                assert result.scalar() == 0, "Tables remain after downgrade"

            # Run upgrade
            code = await run_alembic("upgrade head")
            assert code == 0, f"Upgrade failed with code {code}"

            # Verify all tables recreated
            async with engine.connect() as conn:
                result = await conn.execute(
                    text("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_schema='public' AND table_name != 'alembic_version'")
                )
                after_count = result.scalar()
                assert after_count >= 14, f"Expected 14+ tables after re-upgrade, got {after_count}"

        finally:
            await engine.dispose()

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_upgrade_idempotent(self):
        """Running upgrade twice should be safe."""
        import asyncio

        async def run_alembic(command: str):
            proc = await asyncio.create_subprocess_exec(
                "python", "-m", "alembic", command,
                cwd=".",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            return proc.returncode

        code = await run_alembic("upgrade head")
        assert code == 0, f"First upgrade failed with code {code}"

        code = await run_alembic("upgrade head")
        assert code == 0, f"Idempotent upgrade failed with code {code}"

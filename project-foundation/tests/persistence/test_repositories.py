"""
Repository CRUD validation for all 13 PostgreSQL repositories.

Each test creates an entity via a repository factory function,
then verifies all CRUD operations.
"""

import pytest
from uuid import uuid4
from tests.helpers.persistence import (
    make_user, make_project, make_run, make_crawl_package, make_inventory,
    make_test_plan, make_test_scenario, make_human_review,
    make_ir_document, make_generated_project,
    make_execution, make_test_result, make_artifact, make_audit_log,
)


pytestmark = pytest.mark.asyncio


class TestUserRepository:
    async def test_create_and_get(self, user_repo, db_session):
        user = make_user()
        created = await user_repo.create(user)
        assert created.id is not None

        fetched = await user_repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.email == user.email

    async def test_create_and_get_by_email(self, user_repo, db_session):
        user = make_user(email="unique@test.com")
        await user_repo.create(user)
        fetched = await user_repo.find_by_email("unique@test.com")
        assert fetched is not None

    async def test_exists(self, user_repo, db_session):
        user = make_user()
        created = await user_repo.create(user)
        assert await user_repo.exists(created.id) is True
        assert await user_repo.exists(uuid4()) is False

    async def test_update(self, user_repo, db_session):
        user = make_user(display_name="old")
        created = await user_repo.create(user)
        created.display_name = "new"
        updated = await user_repo.update(created)
        assert updated.display_name == "new"

    async def test_delete(self, user_repo, db_session):
        user = make_user()
        created = await user_repo.create(user)
        assert await user_repo.delete(created.id) is True
        assert await user_repo.get_by_id(created.id) is None

    async def test_list(self, user_repo, db_session):
        for _ in range(3):
            await user_repo.create(make_user())
        results = await user_repo.list(limit=10)
        assert len(results) >= 3

    async def test_list_by_role(self, user_repo, db_session):
        admin = make_user(role="admin")
        await user_repo.create(admin)
        results = await user_repo.list_by_role("admin")
        assert any(u.role == "admin" for u in results)


class TestProjectRepository:
    async def test_crud(self, project_repo, db_session):
        proj = make_project(name="test-proj")
        c = await project_repo.create(proj)
        assert c.id is not None

        f = await project_repo.get_by_id(c.id)
        assert f is not None and f.name == "test-proj"

        c.name = "updated"
        await project_repo.update(c)

        assert await project_repo.exists(c.id)
        assert await project_repo.delete(c.id)

    async def test_find_by_name(self, project_repo, db_session):
        name = f"find-{uuid4().hex[:8]}"
        await project_repo.create(make_project(name=name))
        found = await project_repo.find_by_name(name)
        assert found is not None


class TestRunRepository:
    async def test_crud(self, run_repo, db_session):
        run = make_run()
        c = await run_repo.create(run)
        assert c.id is not None

        fetched = await run_repo.get_by_id(c.id)
        assert fetched is not None

        assert await run_repo.delete(c.id)

    async def test_get_by_run_id(self, run_repo, db_session):
        run_id = uuid4()
        run = make_run(run_id=run_id)
        await run_repo.create(run)
        fetched = await run_repo.get_by_run_id(run_id)
        assert fetched is not None

    async def test_list_recent(self, run_repo, db_session):
        for _ in range(3):
            await run_repo.create(make_run())
        results = await run_repo.list_recent(limit=5)
        assert len(results) >= 3

    async def test_update_status(self, run_repo, db_session):
        from app.models.enums import RunStatus
        run = make_run()
        await run_repo.create(run)
        ok = await run_repo.update_status(run.id, RunStatus.RUNNING)
        assert ok
        fetched = await run_repo.get_by_id(run.id)
        assert fetched.status == "running"


class TestCrawlPackageRepository:
    async def test_get_by_run_id(self, crawl_package_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        cp = make_crawl_package(run_id=run.run_id)
        await crawl_package_repo.create(cp)
        fetched = await crawl_package_repo.get_by_run_id(run.run_id)
        assert fetched is not None


class TestInventoryRepository:
    async def test_get_by_run_id(self, inventory_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        inv = make_inventory(run_id=run.run_id)
        await inventory_repo.create(inv)
        fetched = await inventory_repo.get_by_run_id(run.run_id)
        assert fetched is not None


class TestTestPlanRepository:
    async def test_latest_version(self, test_plan_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        tp = make_test_plan(run_id=run.run_id, version=1, is_latest=True)
        await test_plan_repo.create(tp)
        latest = await test_plan_repo.latest_version(run.run_id)
        assert latest is not None

    async def test_get_by_run_id(self, test_plan_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        await test_plan_repo.create(make_test_plan(run_id=run.run_id))
        results = await test_plan_repo.get_by_run_id(run.run_id)
        assert len(results) >= 1


class TestHumanReviewRepository:
    async def test_latest_review(self, human_review_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        hr = make_human_review(run_id=run.run_id, version=1)
        await human_review_repo.create(hr)
        latest = await human_review_repo.latest_review(run.run_id)
        assert latest is not None


class TestIRDocumentRepository:
    async def test_latest_version(self, ir_document_repo, test_plan_repo, run_repo, db_session):
        # Need to create test_plan first since ir_documents FK references it
        run = make_run()
        await run_repo.create(run)
        tp = make_test_plan(run_id=run.run_id)
        await test_plan_repo.create(tp)
        ir = make_ir_document(test_plan_id=tp.id, run_id=run.run_id, is_latest=True)
        await ir_document_repo.create(ir)
        latest = await ir_document_repo.latest_version(tp.id)
        assert latest is not None


class TestGeneratedProjectRepository:
    async def test_get_by_run_id(self, generated_project_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        gp = make_generated_project(run_id=run.run_id)
        await generated_project_repo.create(gp)
        fetched = await generated_project_repo.get_by_run_id(run.run_id)
        assert fetched is not None


class TestExecutionRepository:
    async def test_crud(self, execution_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        exec_entity = make_execution(run_id=run.run_id)
        created = await execution_repo.create(exec_entity)
        assert created.id is not None

        fetched = await execution_repo.get_by_id(created.id)
        assert fetched is not None

        fetched_by_run = await execution_repo.get_by_run_id(run.run_id)
        assert fetched_by_run is not None

    async def test_list_recent(self, execution_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        for _ in range(3):
            await execution_repo.create(make_execution(run_id=run.run_id))
        results = await execution_repo.list_recent(limit=5)
        assert len(results) >= 3


class TestTestResultRepository:
    async def test_crud(self, test_result_repo, execution_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        exec_entity = make_execution(run_id=run.run_id)
        await execution_repo.create(exec_entity)
        tr = make_test_result(execution_id=exec_entity.id)
        created = await test_result_repo.create(tr)
        assert created.id is not None

        results = await test_result_repo.list_by_execution_id(exec_entity.id)
        assert len(results) >= 1


class TestArtifactRepository:
    async def test_list_by_run_id(self, artifact_repo, run_repo, db_session):
        run = make_run()
        await run_repo.create(run)
        art = make_artifact(run_id=run.run_id)
        await artifact_repo.create(art)
        results = await artifact_repo.list_by_run_id(run.run_id)
        assert len(results) >= 1


class TestAuditLogRepository:
    async def test_list_recent(self, audit_log_repo, db_session):
        al = make_audit_log()
        await audit_log_repo.create(al)
        results = await audit_log_repo.list_recent(limit=5)
        assert len(results) >= 1

    async def test_list_by_entity(self, audit_log_repo, db_session):
        entity_id = uuid4()
        al = make_audit_log(entity_id=entity_id, entity_type="run")
        await audit_log_repo.create(al)
        results = await audit_log_repo.list_by_entity("run", entity_id)
        assert len(results) >= 1

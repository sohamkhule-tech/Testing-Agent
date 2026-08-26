"""
Repository Provider

Creates all 13 PostgreSQL repository instances from a single ``AsyncSession``.

Each repository is constructed once and cached for the lifetime of the
provider instance (typically one per Unit of Work or per request).

Usage::

    provider = RepositoryProvider(session)
    user = await provider.users.get_by_id(...)
    run = await provider.runs.get_by_run_id(...)

Repositories exposed as properties for concise access.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

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


class RepositoryProvider:
    """Constructs and caches all PG repositories for a single session.

    All repository instances share the same ``AsyncSession``.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repos: dict[str, object] = {}

    # ------------------------------------------------------------------
    # Repository accessors — each creates the repo once, then caches it
    # ------------------------------------------------------------------

    @property
    def users(self) -> UserRepository:
        return self._get_or_create("users", UserRepository)

    @property
    def projects(self) -> ProjectRepository:
        return self._get_or_create("projects", ProjectRepository)

    @property
    def runs(self) -> PgRunRepository:
        return self._get_or_create("runs", PgRunRepository)

    @property
    def crawl_packages(self) -> CrawlPackageRepository:
        return self._get_or_create("crawl_packages", CrawlPackageRepository)

    @property
    def inventories(self) -> InventoryRepository:
        return self._get_or_create("inventories", InventoryRepository)

    @property
    def test_plans(self) -> TestPlanRepository:
        return self._get_or_create("test_plans", TestPlanRepository)

    @property
    def human_reviews(self) -> HumanReviewRepository:
        return self._get_or_create("human_reviews", HumanReviewRepository)

    @property
    def ir_documents(self) -> IRDocumentRepository:
        return self._get_or_create("ir_documents", IRDocumentRepository)

    @property
    def generated_projects(self) -> GeneratedProjectRepository:
        return self._get_or_create("generated_projects", GeneratedProjectRepository)

    @property
    def executions(self) -> ExecutionRepository:
        return self._get_or_create("executions", ExecutionRepository)

    @property
    def test_results(self) -> TestResultRepository:
        return self._get_or_create("test_results", TestResultRepository)

    @property
    def artifacts(self) -> ArtifactRepository:
        return self._get_or_create("artifacts", ArtifactRepository)

    @property
    def audit_log(self) -> AuditLogRepository:
        return self._get_or_create("audit_log", AuditLogRepository)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create(self, key: str, repo_cls: type) -> object:
        repo = self._repos.get(key)
        if repo is None:
            repo = repo_cls(self._session)
            self._repos[key] = repo
        return repo

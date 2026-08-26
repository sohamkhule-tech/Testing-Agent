"""Repository implementations.

Existing file-based: RunRepository
New PostgreSQL:     pg_* repositories

All PG repositories accept ``AsyncSession`` via constructor injection
and never call ``commit()`` / ``rollback()`` / ``close()``.
"""

from app.repositories.base import BaseRepository

from app.repositories.project_repository import ProjectRepository as FsProjectRepository
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
from app.repositories.run_repository import RunRepository

__all__ = [
    "ArtifactRepository",
    "FsProjectRepository",
    "AuditLogRepository",
    "BaseRepository",
    "CrawlPackageRepository",
    "ExecutionRepository",
    "GeneratedProjectRepository",
    "HumanReviewRepository",
    "InventoryRepository",
    "IRDocumentRepository",
    "PgRunRepository",
    "ProjectRepository",
    "RunRepository",
    "TestPlanRepository",
    "TestResultRepository",
    "UserRepository",
]

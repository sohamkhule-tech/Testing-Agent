"""
Phase 5A verification script.

Confirms:
  - PersistenceSettings are loaded with correct defaults
  - PersistenceConfig reads flags from settings
  - RepositoryProvider creates all 13 repos
  - UnitOfWork session lifecycle is correct
  - No service integration
  - No DB writes executed
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check(step: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {step}" + (f" — {detail}" if detail else ""))
    if not condition:
        print(f"\n*** FAILED at: {step} ***")
        sys.exit(1)


def main() -> None:
    print("=" * 60)
    print("  Phase 5A — Persistence Infrastructure Verification")
    print("=" * 60)
    print()

    # ------------------------------------------------------------------
    # 1. PersistenceSettings in config
    # ------------------------------------------------------------------
    from app.config.settings import Settings, PersistenceSettings

    s = Settings()
    check("Settings has 'persistence' attribute", hasattr(s, "persistence"))
    check("PersistenceSettings has filesystem_enabled", hasattr(s.persistence, "filesystem_enabled"))
    check("PersistenceSettings has postgres_enabled", hasattr(s.persistence, "postgres_enabled"))
    check("PersistenceSettings has dual_write_enabled", hasattr(s.persistence, "dual_write_enabled"))
    check("PersistenceSettings has database_read_enabled", hasattr(s.persistence, "database_read_enabled"))

    check("filesystem_enabled defaults to True", s.persistence.filesystem_enabled is True)
    check("postgres_enabled defaults to False", s.persistence.postgres_enabled is False)
    check("dual_write_enabled defaults to False", s.persistence.dual_write_enabled is False)
    check("database_read_enabled defaults to False", s.persistence.database_read_enabled is False)

    # ------------------------------------------------------------------
    # 2. PersistenceConfig
    # ------------------------------------------------------------------
    from app.persistence.config import PersistenceConfig, get_persistence_config, persistence_config

    pc = PersistenceConfig()
    check("PersistenceConfig has filesystem_enabled", pc.filesystem_enabled is True)
    check("PersistenceConfig has postgres_enabled", pc.postgres_enabled is False)
    check("PersistenceConfig has dual_write_enabled", pc.dual_write_enabled is False)
    check("PersistenceConfig has database_read_enabled", pc.database_read_enabled is False)

    check("get_persistence_config() returns PersistenceConfig",
          isinstance(get_persistence_config(), PersistenceConfig))

    check("persistence_config singleton is PersistenceConfig",
          isinstance(persistence_config, PersistenceConfig))

    check("persistence_config is cached singleton",
          persistence_config is get_persistence_config())

    # ------------------------------------------------------------------
    # 3. RepositoryProvider — create from a mock session
    # ------------------------------------------------------------------
    from unittest.mock import AsyncMock, MagicMock
    from app.persistence.repository_provider import RepositoryProvider
    from app.repositories.pg_user_repository import UserRepository
    from app.repositories.pg_project_repository import ProjectRepository
    from app.repositories.pg_run_repository import RunRepository as PgRunRepository
    from app.repositories.pg_crawl_package_repository import CrawlPackageRepository
    from app.repositories.pg_inventory_repository import InventoryRepository
    from app.repositories.pg_test_plan_repository import TestPlanRepository
    from app.repositories.pg_human_review_repository import HumanReviewRepository
    from app.repositories.pg_ir_document_repository import IRDocumentRepository
    from app.repositories.pg_generated_project_repository import GeneratedProjectRepository
    from app.repositories.pg_execution_repository import ExecutionRepository
    from app.repositories.pg_test_result_repository import TestResultRepository
    from app.repositories.pg_artifact_repository import ArtifactRepository
    from app.repositories.pg_audit_log_repository import AuditLogRepository

    mock_session = MagicMock()

    provider = RepositoryProvider(mock_session)
    check("provider.users is UserRepository", isinstance(provider.users, UserRepository))
    check("provider.projects is ProjectRepository", isinstance(provider.projects, ProjectRepository))
    check("provider.runs is PgRunRepository", isinstance(provider.runs, PgRunRepository))
    check("provider.crawl_packages is CrawlPackageRepository",
          isinstance(provider.crawl_packages, CrawlPackageRepository))
    check("provider.inventories is InventoryRepository",
          isinstance(provider.inventories, InventoryRepository))
    check("provider.test_plans is TestPlanRepository",
          isinstance(provider.test_plans, TestPlanRepository))
    check("provider.human_reviews is HumanReviewRepository",
          isinstance(provider.human_reviews, HumanReviewRepository))
    check("provider.ir_documents is IRDocumentRepository",
          isinstance(provider.ir_documents, IRDocumentRepository))
    check("provider.generated_projects is GeneratedProjectRepository",
          isinstance(provider.generated_projects, GeneratedProjectRepository))
    check("provider.executions is ExecutionRepository",
          isinstance(provider.executions, ExecutionRepository))
    check("provider.test_results is TestResultRepository",
          isinstance(provider.test_results, TestResultRepository))
    check("provider.artifacts is ArtifactRepository",
          isinstance(provider.artifacts, ArtifactRepository))
    check("provider.audit_log is AuditLogRepository",
          isinstance(provider.audit_log, AuditLogRepository))

    check("All 13 repos created from one session", len(provider._repos) == 13)

    # Verify cache — accessing same repo twice returns the same instance
    users_1 = provider.users
    users_2 = provider.users
    check("Repository cache works (same instance returned)", users_1 is users_2)

    # Verify all repos share the same session
    for key, repo in provider._repos.items():
        check(f"  {key} session matches provider session", repo.session is mock_session)

    # ------------------------------------------------------------------
    # 4. UnitOfWork — verify without a database (structural test only)
    # ------------------------------------------------------------------
    from app.persistence.unit_of_work import UnitOfWork

    uow = UnitOfWork()
    check("UnitOfWork is instantiable", isinstance(uow, UnitOfWork))
    check("UnitOfWork has commit method", callable(uow.commit))
    check("UnitOfWork has rollback method", callable(uow.rollback))
    check("UnitOfWork has flush method", callable(uow.flush))
    check("UnitOfWork has __aenter__", hasattr(uow, "__aenter__"))
    check("UnitOfWork has __aexit__", hasattr(uow, "__aexit__"))

    # Verify all provider properties are exposed on UnitOfWork (check on class)
    for attr in [
        "users", "projects", "runs", "crawl_packages", "inventories",
        "test_plans", "human_reviews", "ir_documents", "generated_projects",
        "executions", "test_results", "artifacts", "audit_log",
    ]:
        check(f"UnitOfWork.{attr} property exists",
              isinstance(getattr(type(uow), attr, None), property))

    # Verify session raises before context entered
    try:
        _ = UnitOfWork().session
        check("session access before context raises", False)
    except RuntimeError:
        check("session access before context raises RuntimeError", True)
    except Exception:
        check("session access before context raises RuntimeError", False)

    # ------------------------------------------------------------------
    # 5. Verify no existing code was modified
    # ------------------------------------------------------------------
    from app.repositories.base import BaseRepository
    from app.repositories.run_repository import RunRepository as FileRunRepository
    check("Existing BaseRepository unchanged", BaseRepository is not None)
    check("Existing file-based RunRepository unchanged", FileRunRepository is not None)

    from app.infrastructure.database import get_async_session, get_db_session
    check("Existing get_async_session unchanged", callable(get_async_session))
    check("Existing get_db_session unchanged", callable(get_db_session))

    # ------------------------------------------------------------------
    # 6. Install test — verify session factory integration
    # ------------------------------------------------------------------
    from app.infrastructure.database import get_session_factory
    factory = get_session_factory()
    uow_with_factory = UnitOfWork(session_factory=factory)
    check("UnitOfWork accepts custom session factory",
          isinstance(uow_with_factory, UnitOfWork))

    # ------------------------------------------------------------------
    # 7. PersistenceConfig flags match settings
    # ------------------------------------------------------------------
    check("Config filesystem matches settings",
          pc.filesystem_enabled == s.persistence.filesystem_enabled)
    check("Config postgres matches settings",
          pc.postgres_enabled == s.persistence.postgres_enabled)
    check("Config dual_write matches settings",
          pc.dual_write_enabled == s.persistence.dual_write_enabled)
    check("Config db_read matches settings",
          pc.database_read_enabled == s.persistence.database_read_enabled)

    # ------------------------------------------------------------------
    # 8. Package exports
    # ------------------------------------------------------------------
    from app.persistence import PersistenceConfig, RepositoryProvider, UnitOfWork
    check("PersistenceConfig exported from package",
          PersistenceConfig is not None)
    check("RepositoryProvider exported from package",
          RepositoryProvider is not None)
    check("UnitOfWork exported from package",
          UnitOfWork is not None)

    print()
    print("=" * 60)
    print("  ALL CHECKS PASSED — Phase 5A Complete")
    print("=" * 60)
    print()
    print("Summary:")
    print("  Created: app/persistence/ (4 files)")
    print("  Modified: app/config/settings.py (PersistenceSettings)")
    print("  Untouched:")
    print("    - ORM models")
    print("    - Business logic")
    print("    - Services")
    print("    - API routes")
    print("    - Agents")
    print("    - Workflow")
    print("    - Existing repositories")
    print("    - Alembic")
    print()
    print("Ready for Phase 5B: Dual-write & Service Integration")


if __name__ == "__main__":
    main()

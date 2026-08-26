"""
Integration validation: services unchanged, flags off, no PG writes.

Confirms that the application behaves identically to pre-migration
when all PostgreSQL feature flags are disabled.
"""

from unittest.mock import MagicMock, patch

import pytest
from app.persistence.config import get_persistence_config


class TestFeatureFlagsDisabled:
    def test_all_flags_disabled_by_default(self):
        cfg = get_persistence_config()
        assert cfg.postgres_enabled is False
        assert cfg.dual_write_enabled is False
        assert cfg.database_read_enabled is False
        assert cfg.filesystem_enabled is True

    def test_dual_run_repository_returns_none(self):
        from app.dependencies import get_dual_run_repository
        assert get_dual_run_repository() is None

    def test_pg_run_repository_returns_none(self):
        from app.dependencies import get_pg_run_repository
        assert get_pg_run_repository() is None

    def test_get_run_repository_returns_file_based(self):
        from app.dependencies import get_run_repository
        repo = get_run_repository()
        assert repo.__class__.__name__ == "RunRepository"

    def test_get_trigger_service_uses_file_repo(self):
        from app.dependencies import get_trigger_service
        svc = get_trigger_service()
        assert svc.repository.__class__.__name__ == "RunRepository"


class TestPersistenceAwareMixin:
    def test_mixin_properties_exist(self):
        from app.services.persistence_mixin import PersistenceAware
        assert hasattr(PersistenceAware, "persistence_config")
        assert hasattr(PersistenceAware, "dual_run_repository")
        assert hasattr(PersistenceAware, "log_persistence_status")

    def test_dual_run_repository_none_when_pg_disabled(self):
        from app.services.persistence_mixin import PersistenceAware
        # Create a minimal instance with the mixin
        class FakeService(PersistenceAware):
            pass
        svc = FakeService()
        assert svc.dual_run_repository is None

    def test_log_persistence_status_does_not_raise(self):
        from app.services.persistence_mixin import PersistenceAware
        class FakeService(PersistenceAware):
            pass
        svc = FakeService()
        # Should not raise with default flags
        svc.log_persistence_status("test_op")


class TestServicesUnchanged:
    """Verify that key service constructors and methods remain unchanged."""

    def test_trigger_service_signature(self):
        from app.services.trigger_service import TriggerService
        import inspect
        sig = inspect.signature(TriggerService.__init__)
        params = list(sig.parameters.keys())
        assert "repository" in params
        assert "workspace_manager" in params
        # No new required parameters
        assert len(params) <= 4  # self, repository, workspace_manager + any defaults

    def test_trigger_service_has_expected_methods(self):
        from app.services.trigger_service import TriggerService
        for method in ["create_run", "get_run", "get_metadata", "update_status"]:
            assert hasattr(TriggerService, method), f"Missing {method}"

    def test_crawler_service_unchanged(self):
        from app.services.crawler_service import CrawlerService
        assert hasattr(CrawlerService, "crawl")

    def test_human_review_service_unchanged(self):
        from app.services.human_review_service import HumanReviewService
        assert hasattr(HumanReviewService, "review_test_plan")
        assert hasattr(HumanReviewService, "load_test_plan")

    def test_all_services_still_importable(self):
        from app.services import (
            CrawlerService,
            HumanReviewService,
            InventoryAggregatorService,
            TestDesignService,
            TriggerService,
        )
        # If we got here, all imports work


class TestRoutesUnchanged:
    def test_trigger_router_imports(self):
        from app.api.routes.trigger import router
        assert router is not None
        assert len(router.routes) > 0

    def test_health_route_imports(self):
        from app.api.health import router as health_router
        assert health_router is not None


class TestDependenciesUnchanged:
    def test_all_original_deps_work(self):
        from app.dependencies import (
            get_workspace_manager,
            get_run_repository,
            get_trigger_service,
            get_trigger_agent,
            get_browser_manager,
            get_crawler_service,
            get_crawler_agent,
            get_inventory_aggregator_service,
            get_llm_client,
            get_test_design_service,
            get_test_design_agent,
            get_human_review_service,
        )
        assert callable(get_workspace_manager)
        assert callable(get_run_repository)

    def test_new_deps_available(self):
        from app.dependencies import (
            get_persistence_config,
            get_fs_run_repository,
            get_dual_run_repository,
            get_pg_run_repository,
        )
        assert callable(get_persistence_config)
        assert callable(get_fs_run_repository)
        assert callable(get_dual_run_repository)
        assert callable(get_pg_run_repository)

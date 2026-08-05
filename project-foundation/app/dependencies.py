"""
Dependency Injection Container

Provides dependency injection for the application.
"""

from functools import lru_cache
from pathlib import Path

from app.agents import CrawlerAgent, TestDesignAgent, TriggerAgent
from app.config import get_settings
from app.infrastructure import BrowserManager, WorkspaceManager
from app.llm import OpenAIClient
from app.repositories import RunRepository
from app.services import CrawlerService, DashboardService, HumanReviewService, InventoryAggregatorService, ProjectService, TestDesignService, TriggerService


# ===================================================================
# Core infrastructure (existing — unchanged)
# ===================================================================


@lru_cache()
def get_workspace_manager() -> WorkspaceManager:
    """Get workspace manager singleton."""
    return WorkspaceManager()


@lru_cache()
def get_run_repository() -> RunRepository:
    """Get run repository singleton (file-based)."""
    settings = get_settings()
    storage_dir = Path(settings.storage.storage_base_path) / "runs" / "metadata"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return RunRepository(storage_dir=storage_dir)


@lru_cache()
def get_trigger_service() -> TriggerService:
    """Get trigger service singleton (file-based)."""
    return TriggerService(
        repository=get_run_repository(),
        workspace_manager=get_workspace_manager(),
    )


@lru_cache()
def get_trigger_agent() -> TriggerAgent:
    """Get trigger agent singleton."""
    return TriggerAgent(service=get_trigger_service())


@lru_cache()
def get_browser_manager() -> BrowserManager:
    """Get browser manager singleton."""
    settings = get_settings()
    return BrowserManager(
        browser_type=settings.playwright.playwright_browser,
        headless=settings.playwright.playwright_headless,
        timeout=settings.playwright.playwright_timeout,
    )


@lru_cache()
def get_crawler_service() -> CrawlerService:
    """Get crawler service singleton."""
    return CrawlerService(browser_manager=get_browser_manager())


@lru_cache()
def get_crawler_agent() -> CrawlerAgent:
    """Get crawler agent singleton."""
    return CrawlerAgent(service=get_crawler_service())


@lru_cache()
def get_inventory_aggregator_service() -> InventoryAggregatorService:
    """Get inventory aggregator service singleton."""
    return InventoryAggregatorService()


@lru_cache()
def get_llm_client() -> OpenAIClient:
    """Get LLM client singleton."""
    return OpenAIClient()


@lru_cache()
def get_test_design_service() -> TestDesignService:
    """Get test design service singleton."""
    return TestDesignService()


@lru_cache()
def get_test_design_agent() -> TestDesignAgent:
    """Get test design agent singleton."""
    return TestDesignAgent(
        service=get_test_design_service(),
        llm_client=get_llm_client(),
    )


@lru_cache()
def get_code_generation_agent():
    """Get code generation agent singleton."""
    from app.agents.code_generation_agent import CodeGenerationAgent
    return CodeGenerationAgent(llm_client=get_llm_client())


@lru_cache()
def get_human_review_service() -> HumanReviewService:
    """Get human review service singleton."""
    return HumanReviewService()


# ===================================================================
# Project & Dashboard dependencies (new)
# ===================================================================


@lru_cache()
def get_project_repository():
    """Get file-based project repository singleton."""
    from pathlib import Path
    from app.repositories.project_repository import ProjectRepository
    settings = get_settings()
    storage_dir = Path(settings.storage.storage_base_path) / "projects"
    storage_dir.mkdir(parents=True, exist_ok=True)
    return ProjectRepository(storage_dir=storage_dir)


@lru_cache()
def get_project_service() -> ProjectService:
    """Get project service singleton."""
    return ProjectService(
        project_repository=get_project_repository(),
        run_repository=get_run_repository(),
    )


@lru_cache()
def get_dashboard_service() -> DashboardService:
    """Get dashboard service singleton."""
    return DashboardService(
        project_repository=get_project_repository(),
        run_repository=get_run_repository(),
    )


# ===================================================================
# Persistence-aware dependencies (new — additive only)
# ===================================================================


@lru_cache()
def get_persistence_config():
    """Get cached persistence configuration with feature flags."""
    from app.persistence.config import get_persistence_config as _get_pc
    return _get_pc()


@lru_cache()
def get_fs_run_repository() -> RunRepository:
    """Get file-based RunRepository (same as ``get_run_repository``).

    Explicit alias so dual-repo construction does not depend on
    the original function name.
    """
    return get_run_repository()


def get_dual_run_repository():
    """Get a ``DualRunRepository`` wrapping FS + PG backends.

    Returns ``None`` when ``postgres_enabled`` is ``False``,
    preserving existing filesystem-only behaviour.
    """
    cfg = get_persistence_config()
    if not cfg.postgres_enabled:
        return None

    from app.persistence.dual_run_repository import DualRunRepository
    from app.repositories.pg_run_repository import RunRepository as PgRunRepository

    fs_repo = get_fs_run_repository()
    pg_repo = PgRunRepository.__new__(PgRunRepository)
    return DualRunRepository(fs_repo=fs_repo, pg_repo=pg_repo, config=cfg)


def get_pg_run_repository():
    """Get PostgreSQL ``PgRunRepository`` (requires an active session).

    Returns ``None`` when ``postgres_enabled`` is ``False``.
    The caller (e.g. a dual-repo or a service with a UnitOfWork)
    is responsible for providing the ``AsyncSession``.
    """
    cfg = get_persistence_config()
    if not cfg.postgres_enabled:
        return None

    from app.repositories.pg_run_repository import RunRepository as PgRunRepository
    return PgRunRepository

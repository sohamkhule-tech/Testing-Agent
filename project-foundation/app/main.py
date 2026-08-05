"""
FastAPI Application Factory

Creates and configures FastAPI application instance.
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.middleware import (
    CorrelationIDMiddleware,
    ExceptionHandlerMiddleware,
    RequestLoggingMiddleware,
    SensitiveDataScrubberMiddleware,
)
from app.api.routes import dashboard_router, events_router, projects_router, trigger_router, workflow_router
from app.config import get_settings
from app.constants import Constants
from app.logging import configure_logging, get_logger

logger = get_logger("app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """
    Application lifespan manager.

    Handles startup and shutdown events.
    """
    # Startup
    settings = get_settings()
    logger.info(
        "application_startup",
        version=Constants.VERSION,
        environment=settings.app.environment,
    )

    # Validate persistence feature flag combinations.
    # Fail fast with a clear message if the configuration is invalid.
    from app.persistence.startup_validator import validate_current_config

    try:
        validate_current_config()
        logger.info(
            "persistence_config_valid",
            filesystem_enabled=settings.persistence.filesystem_enabled,
            postgres_enabled=settings.persistence.postgres_enabled,
            dual_write_enabled=settings.persistence.dual_write_enabled,
            database_read_enabled=settings.persistence.database_read_enabled,
        )
    except Exception as exc:
        logger.error("persistence_config_invalid", error=str(exc))
        raise

    # Validate all required dependencies and imports are available
    # Catches missing imports (like asyncio) at startup rather than runtime
    from app.validation.startup_checks import run_all_startup_checks

    try:
        run_all_startup_checks()
        logger.info("startup_validation_passed")
    except Exception as exc:
        logger.error("startup_validation_failed", error=str(exc))
        raise

    yield

    # Shutdown
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    """
    Create and configure FastAPI application.

    Returns:
        Configured FastAPI application
    """
    # Configure logging
    settings = get_settings()
    configure_logging()

    # Create FastAPI app
    app = FastAPI(
        title="Enterprise AI Agentic Testing Platform",
        description="Automated testing platform with AI agents and workflow orchestration",
        version=Constants.VERSION,
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Custom middleware (order matters - first added = outermost)
    app.add_middleware(ExceptionHandlerMiddleware)
    app.add_middleware(SensitiveDataScrubberMiddleware)
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(CorrelationIDMiddleware)

    # Register routers
    app.include_router(health_router)
    app.include_router(dashboard_router, prefix="/api/v1")
    app.include_router(projects_router, prefix="/api/v1")
    app.include_router(trigger_router, prefix="/api/v1")
    app.include_router(workflow_router, prefix="/api/v1")
    app.include_router(events_router, prefix="/api/v1")

    logger.info("application_configured", version=Constants.VERSION)

    return app


# Application instance
app = create_app()

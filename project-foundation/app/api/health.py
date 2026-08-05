"""
Health Check API Endpoints

Provides system health and status endpoints.
"""

from datetime import datetime

from fastapi import APIRouter

from app.constants import Constants
from app.models import HealthCheckResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get("/", response_model=HealthCheckResponse)
async def health_check() -> HealthCheckResponse:
    """
    Basic health check endpoint.

    Includes persistence mode and feature flag status.
    """
    components = {
        "api": "healthy",
        "storage": "healthy",
        "validation": "healthy",
    }

    # Additive: include persistence status when the module is available
    try:
        from app.persistence.rollout_manager import get_rollout_manager

        rollout = get_rollout_manager()
        summary = rollout.summary
        components["persistence"] = summary["mode"]
        if summary["writes_to_postgres"]:
            components["postgres_writes"] = "enabled"
        if summary["reads_from_postgres"]:
            components["postgres_reads"] = "enabled"
    except ImportError:
        pass

    return HealthCheckResponse(
        status="healthy",
        version=Constants.VERSION,
        timestamp=datetime.utcnow(),
        components=components,
    )


@router.get("/ready", response_model=HealthCheckResponse)
async def readiness_check() -> HealthCheckResponse:
    """
    Readiness check for Kubernetes/load balancers.

    Returns:
        Readiness status
    """
    components = {
        "api": "ready",
        "storage": "ready",
        "validation": "ready",
    }
    try:
        from app.persistence.rollout_manager import get_rollout_manager

        summary = get_rollout_manager().summary
        components["persistence"] = summary["mode"]
    except ImportError:
        pass

    return HealthCheckResponse(
        status="ready",
        version=Constants.VERSION,
        timestamp=datetime.utcnow(),
        components=components,
    )


@router.get("/live", response_model=HealthCheckResponse)
async def liveness_check() -> HealthCheckResponse:
    """
    Liveness check for Kubernetes/load balancers.
    """
    return HealthCheckResponse(
        status="live",
        version=Constants.VERSION,
        timestamp=datetime.utcnow(),
        components={"api": "live"},
    )


@router.get("/db")
async def database_health():
    """
    Detailed database and persistence health status.

    Returns information about connection pool, rollout mode,
    and metrics counters.  This endpoint is additive and does
    not change the basic health contract.
    """
    result = {
        "status": "unknown",
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        from app.persistence.rollout_manager import get_rollout_manager
        from app.persistence.metrics import persistence_metrics
        from app.infrastructure.database import check_database_health

        # Rollout state
        rollout = get_rollout_manager()
        result["rollout"] = rollout.summary

        # Database connectivity
        health = await check_database_health()
        result["connectivity"] = health
        result["status"] = health["status"]

        # Metrics snapshot
        result["metrics"] = persistence_metrics.snapshot()

        # Migration info
        try:
            from alembic.script import ScriptDirectory
            from alembic.config import Config

            alembic_cfg = Config("alembic.ini")
            script = ScriptDirectory.from_config(alembic_cfg)
            result["migration"] = {
                "head": script.get_current_head(),
                "heads": script.get_heads(),
            }
        except Exception:
            result["migration"] = {"error": "unavailable"}

    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    return result

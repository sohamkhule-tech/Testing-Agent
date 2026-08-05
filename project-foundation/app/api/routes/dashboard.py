from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_dashboard_service
from app.logging import get_logger
from app.schemas.project import DashboardStats, ProjectResponse, TestRunResponse
from app.services.dashboard_service import DashboardService

logger = get_logger("api.dashboard")

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_dashboard_stats(
    service: DashboardService = Depends(get_dashboard_service),
) -> DashboardStats:
    try:
        return await service.get_stats()
    except Exception as e:
        logger.error("dashboard_stats_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get dashboard stats")


@router.get("/recent-runs", response_model=list[TestRunResponse])
async def get_recent_runs(
    limit: int = Query(default=10, ge=1, le=100),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[TestRunResponse]:
    try:
        return await service.get_recent_runs(limit=limit)
    except Exception as e:
        logger.error("dashboard_recent_runs_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get recent runs"
        )


@router.get("/recent-projects", response_model=list[ProjectResponse])
async def get_recent_projects(
    limit: int = Query(default=5, ge=1, le=50),
    service: DashboardService = Depends(get_dashboard_service),
) -> list[ProjectResponse]:
    try:
        return await service.get_recent_projects(limit=limit)
    except Exception as e:
        logger.error("dashboard_recent_projects_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get recent projects"
        )

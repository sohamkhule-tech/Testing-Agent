from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_project_service
from app.exceptions import NotFoundError, ValidationError
from app.logging import get_logger
from app.schemas.project import CreateProjectRequest, ProjectResponse, ProjectStats, RunListResponse
from app.services.project_service import ProjectService

logger = get_logger("api.projects")

router = APIRouter(prefix="/projects", tags=["Projects"])


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    service: ProjectService = Depends(get_project_service),
) -> list[ProjectResponse]:
    try:
        return await service.list_projects()
    except Exception as e:
        logger.error("list_projects_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list projects")


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    request: CreateProjectRequest,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        return await service.create_project(request)
    except ValidationError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("create_project_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create project")


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        return await service.get_project(project_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("get_project_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get project")


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: UUID,
    data: CreateProjectRequest,
    service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        return await service.update_project(project_id, data.model_dump(exclude_unset=True))
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("update_project_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to update project")


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    service: ProjectService = Depends(get_project_service),
) -> None:
    try:
        await service.delete_project(project_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("delete_project_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to delete project")


@router.get("/{project_id}/stats", response_model=ProjectStats)
async def get_project_stats(
    project_id: UUID,
    service: ProjectService = Depends(get_project_service),
) -> ProjectStats:
    try:
        return await service.get_project_stats(project_id)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("get_project_stats_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get project stats")


@router.get("/{project_id}/runs", response_model=RunListResponse)
async def get_project_runs(
    project_id: UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: ProjectService = Depends(get_project_service),
) -> RunListResponse:
    try:
        return await service.get_project_runs_paginated(project_id, page=page, page_size=page_size)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except Exception as e:
        logger.error("get_project_runs_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to get project runs")


# ---------------------------------------------------------------------------
# Phase 2 — Project default prompt endpoints
# ---------------------------------------------------------------------------

from pydantic import BaseModel as _BaseModel, Field as _Field


class _PromptUpdateRequest(_BaseModel):
    default_prompt_text: str = _Field(..., max_length=10000)


@router.get("/{project_id}/prompt", summary="Get project default prompt")
async def get_project_prompt(
    project_id: UUID,
    service: ProjectService = Depends(get_project_service),
) -> dict:
    try:
        entity = await service.project_repo.get_by_id(project_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Project not found")
        return {
            "project_id": str(project_id),
            "default_prompt_text": getattr(entity, "default_prompt_text", None) or "",
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_project_prompt_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to get project prompt")


@router.put("/{project_id}/prompt", summary="Save project default prompt")
async def update_project_prompt(
    project_id: UUID,
    body: _PromptUpdateRequest,
    service: ProjectService = Depends(get_project_service),
) -> dict:
    try:
        entity = await service.project_repo.get_by_id(project_id)
        if not entity:
            raise HTTPException(status_code=404, detail="Project not found")
        entity.default_prompt_text = body.default_prompt_text
        await service.project_repo.update(entity)
        return {
            "project_id": str(project_id),
            "default_prompt_text": entity.default_prompt_text,
            "updated_at": entity.updated_at.isoformat() if entity.updated_at else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("update_project_prompt_failed", project_id=str(project_id), error=str(e))
        raise HTTPException(status_code=500, detail="Failed to update project prompt")

import pytest
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from app.services.project_service import ProjectService
from app.domain.project import ProjectEntity
from app.exceptions import NotFoundError


@pytest.mark.asyncio
async def test_delete_project_success():
    project_id = uuid4()
    project_repo = AsyncMock()
    run_repo = AsyncMock()

    mock_project = MagicMock(spec=ProjectEntity)
    mock_project.id = project_id

    project_repo.get_by_id.return_value = mock_project
    project_repo.delete.return_value = True

    service = ProjectService(project_repository=project_repo, run_repository=run_repo)
    await service.delete_project(project_id)

    project_repo.get_by_id.assert_called_once_with(project_id)
    project_repo.delete.assert_called_once_with(project_id)


@pytest.mark.asyncio
async def test_delete_project_not_found():
    project_id = uuid4()
    project_repo = AsyncMock()
    run_repo = AsyncMock()

    project_repo.get_by_id.return_value = None

    service = ProjectService(project_repository=project_repo, run_repository=run_repo)

    with pytest.raises(NotFoundError):
        await service.delete_project(project_id)

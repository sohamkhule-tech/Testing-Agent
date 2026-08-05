from datetime import datetime
from pathlib import Path
from typing import Dict
from uuid import UUID

from app.core.interfaces import IRepository
from app.domain.project import ProjectEntity
from app.exceptions import NotFoundError, StorageError
from app.logging import LoggerMixin
from app.utils import load_file, save_file


class ProjectRepository(IRepository[ProjectEntity, UUID], LoggerMixin):
    def __init__(self, storage_dir: Path) -> None:
        super().__init__()
        self.storage_dir = storage_dir
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._cache: Dict[UUID, ProjectEntity] = {}

    def _get_project_file(self, project_id: UUID) -> Path:
        return self.storage_dir / f"{project_id}.json"

    async def create(self, entity: ProjectEntity) -> ProjectEntity:
        try:
            self._cache[entity.id] = entity
            file_path = self._get_project_file(entity.id)
            data = entity.model_dump(mode="json")
            await save_file(file_path, data)
            self.logger.info("project_created", project_id=str(entity.id), name=entity.name)
            return entity
        except Exception as e:
            self.logger.error("project_create_failed", project_id=str(entity.id), error=str(e))
            raise StorageError(f"Failed to create project: {str(e)}")

    async def get_by_id(self, entity_id: UUID) -> ProjectEntity | None:
        if entity_id in self._cache:
            return self._cache[entity_id]
        try:
            file_path = self._get_project_file(entity_id)
            if not file_path.exists():
                return None
            data = await load_file(file_path)
            entity = ProjectEntity(**data)
            self._cache[entity_id] = entity
            return entity
        except Exception as e:
            self.logger.error("project_load_failed", project_id=str(entity_id), error=str(e))
            return None

    async def update(self, entity: ProjectEntity) -> ProjectEntity:
        try:
            if not await self.exists(entity.id):
                raise NotFoundError(f"Project not found: {entity.id}", resource_id=str(entity.id))
            entity.updated_at = datetime.utcnow()
            self._cache[entity.id] = entity
            file_path = self._get_project_file(entity.id)
            data = entity.model_dump(mode="json")
            await save_file(file_path, data)
            self.logger.info("project_updated", project_id=str(entity.id))
            return entity
        except NotFoundError:
            raise
        except Exception as e:
            self.logger.error("project_update_failed", project_id=str(entity.id), error=str(e))
            raise StorageError(f"Failed to update project: {str(e)}")

    async def delete(self, entity_id: UUID) -> bool:
        try:
            if entity_id in self._cache:
                del self._cache[entity_id]
            file_path = self._get_project_file(entity_id)
            if file_path.exists():
                file_path.unlink()
                self.logger.info("project_deleted", project_id=str(entity_id))
                return True
            return False
        except Exception as e:
            self.logger.error("project_delete_failed", project_id=str(entity_id), error=str(e))
            return False

    async def exists(self, entity_id: UUID) -> bool:
        if entity_id in self._cache:
            return True
        return self._get_project_file(entity_id).exists()

    async def list_all(self) -> list[ProjectEntity]:
        projects = []
        try:
            for file_path in self.storage_dir.glob("*.json"):
                data = await load_file(file_path)
                entity = ProjectEntity(**data)
                self._cache[entity.id] = entity
                projects.append(entity)
            projects.sort(key=lambda p: p.updated_at or p.created_at, reverse=True)
            return projects
        except Exception as e:
            self.logger.error("project_list_failed", error=str(e))
            return list(self._cache.values())

    async def list_recent(self, limit: int = 10) -> list[ProjectEntity]:
        all_projects = await self.list_all()
        return all_projects[:limit]

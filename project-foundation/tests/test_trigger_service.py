"""
Unit Tests for Trigger Service

Tests for trigger service business logic.
"""

import pytest
from pathlib import Path
from uuid import UUID

from app.constants import RunStatus
from app.exceptions import NotFoundError, ValidationError
from app.infrastructure import WorkspaceManager
from app.repositories import RunRepository
from app.schemas import CreateRunRequest, TargetApplicationInput
from app.services import TriggerService


@pytest.fixture
def repository(tmp_path):
    """Create run repository for testing."""
    return RunRepository(storage_dir=tmp_path / "metadata")


@pytest.fixture
def workspace_manager():
    """Create workspace manager for testing."""
    return WorkspaceManager()


@pytest.fixture
def trigger_service(repository, workspace_manager):
    """Create trigger service for testing."""
    return TriggerService(
        repository=repository,
        workspace_manager=workspace_manager,
    )


@pytest.fixture
def sample_request():
    """Create sample run request."""
    return CreateRunRequest(
        target_application=TargetApplicationInput(
            base_url="https://example.com",
            environment="staging",
        ),
        requested_by="test@example.com",
    )


class TestTriggerService:
    """Test trigger service functionality."""

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_service_initialization(self, trigger_service):
        """Test service can be initialized."""
        await trigger_service.initialize()
        assert trigger_service.repository is not None
        assert trigger_service.workspace_manager is not None

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_run_success(self, trigger_service, sample_request):
        """Test run creation succeeds."""
        entity, context = await trigger_service.create_run(sample_request)

        assert entity is not None
        assert entity.run_id is not None
        assert entity.status == RunStatus.PENDING
        assert entity.requested_by == "test@example.com"
        assert context is not None
        assert context.workspace_root.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_run_generates_unique_ids(self, trigger_service, sample_request):
        """Test each run gets unique IDs."""
        entity1, _ = await trigger_service.create_run(sample_request)
        entity2, _ = await trigger_service.create_run(sample_request)

        assert entity1.run_id != entity2.run_id
        assert entity1.request_id != entity2.request_id

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_run_success(self, trigger_service, sample_request):
        """Test retrieving run by ID."""
        entity, _ = await trigger_service.create_run(sample_request)

        retrieved = await trigger_service.get_run(entity.run_id)

        assert retrieved.run_id == entity.run_id
        assert retrieved.requested_by == entity.requested_by

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_run_not_found(self, trigger_service):
        """Test get run raises NotFoundError for nonexistent run."""
        fake_id = UUID("12345678-1234-1234-1234-123456789012")

        with pytest.raises(NotFoundError):
            await trigger_service.get_run(fake_id)

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_get_metadata_success(self, trigger_service, sample_request):
        """Test retrieving run metadata."""
        entity, _ = await trigger_service.create_run(sample_request)

        metadata = await trigger_service.get_metadata(entity.run_id)

        assert metadata.run_id == entity.run_id
        assert metadata.status == entity.status
        assert metadata.requested_by == entity.requested_by

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_update_status_success(self, trigger_service, sample_request):
        """Test updating run status."""
        entity, _ = await trigger_service.create_run(sample_request)

        success = await trigger_service.update_status(
            run_id=entity.run_id,
            status=RunStatus.RUNNING,
            stage="testing",
            progress=50,
            message="Test in progress",
        )

        assert success is True

        updated = await trigger_service.get_run(entity.run_id)
        assert updated.status == RunStatus.RUNNING
        assert updated.current_stage == "testing"
        assert updated.progress_percent == 50
        assert updated.message == "Test in progress"

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_run_creates_workspace(self, trigger_service, sample_request):
        """Test run creation creates workspace directories."""
        entity, context = await trigger_service.create_run(sample_request)

        assert context.workspace_root.exists()
        assert context.artifacts_dir.exists()
        assert context.logs_dir.exists()
        assert context.reports_dir.exists()
        assert context.metadata_dir.exists()
        assert context.contracts_dir.exists()
        assert context.screenshots_dir.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_run_saves_test_run_request(self, trigger_service, sample_request):
        """Test run creation saves test-run-request.json."""
        entity, context = await trigger_service.create_run(sample_request)

        contract_file = context.contracts_dir / "test-run-request.json"
        assert contract_file.exists()

    @pytest.mark.unit
    @pytest.mark.asyncio
    async def test_create_run_saves_metadata(self, trigger_service, sample_request):
        """Test run creation saves execution metadata."""
        entity, context = await trigger_service.create_run(sample_request)

        metadata_file = context.metadata_dir / "execution.json"
        assert metadata_file.exists()

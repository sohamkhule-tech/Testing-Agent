"""
Run Domain Models

Domain entities for test run management.
"""

from datetime import datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants import RunStatus
from app.models import TimestampedModel


class RunMetadata(BaseModel):
    """
    Metadata for a test run.

    Tracks execution context and operational data.
    """

    run_id: UUID = Field(..., description="Unique run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    requested_by: str = Field(..., description="Requesting principal")
    workspace_path: str = Field(..., description="Run workspace directory")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    status: RunStatus = Field(default=RunStatus.PENDING, description="Current status")
    current_stage: str | None = Field(None, description="Current pipeline stage")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Progress")
    message: str | None = Field(None, description="Status message")
    error: str | None = Field(None, description="Error message if failed")

    model_config = ConfigDict(frozen=False, validate_assignment=True, use_enum_values=True)

    def update_status(
        self,
        status: RunStatus,
        stage: str | None = None,
        progress: int | None = None,
        message: str | None = None,
        error: str | None = None,
    ) -> None:
        """Update run status and metadata."""
        self.status = status
        self.updated_at = datetime.utcnow()
        if stage is not None:
            self.current_stage = stage
        if progress is not None:
            self.progress_percent = progress
        if message is not None:
            self.message = message
        if error is not None:
            self.error = error


class RunContext(BaseModel):
    """
    Runtime execution context for a test run.

    Contains paths, identifiers, and execution parameters.
    """

    run_id: UUID = Field(..., description="Run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    correlation_id: str = Field(..., description="Trace correlation ID")
    workspace_root: Path = Field(..., description="Run workspace root")
    artifacts_dir: Path = Field(..., description="Artifacts directory")
    logs_dir: Path = Field(..., description="Logs directory")
    reports_dir: Path = Field(..., description="Reports directory")
    metadata_dir: Path = Field(..., description="Metadata directory")
    contracts_dir: Path = Field(..., description="Contracts directory")
    screenshots_dir: Path = Field(..., description="Screenshots directory")

    model_config = ConfigDict(frozen=False, arbitrary_types_allowed=True)

    @classmethod
    def create(cls, run_id: UUID, request_id: UUID, correlation_id: str, base_workspace: Path) -> "RunContext":
        """
        Create run context with directory structure.

        Args:
            run_id: Run identifier
            request_id: Request correlation ID
            correlation_id: Trace correlation ID
            base_workspace: Base workspace directory

        Returns:
            Initialized run context
        """
        workspace_root = base_workspace / "runs" / str(run_id)
        return cls(
            run_id=run_id,
            request_id=request_id,
            correlation_id=correlation_id,
            workspace_root=workspace_root,
            artifacts_dir=workspace_root / "artifacts",
            logs_dir=workspace_root / "logs",
            reports_dir=workspace_root / "reports",
            metadata_dir=workspace_root / "metadata",
            contracts_dir=workspace_root / "contracts",
            screenshots_dir=workspace_root / "screenshots",
        )


class RunEntity(TimestampedModel):
    """
    Run entity for persistence.

    Complete representation of a test run.
    """

    run_id: UUID = Field(..., description="Unique run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    project_id: UUID | None = Field(None, description="Associated project ID")
    requested_by: str = Field(..., description="Requesting principal")
    workspace_path: str = Field(..., description="Workspace directory")
    status: RunStatus = Field(default=RunStatus.PENDING, description="Current status")
    current_stage: str | None = Field(None, description="Current pipeline stage")
    progress_percent: int = Field(default=0, description="Progress percentage")
    message: str | None = Field(None, description="Status message")
    error: str | None = Field(None, description="Error message")
    test_run_request: dict = Field(..., description="Canonical test run request")
    # Prompt fields (Phase 1 — Prompt Persistence)
    user_prompt_text: str | None = Field(None, description="User prompt with credentials redacted")
    user_prompt_redacted_text: str | None = Field(None, description="Display-safe redacted prompt")
    prompt_context_json: dict | None = Field(None, description="Parsed ParsedPromptIntent as dict")
    prompt_version: str | None = Field(None, description="Prompt template version tag")
    # ── Checkpoint / resume fields ──
    completed_stages: list[str] | None = Field(None, description="Ordered list of successfully completed stage names")
    last_completed_stage: str | None = Field(None, description="Most recent completed stage name")
    failed_stage: str | None = Field(None, description="Stage that failed (if any)")
    resume_allowed: bool = Field(default=False, description="Whether the run can be resumed")
    artifact_paths: dict[str, str] | None = Field(None, description="Map of stage name -> primary artifact path")
    stage_logs: dict[str, list[str]] | None = Field(None, description="Per-stage log lines captured during execution")

    model_config = ConfigDict(frozen=False, validate_assignment=True, use_enum_values=True)

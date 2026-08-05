"""
Trigger Agent Request/Response Schemas

DTOs for test run creation and management following test-run-request.json contract.
"""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.constants import RunStatus


class TargetApplicationInput(BaseModel):
    """Target application configuration."""

    application_id: UUID | None = Field(
        None, description="ID of previously registered application"
    )
    application_name: str | None = Field(
        None, min_length=1, max_length=128, description="Name for unregistered application"
    )
    base_url: HttpUrl = Field(..., description="Base URL of target application")
    environment: Literal["development", "staging", "production"] = Field(
        default="staging", description="Deployment environment"
    )

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class ExecutionModeInput(BaseModel):
    """Execution mode configuration."""

    crawl_strategy: Literal["full", "incremental", "skip"] = Field(
        default="full", description="How crawler approaches application"
    )
    test_level: Literal["smoke", "regression"] = Field(
        default="regression", description="Depth of test generation"
    )

    model_config = ConfigDict(populate_by_name=True)


class AuthenticationInput(BaseModel):
    """Authentication configuration."""

    required: bool = Field(default=False, description="Whether auth is required")
    login_strategy: Literal["form", "api", "basic", "oauth", "sso", "none"] | None = Field(
        None, description="Authentication mechanism"
    )
    credentials_ref: UUID | None = Field(
        None, description="Reference to stored credentials"
    )
    login_url: HttpUrl | None = Field(None, description="Login page URL")

    model_config = ConfigDict(populate_by_name=True)


class ScopeInput(BaseModel):
    """Crawl scope configuration."""

    include_pages: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="URL patterns to include",
    )
    exclude_pages: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="URL patterns to exclude",
    )
    include_apis: bool = Field(default=True, description="Discover API endpoints")
    max_crawl_depth: int = Field(
        default=5, ge=1, le=20, description="Maximum crawl depth"
    )
    max_pages: int = Field(
        default=50, ge=1, le=500, description="Maximum pages to crawl"
    )

    model_config = ConfigDict(populate_by_name=True)


class AIConfigInput(BaseModel):
    """AI model configuration."""

    model: str = Field(
        default="deepseek-r1-distill-qwen-8b",
        min_length=1,
        max_length=128,
        description="LLM model name",
    )
    temperature: float = Field(
        default=0.2, ge=0.0, le=1.0, description="Sampling temperature"
    )
    reasoning_level: Literal["low", "medium", "high"] = Field(
        default="medium", description="AI reasoning depth"
    )

    model_config = ConfigDict(populate_by_name=True)


class ExecutionConfigInput(BaseModel):
    """Execution runtime configuration."""

    timeout: int = Field(
        default=300, ge=30, le=3600, description="Run timeout in seconds"
    )
    retries: int = Field(
        default=1, ge=0, le=5, description="Failed test retry count"
    )
    parallelism: int = Field(
        default=1, ge=1, le=10, description="Parallel test workers"
    )
    browser: Literal["chromium", "firefox", "webkit"] = Field(
        default="chromium", description="Browser engine"
    )
    headless: bool = Field(default=True, description="Headless browser mode")

    model_config = ConfigDict(populate_by_name=True)


class OutputConfigInput(BaseModel):
    """Output and artifact configuration."""

    workspace: str | None = Field(
        None, min_length=1, max_length=256, description="Workspace directory override"
    )
    artifact_retention: Literal["run", "day", "week", "month"] = Field(
        default="run", description="Artifact retention policy"
    )

    model_config = ConfigDict(populate_by_name=True)


class MetadataInput(BaseModel):
    """User-defined metadata."""

    tags: list[str] = Field(
        default_factory=list,
        max_length=20,
        description="Run categorization tags",
    )
    notes: str | None = Field(
        None, max_length=2000, description="Free-text run notes"
    )

    model_config = ConfigDict(populate_by_name=True)


class CreateRunRequest(BaseModel):
    """
    Request to create a new test run.

    Based on test-run-request.json contract input section.
    """

    request_id: UUID | None = Field(
        None, description="Client idempotency key"
    )
    requested_by: str | None = Field(
        None, min_length=1, max_length=256, description="User/service identifier"
    )
    target_application: TargetApplicationInput = Field(
        ..., description="Target application configuration"
    )
    execution_mode: ExecutionModeInput = Field(
        default_factory=ExecutionModeInput, description="Execution mode"
    )
    authentication: AuthenticationInput = Field(
        default_factory=AuthenticationInput, description="Auth configuration"
    )
    scope: ScopeInput = Field(
        default_factory=ScopeInput, description="Crawl scope"
    )
    ai: AIConfigInput = Field(
        default_factory=AIConfigInput, description="AI configuration"
    )
    execution: ExecutionConfigInput = Field(
        default_factory=ExecutionConfigInput, description="Execution config"
    )
    output: OutputConfigInput = Field(
        default_factory=OutputConfigInput, description="Output config"
    )
    metadata: MetadataInput = Field(
        default_factory=MetadataInput, description="User metadata"
    )

    model_config = ConfigDict(populate_by_name=True)


class TestRunRequest(BaseModel):
    """
    Canonical test run request artifact.

    Produced by Trigger Agent, consumed by downstream agents.
    Follows test-run-request.json contract.
    """

    run_id: UUID = Field(..., description="Unique run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    created_at: datetime = Field(..., description="Creation timestamp")
    requested_by: str = Field(
        ..., min_length=1, max_length=256, description="Requesting principal"
    )
    target_application: TargetApplicationInput = Field(
        ..., description="Target application"
    )
    execution_mode: ExecutionModeInput = Field(..., description="Execution mode")
    authentication: AuthenticationInput = Field(..., description="Authentication")
    scope: ScopeInput = Field(..., description="Scope")
    ai: AIConfigInput = Field(..., description="AI config")
    execution: ExecutionConfigInput = Field(..., description="Execution config")
    output: OutputConfigInput = Field(..., description="Output config")
    metadata: MetadataInput = Field(..., description="Metadata")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class RunResponse(BaseModel):
    """Response for run creation and queries."""

    run_id: UUID = Field(..., description="Unique run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    status: RunStatus = Field(..., description="Current run status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    requested_by: str = Field(..., description="Requesting principal")
    workspace_path: str | None = Field(None, description="Workspace directory path")
    message: str | None = Field(None, description="Status message")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class RunStatusResponse(BaseModel):
    """Detailed run status response."""

    run_id: UUID = Field(..., description="Run identifier")
    status: RunStatus = Field(..., description="Current status")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    current_stage: str | None = Field(None, description="Current pipeline stage")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    message: str | None = Field(None, description="Status message")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

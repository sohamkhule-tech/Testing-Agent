"""
Base Pydantic Models and Schemas

Foundation models for requests, responses, and domain entities.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.constants import RunStatus


class BaseDTO(BaseModel):
    """Base Data Transfer Object."""

    model_config = ConfigDict(
        frozen=False,
        validate_assignment=True,
        use_enum_values=True,
        populate_by_name=True,
    )


class TimestampedModel(BaseDTO):
    """Model with timestamp fields."""

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class BaseResponse(BaseDTO):
    """Base API response model."""

    success: bool = Field(..., description="Whether the operation was successful")
    message: str = Field(..., description="Response message")
    correlation_id: str | None = Field(None, description="Request correlation ID")


class SuccessResponse(BaseResponse):
    """Success response with optional data."""

    success: bool = Field(default=True)
    data: dict[str, Any] | None = Field(None, description="Response data")


class ErrorResponse(BaseResponse):
    """Error response with error details."""

    success: bool = Field(default=False)
    error_code: str = Field(..., description="Error code")
    error_details: dict[str, Any] | None = Field(None, description="Error details")


class PaginatedResponse(BaseDTO):
    """Paginated response model."""

    items: list[Any] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Number of items per page")
    total_pages: int = Field(..., description="Total number of pages")


class HealthCheckResponse(BaseDTO):
    """Health check response."""

    status: str = Field(..., description="Service status")
    version: str = Field(..., description="Service version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: dict[str, str] = Field(
        default_factory=dict, description="Component health status"
    )


class RunRequest(BaseDTO):
    """Base request for starting a run."""

    run_id: str | None = Field(None, description="Optional run ID")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Run configuration"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Run metadata"
    )


class RunResponse(TimestampedModel):
    """Response for run operations."""

    run_id: str = Field(..., description="Unique run identifier")
    status: RunStatus = Field(..., description="Run status")
    result: dict[str, Any] | None = Field(None, description="Run result data")
    error: str | None = Field(None, description="Error message if failed")


class ArtifactMetadata(TimestampedModel):
    """Metadata for stored artifacts."""

    artifact_id: str = Field(..., description="Unique artifact identifier")
    artifact_type: str = Field(..., description="Type of artifact")
    size_bytes: int = Field(..., description="Size in bytes")
    checksum: str | None = Field(None, description="Content checksum")
    tags: dict[str, str] = Field(
        default_factory=dict, description="Custom tags"
    )


class ValidationResult(BaseDTO):
    """Result of validation operation."""

    is_valid: bool = Field(..., description="Whether validation passed")
    errors: list[str] = Field(default_factory=list, description="Validation errors")
    warnings: list[str] = Field(default_factory=list, description="Validation warnings")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional validation metadata"
    )

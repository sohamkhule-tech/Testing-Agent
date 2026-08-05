from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.constants import RunStatus


class ProjectResponse(BaseModel):
    id: UUID = Field(..., description="Unique project identifier")
    name: str = Field(..., description="Project name")
    description: str | None = Field(None, description="Project description")
    application_url: str = Field(..., description="Target application URL")
    auth_type: str | None = Field(None, description="Authentication type")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    total_runs: int = Field(default=0, description="Total number of runs")
    last_run_at: datetime | None = Field(None, description="Last run timestamp")
    last_run_status: RunStatus | None = Field(None, description="Last run status")
    pending_reviews: int = Field(default=0, description="Pending reviews")
    tags: list[str] = Field(default_factory=list, description="Project tags")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=256, description="Project name")
    description: str | None = Field(None, description="Project description")
    application_url: str = Field(..., description="Target application URL")
    starting_urls: list[str] = Field(default_factory=list, description="Starting URLs for crawling")
    auth_type: str | None = Field(None, description="Authentication type")
    max_pages: int | None = Field(None, ge=1, le=1000, description="Maximum pages to crawl")
    max_depth: int | None = Field(None, ge=1, le=20, description="Maximum crawl depth")
    include_patterns: list[str] = Field(default_factory=list, description="URL patterns to include")
    exclude_patterns: list[str] = Field(default_factory=list, description="URL patterns to exclude")
    tags: list[str] = Field(default_factory=list, description="Project tags")

    model_config = ConfigDict(populate_by_name=True)


class ProjectStats(BaseModel):
    total_pages_crawled: int = Field(default=0, description="Total pages crawled")
    total_forms_discovered: int = Field(default=0, description="Total forms discovered")
    total_scenarios_generated: int = Field(default=0, description="Total scenarios generated")
    total_runs: int = Field(default=0, description="Total runs")
    successful_runs: int = Field(default=0, description="Successful runs")
    failed_runs: int = Field(default=0, description="Failed runs")
    average_duration_seconds: float = Field(default=0.0, description="Average run duration")

    model_config = ConfigDict(populate_by_name=True)


class DashboardStats(BaseModel):
    total_projects: int = Field(default=0, description="Total projects")
    total_runs: int = Field(default=0, description="Total runs")
    active_runs: int = Field(default=0, description="Active runs")
    pending_reviews: int = Field(default=0, description="Pending reviews")
    completed_today: int = Field(default=0, description="Runs completed today")
    success_rate: float = Field(default=0.0, description="Success rate percentage")

    model_config = ConfigDict(populate_by_name=True)


class RunListResponse(BaseModel):
    runs: list["TestRunResponse"] = Field(default_factory=list, description="List of runs")
    total: int = Field(default=0, description="Total number of runs")
    page: int = Field(default=1, description="Current page")
    page_size: int = Field(default=20, description="Page size")

    model_config = ConfigDict(populate_by_name=True)


class TestRunResponse(BaseModel):
    run_id: UUID = Field(..., description="Unique run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    project_id: UUID | None = Field(None, description="Associated project ID")
    status: RunStatus = Field(..., description="Current run status")
    current_phase: str | None = Field(None, description="Current workflow phase")
    started_at: datetime | None = Field(None, description="Start timestamp")
    completed_at: datetime | None = Field(None, description="Completion timestamp")
    duration_seconds: float | None = Field(None, description="Duration in seconds")
    requested_by: str | None = Field(None, description="Requesting principal")
    workspace_path: str | None = Field(None, description="Workspace directory path")
    pages_visited: int | None = Field(None, description="Pages visited")
    scenarios_generated: int | None = Field(None, description="Scenarios generated")
    review_status: str | None = Field(None, description="Review status")
    error_message: str | None = Field(None, description="Error message if failed")

    model_config = ConfigDict(populate_by_name=True, use_enum_values=True)

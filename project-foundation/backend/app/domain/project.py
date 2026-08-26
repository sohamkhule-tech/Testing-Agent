from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.constants import RunStatus
from app.models import TimestampedModel


class ProjectEntity(TimestampedModel):
    id: UUID = Field(..., description="Unique project identifier")
    name: str = Field(..., min_length=1, max_length=256, description="Project name")
    description: str | None = Field(None, description="Project description")
    application_url: str = Field(..., description="Target application URL")
    auth_type: str | None = Field(None, description="Authentication type")
    tags: list[str] = Field(default_factory=list, description="Project tags")
    total_runs: int = Field(default=0, description="Total runs count")
    last_run_at: datetime | None = Field(None, description="Last run timestamp")
    last_run_status: RunStatus | None = Field(None, description="Last run status")
    pending_reviews: int = Field(default=0, description="Pending review count")
    # Phase 2 — project-level default prompt
    default_prompt_text: str | None = Field(None, description="Default AI test instructions for this project")

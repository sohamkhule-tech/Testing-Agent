"""
Review Schemas

Pydantic models for human review and approval workflow.
"""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ReviewStatus(str, Enum):
    """Review status enumeration."""

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ReviewDecision(str, Enum):
    """Review decision enumeration."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    PARTIAL_APPROVAL = "partial_approval"


class ScenarioReviewStatus(str, Enum):
    """Individual scenario review status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    DISABLED = "disabled"


class ReviewComment(BaseModel):
    """Review comment for a scenario or plan."""

    comment_id: UUID = Field(..., description="Unique comment identifier")
    reviewer_name: str = Field(..., max_length=256, description="Reviewer name")
    reviewer_email: str | None = Field(None, max_length=256, description="Reviewer email")
    comment_text: str = Field(..., max_length=4000, description="Comment content")
    created_at: datetime = Field(..., description="Comment timestamp")
    scenario_id: str | None = Field(None, max_length=64, description="Associated scenario ID")


class ScenarioReview(BaseModel):
    """Review record for individual scenario."""

    scenario_id: str = Field(..., max_length=64, description="Scenario identifier")
    status: ScenarioReviewStatus = Field(..., description="Review status")
    enabled: bool = Field(default=True, description="Whether scenario is enabled")
    comments: list[ReviewComment] = Field(default_factory=list, description="Scenario comments")
    modified: bool = Field(default=False, description="Whether scenario was modified")
    original_priority: str | None = Field(None, description="Original priority before edit")
    original_risk: str | None = Field(None, description="Original risk before edit")


class ReviewMetadata(BaseModel):
    """Metadata about the review process."""

    run_id: UUID = Field(..., description="Test run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    review_version: int = Field(default=1, ge=1, description="Review version number")
    review_status: ReviewStatus = Field(..., description="Overall review status")
    reviewer_name: str = Field(..., max_length=256, description="Primary reviewer name")
    reviewer_email: str | None = Field(None, max_length=256, description="Reviewer email")
    review_started_at: datetime = Field(..., description="Review start timestamp")
    review_completed_at: datetime | None = Field(None, description="Review completion timestamp")
    approval_date: datetime | None = Field(None, description="Approval timestamp")
    decision: ReviewDecision | None = Field(None, description="Final review decision")
    review_duration_seconds: int | None = Field(None, ge=0, description="Review duration")
    
    # Summary statistics
    total_scenarios: int = Field(default=0, ge=0, description="Total scenarios reviewed")
    approved_scenarios: int = Field(default=0, ge=0, description="Approved scenario count")
    rejected_scenarios: int = Field(default=0, ge=0, description="Rejected scenario count")
    modified_scenarios: int = Field(default=0, ge=0, description="Modified scenario count")
    disabled_scenarios: int = Field(default=0, ge=0, description="Disabled scenario count")
    added_scenarios: int = Field(default=0, ge=0, description="Added scenario count")
    removed_scenarios: int = Field(default=0, ge=0, description="Removed scenario count")
    
    # Comments and notes
    general_comments: list[ReviewComment] = Field(default_factory=list, description="General review comments")
    approval_summary: str | None = Field(None, max_length=2000, description="Approval summary")
    
    # Version history reference
    previous_version: int | None = Field(None, ge=1, description="Previous version number")


class ApprovedTestPlan(BaseModel):
    """Approved test plan after human review."""

    # Inherit all fields from TestPlan but add review metadata
    run_id: UUID = Field(..., description="Test run identifier")
    request_id: UUID = Field(..., description="Request correlation ID")
    generated_at: datetime = Field(..., description="Original plan generation timestamp")
    approved_at: datetime = Field(..., description="Approval timestamp")
    review_version: int = Field(default=1, ge=1, description="Review version")
    review_status: ReviewStatus = Field(..., description="Review status")
    reviewer_name: str = Field(..., max_length=256, description="Reviewer name")
    
    # Original test plan data (simplified for now, can be expanded)
    test_plan_data: dict[str, Any] = Field(..., description="Complete test plan data")
    scenario_reviews: dict[str, ScenarioReview] = Field(
        default_factory=dict,
        description="Per-scenario review data"
    )
    
    model_config = {"frozen": False}

    @property
    def test_scenarios(self) -> list:
        """Access test scenarios from test_plan_data for backward compatibility."""
        if not self.test_plan_data or not isinstance(self.test_plan_data, dict):
            return []
        return self.test_plan_data.get("test_scenarios", self.test_plan_data.get("scenarios", []))

    @property
    def modules(self) -> list:
        """Access modules from test_plan_data for backward compatibility."""
        if not self.test_plan_data or not isinstance(self.test_plan_data, dict):
            return []
        return self.test_plan_data.get("modules", [])


class ReviewRequest(BaseModel):
    """Request to perform human review."""

    run_id: UUID = Field(..., description="Test run identifier")
    reviewer_name: str = Field(..., min_length=1, max_length=256, description="Reviewer name")
    reviewer_email: str | None = Field(None, max_length=256, description="Reviewer email")
    auto_approve: bool = Field(default=False, description="Auto-approve without modifications")
    scenario_decisions: dict[str, ScenarioReviewStatus] | None = Field(
        None,
        description="Per-scenario review decisions"
    )
    general_comments: str | None = Field(None, max_length=2000, description="General review notes")

"""
Design Domain ORM Models

test_plans, test_scenarios, human_reviews
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.models.enums import ReviewDecisionType, ReviewStatusType


# ===================================================================
# TestPlan
# ===================================================================


class TestPlan(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "test_plans"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    status: Mapped[str] = mapped_column(ReviewStatusType(32), nullable=False)
    model_used: Mapped[str | None] = mapped_column(nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    module_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    scenario_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    estimated_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    coverage_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    application_summary: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    json_path: Mapped[str] = mapped_column(nullable=False)
    md_path: Mapped[str | None] = mapped_column(nullable=True)
    superseded_at: Mapped[datetime | None] = mapped_column(nullable=True)

    run: Mapped[Run] = relationship("Run", back_populates="test_plans")
    scenarios: Mapped[list[TestScenario]] = relationship(
        "TestScenario", back_populates="test_plan", cascade="all, delete-orphan"
    )
    reviews: Mapped[list[HumanReview]] = relationship(
        "HumanReview", back_populates="test_plan", cascade="all, delete-orphan"
    )
    ir_documents: Mapped[list[IRDocument]] = relationship(
        "IRDocument", back_populates="test_plan", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_test_plans_run_id", "run_id"),
        Index("idx_test_plans_is_latest", "is_latest"),
        UniqueConstraint("run_id", "version", name="uq_test_plans_run_version"),
    )


# ===================================================================
# TestScenario
# ===================================================================


class TestScenario(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "test_scenarios"

    test_plan_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("test_plans.id"), nullable=False
    )
    scenario_id: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[str] = mapped_column(nullable=False)
    category: Mapped[str] = mapped_column(nullable=False)
    module_name: Mapped[str] = mapped_column(nullable=False)
    target_page: Mapped[str | None] = mapped_column(nullable=True)
    risk_level: Mapped[str] = mapped_column(nullable=False)
    preconditions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    test_steps: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    required_test_data: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tags: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    dependencies: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    test_plan: Mapped[TestPlan] = relationship("TestPlan", back_populates="scenarios")

    __table_args__ = (
        Index("idx_test_scenarios_plan_id", "test_plan_id"),
        Index("idx_test_scenarios_category", "category"),
        Index("idx_test_scenarios_priority", "priority"),
        Index("idx_test_scenarios_module", "module_name"),
        Index("idx_test_scenarios_risk_level", "risk_level"),
        UniqueConstraint("test_plan_id", "scenario_id", name="uq_test_scenarios_plan_scenario"),
    )


# ===================================================================
# HumanReview
# ===================================================================


class HumanReview(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "human_reviews"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    test_plan_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("test_plans.id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(ReviewStatusType(32), nullable=False)
    decision: Mapped[str | None] = mapped_column(ReviewDecisionType(32), nullable=True)
    reviewer_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    reviewer_name: Mapped[str] = mapped_column(nullable=False)
    reviewer_email: Mapped[str | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_scenarios: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    approved_scenarios: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    rejected_scenarios: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    modified_scenarios: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    disabled_scenarios: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    decision_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    general_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    approval_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    auto_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_plan_path: Mapped[str] = mapped_column(nullable=False)
    approved_md_path: Mapped[str | None] = mapped_column(nullable=True)
    review_metadata_path: Mapped[str] = mapped_column(nullable=False)

    run: Mapped[Run] = relationship("Run", back_populates="human_reviews")
    test_plan: Mapped[TestPlan] = relationship("TestPlan", back_populates="reviews")
    reviewer: Mapped[User | None] = relationship(
        "User", back_populates="reviews_done", foreign_keys=[reviewer_id]
    )

    __table_args__ = (
        Index("idx_human_reviews_run_id", "run_id"),
        Index("idx_human_reviews_reviewer_id", "reviewer_id"),
        Index("idx_human_reviews_status", "status"),
        UniqueConstraint("run_id", "version", name="uq_human_reviews_run_version"),
    )

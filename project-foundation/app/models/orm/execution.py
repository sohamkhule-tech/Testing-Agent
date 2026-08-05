"""
Execution Domain ORM Models

executions, test_results
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.models.enums import ExecutionStatusType, TestStatusType, TriggerTypeType


# ===================================================================
# Execution
# ===================================================================


class Execution(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "executions"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    project_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("generated_projects.id"), nullable=True
    )
    triggered_by: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(TriggerTypeType(32), nullable=False)
    environment_name: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(ExecutionStatusType(32), nullable=False)
    browser: Mapped[str] = mapped_column(nullable=False)
    headless: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    total_tests: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_skipped: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tests_flaky: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pass_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    total_duration_seconds: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )
    health_score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    health_status: Mapped[str | None] = mapped_column(nullable=True)
    metrics_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    playwright_exit_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    artifacts_path: Mapped[str] = mapped_column(nullable=False)
    reports_path: Mapped[str] = mapped_column(nullable=False)
    execution_logs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    run: Mapped[Run] = relationship("Run", back_populates="executions")
    generated_project: Mapped[GeneratedProject | None] = relationship(
        "GeneratedProject", back_populates="executions", foreign_keys=[project_id]
    )
    # triggered_by_user is a back-reference; not required since User.executions doesn't exist
    test_results: Mapped[list[TestResult]] = relationship(
        "TestResult", back_populates="execution", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_executions_run_id", "run_id", unique=True),
        Index("idx_executions_status", "status"),
        Index("idx_executions_trigger_type", "trigger_type"),
        Index("idx_executions_created_at", "created_at"),
        Index("idx_executions_pass_rate", "pass_rate"),
    )


# ===================================================================
# TestResult
# ===================================================================


class TestResult(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "test_results"

    execution_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("executions.id"), nullable=False
    )
    title: Mapped[str] = mapped_column(nullable=False)
    file: Mapped[str | None] = mapped_column(nullable=True)
    line: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(TestStatusType(32), nullable=False)
    duration_ms: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    browser: Mapped[str | None] = mapped_column(nullable=True)
    retry_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    was_retried: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    original_status: Mapped[str | None] = mapped_column(TestStatusType(32), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_stack: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    retry_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    artifact_refs: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    annotations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    execution: Mapped[Execution] = relationship("Execution", back_populates="test_results")

    __table_args__ = (
        Index("idx_test_results_execution_id", "execution_id"),
        Index("idx_test_results_execution_status", "execution_id", "status"),
        Index("idx_test_results_title", "title"),
        UniqueConstraint(
            "execution_id", "title", "file",
            name="uq_test_results_exec_title_file",
        ),
    )

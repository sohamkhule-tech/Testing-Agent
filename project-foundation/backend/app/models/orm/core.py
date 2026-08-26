"""
Core Domain ORM Models

users, projects, runs
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Integer, Numeric, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    RunStatusType,
    TriggerTypeType,
    UserRoleType,
    UserStatusType,
)


# ===================================================================
# User
# ===================================================================


class User(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "users"

    tenant_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False)
    email: Mapped[str] = mapped_column(nullable=False)
    display_name: Mapped[str] = mapped_column(nullable=False)
    role: Mapped[str] = mapped_column(UserRoleType(32), nullable=False)
    status: Mapped[str] = mapped_column(UserStatusType(32), nullable=False)
    avatar_url: Mapped[str | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(nullable=True)

    projects_created: Mapped[list[Project]] = relationship(
        "Project", back_populates="creator", foreign_keys="Project.created_by"
    )
    runs_requested: Mapped[list[Run]] = relationship(
        "Run", back_populates="requester", foreign_keys="Run.requested_by"
    )
    reviews_done: Mapped[list[HumanReview]] = relationship(
        "HumanReview", back_populates="reviewer", foreign_keys="HumanReview.reviewer_id"
    )
    audit_entries: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="actor", foreign_keys="AuditLog.actor_id"
    )

    __table_args__ = (
        Index("idx_users_email", "email", postgresql_where="deleted_at IS NULL"),
        Index("idx_users_tenant_id", "tenant_id"),
        Index("idx_users_role", "role"),
    )


# ===================================================================
# Project
# ===================================================================


class Project(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    tenant_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_url: Mapped[str] = mapped_column(nullable=False)
    environment: Mapped[str] = mapped_column(nullable=False)
    created_by: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    default_browser: Mapped[str] = mapped_column(nullable=False)
    default_timeout: Mapped[int] = mapped_column(nullable=False)
    authentication_type: Mapped[str | None] = mapped_column(nullable=True)
    repository_url: Mapped[str | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    creator: Mapped[User | None] = relationship(
        "User", back_populates="projects_created", foreign_keys=[created_by]
    )
    runs: Mapped[list[Run]] = relationship("Run", back_populates="project")

    __table_args__ = (
        Index("idx_projects_name", "name", postgresql_where="deleted_at IS NULL"),
        Index("idx_projects_tenant_id", "tenant_id"),
        Index("idx_projects_created_by", "created_by"),
        Index("idx_projects_environment", "environment"),
    )


# ===================================================================
# Run
# ===================================================================


class Run(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "runs"

    run_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False, unique=True)
    tenant_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False)
    project_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("projects.id"), nullable=True
    )
    request_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    trigger_type: Mapped[str] = mapped_column(TriggerTypeType(32), nullable=False)
    trigger_source: Mapped[str | None] = mapped_column(nullable=True)
    environment_name: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(RunStatusType(32), nullable=False)
    current_stage: Mapped[str | None] = mapped_column(nullable=True)
    progress_percent: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    workspace_path: Mapped[str] = mapped_column(nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    node_execution: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)

    project: Mapped[Project | None] = relationship("Project", back_populates="runs")
    requester: Mapped[User | None] = relationship(
        "User", back_populates="runs_requested", foreign_keys=[requested_by]
    )

    crawl_packages: Mapped[list[CrawlPackage]] = relationship(
        "CrawlPackage", back_populates="run", cascade="all, delete-orphan"
    )
    inventories: Mapped[list[Inventory]] = relationship(
        "Inventory", back_populates="run", cascade="all, delete-orphan"
    )
    test_plans: Mapped[list[TestPlan]] = relationship(
        "TestPlan", back_populates="run", cascade="all, delete-orphan"
    )
    human_reviews: Mapped[list[HumanReview]] = relationship(
        "HumanReview", back_populates="run", cascade="all, delete-orphan"
    )
    ir_documents: Mapped[list[IRDocument]] = relationship(
        "IRDocument", back_populates="run", cascade="all, delete-orphan"
    )
    generated_projects: Mapped[list[GeneratedProject]] = relationship(
        "GeneratedProject", back_populates="run", cascade="all, delete-orphan"
    )
    executions: Mapped[list[Execution]] = relationship(
        "Execution", back_populates="run", cascade="all, delete-orphan"
    )
    artifacts: Mapped[list[Artifact]] = relationship(
        "Artifact", back_populates="run", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("idx_runs_run_id", "run_id"),
        Index("idx_runs_tenant_project", "tenant_id", "project_id", "created_at"),
        Index("idx_runs_status", "status"),
        Index("idx_runs_trigger_source", "trigger_source"),
        Index("idx_runs_created_at", "created_at"),
        Index("idx_runs_requested_by", "requested_by"),
    )

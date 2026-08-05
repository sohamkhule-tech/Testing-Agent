"""
Generation Domain ORM Models

ir_documents, generated_projects
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, SmallInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.models.enums import GenerationStatusType


# ===================================================================
# IRDocument
# ===================================================================


class IRDocument(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "ir_documents"

    test_plan_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("test_plans.id"), nullable=False
    )
    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_latest: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ir_schema_version: Mapped[str] = mapped_column(nullable=False)
    valid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    validation_warnings: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    refinement_attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    total_pages: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    total_elements: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    total_flows: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    total_modules: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    model_used: Mapped[str | None] = mapped_column(nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prompt_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    ir_path: Mapped[str] = mapped_column(nullable=False)
    dep_graph_path: Mapped[str | None] = mapped_column(nullable=True)

    test_plan: Mapped[TestPlan] = relationship("TestPlan", back_populates="ir_documents")
    run: Mapped[Run] = relationship("Run", back_populates="ir_documents")
    generated_project: Mapped[GeneratedProject | None] = relationship(
        "GeneratedProject", back_populates="ir_document", uselist=False
    )

    __table_args__ = (
        Index("idx_ir_documents_run_id", "run_id"),
        Index("idx_ir_documents_is_latest", "is_latest"),
        UniqueConstraint("test_plan_id", "version", name="uq_ir_documents_plan_version"),
    )


# ===================================================================
# GeneratedProject
# ===================================================================


class GeneratedProject(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "generated_projects"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    ir_document_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("ir_documents.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(GenerationStatusType(32), nullable=False)
    project_path: Mapped[str] = mapped_column(nullable=False)
    ir_path: Mapped[str | None] = mapped_column(nullable=True)
    metadata_path: Mapped[str] = mapped_column(nullable=False)
    files_data: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    files_generated: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    page_objects_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    test_files_count: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    scenarios_implemented: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    modules_covered: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    total_lines_of_code: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    validation_status: Mapped[str | None] = mapped_column(nullable=True)
    validation_errors: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    validation_warnings: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    generation_duration_seconds: Mapped[float] = mapped_column(
        Numeric(10, 2), nullable=False, default=0
    )
    model_used: Mapped[str | None] = mapped_column(nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    run: Mapped[Run] = relationship("Run", back_populates="generated_projects")
    ir_document: Mapped[IRDocument | None] = relationship(
        "IRDocument", back_populates="generated_project", foreign_keys=[ir_document_id]
    )
    executions: Mapped[list[Execution]] = relationship(
        "Execution", back_populates="generated_project"
    )

    __table_args__ = (
        Index("idx_generated_projects_run_id", "run_id", unique=True),
    )

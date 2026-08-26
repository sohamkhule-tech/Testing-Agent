"""
System Domain ORM Models

artifacts, audit_log
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as SA_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base, TimestampMixin, UUIDMixin
from app.models.enums import ArtifactTypeType, AuditActionType, StorageBackendType


# ===================================================================
# Artifact
# ===================================================================


class Artifact(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "artifacts"

    run_id: Mapped[UUID] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("runs.run_id"), nullable=False
    )
    execution_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("executions.id"), nullable=True
    )
    test_result_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("test_results.id"), nullable=True
    )
    artifact_type: Mapped[str] = mapped_column(ArtifactTypeType(32), nullable=False)
    file_name: Mapped[str] = mapped_column(nullable=False)
    file_path: Mapped[str] = mapped_column(nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    mime_type: Mapped[str | None] = mapped_column(nullable=True)
    checksum: Mapped[str | None] = mapped_column(nullable=True)
    storage_backend: Mapped[str] = mapped_column(StorageBackendType(32), nullable=False)
    storage_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, nullable=False, default=dict)
    deleted_at: Mapped[datetime | None] = mapped_column(nullable=True)

    run: Mapped[Run] = relationship("Run", back_populates="artifacts")
    execution: Mapped[Execution | None] = relationship(
        "Execution", foreign_keys=[execution_id]
    )
    test_result: Mapped[TestResult | None] = relationship(
        "TestResult", foreign_keys=[test_result_id]
    )

    __table_args__ = (
        Index("idx_artifacts_run_id", "run_id"),
        Index("idx_artifacts_type", "artifact_type"),
        Index("idx_artifacts_execution_id", "execution_id"),
        Index("idx_artifacts_storage_backend", "storage_backend"),
    )


# ===================================================================
# AuditLog
# ===================================================================


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    tenant_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False)
    action: Mapped[str] = mapped_column(AuditActionType(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(nullable=False)
    entity_id: Mapped[UUID] = mapped_column(SA_UUID(as_uuid=True), nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(
        SA_UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    actor_name: Mapped[str | None] = mapped_column(nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    ip_address: Mapped[str | None] = mapped_column(nullable=True)
    user_agent: Mapped[str | None] = mapped_column(nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False)

    actor: Mapped[User | None] = relationship(
        "User", back_populates="audit_entries", foreign_keys=[actor_id]
    )

    __table_args__ = (
        Index("idx_audit_log_created_at", "created_at"),
        Index("idx_audit_log_entity", "entity_type", "entity_id"),
        Index("idx_audit_log_action", "action"),
        Index("idx_audit_log_actor_id", "actor_id"),
        Index("idx_audit_log_tenant_id", "tenant_id"),
    )

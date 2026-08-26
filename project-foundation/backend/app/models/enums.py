"""
Database Enum Definitions & SQLAlchemy Type Decorators

Mirrors the enum values from ``app.constants`` for the persistence layer.
Each DB-facing enum has a corresponding ``TypeDecorator`` that handles
bidirectional conversion between Python enums and VARCHAR columns.

These are NOT ORM models — only type helpers for Phase 2.
"""

from __future__ import annotations

import enum
from typing import Any

from sqlalchemy import String
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.types import SchemaType, TypeDecorator


# ---------------------------------------------------------------------------
# Helper: factory that creates a TypeDecorator for a given Python Enum
# ---------------------------------------------------------------------------


def _make_enum_type(enum_cls: type[enum.Enum]) -> type[TypeDecorator]:
    """Return a ``TypeDecorator`` subclass that stores *enum_cls* as VARCHAR.

    Usage::

        RunStatusType = _make_enum_type(RunStatus)

        class RunModel(Base):
            __tablename__ = "runs"
            status: Mapped[RunStatus] = mapped_column(RunStatusType(32))
    """

    class EnumType(TypeDecorator):
        impl = String
        cache_ok = True

        def __init__(self, length: int = 32, **kwargs: Any) -> None:
            super().__init__(length=length, **kwargs)
            self.enum_cls = enum_cls

        def process_bind_param(self, value: Any, dialect: Dialect) -> str | None:
            if value is None:
                return None
            if isinstance(value, enum_cls):
                return value.value
            if isinstance(value, str):
                # Allow raw strings during transition
                return value
            raise TypeError(f"Expected {enum_cls.__name__}, got {type(value).__name__}")

        def process_result_value(self, value: Any, dialect: Dialect) -> enum.Enum | None:
            if value is None:
                return None
            return enum_cls(value)

        def copy(self, **kwargs: Any) -> EnumType:
            return EnumType(self.impl.length, **kwargs)

        # Make Alembic autogen detect changes correctly
        def __repr__(self) -> str:
            return f"{enum_cls.__name__}Type({self.impl.length})"

    return EnumType


# ===================================================================
# Enums — values kept in sync with app.constants
# ===================================================================


class RunStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class NodeStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class ExecutionStatus(str, enum.Enum):
    PENDING = "pending"
    INSTALLING = "installing"
    PREPARING = "preparing"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_FAILURES = "completed_with_failures"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class ReviewStatus(str, enum.Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    PARTIALLY_APPROVED = "partially_approved"
    CHANGES_REQUESTED = "changes_requested"
    REJECTED = "rejected"
    ARCHIVED = "archived"


class ReviewDecision(str, enum.Enum):
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_CHANGES = "request_changes"
    PARTIAL_APPROVAL = "partial_approval"


class GenerationStatus(str, enum.Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VALIDATION_FAILED = "validation_failed"


class TestStatus(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    FLAKY = "flaky"
    TIMEOUT = "timeout"


class FailureType(str, enum.Enum):
    LOCATOR_NOT_FOUND = "locator_not_found"
    TIMEOUT = "timeout"
    ASSERTION_FAILED = "assertion_failed"
    NETWORK_ERROR = "network_error"
    AUTH_FAILED = "auth_failed"
    NAVIGATION_ERROR = "navigation_error"
    UNEXPECTED_DIALOG = "unexpected_dialog"
    BROWSER_CRASH = "browser_crash"
    ENVIRONMENT_ERROR = "environment_error"
    MISSING_ELEMENT = "missing_element"
    UNKNOWN = "unknown"


class TriggerType(str, enum.Enum):
    MANUAL = "manual"
    API = "api"
    SCHEDULED = "scheduled"
    CI_CD = "ci_cd"
    WEBHOOK = "webhook"


class ArtifactType(str, enum.Enum):
    SCREENSHOT = "screenshot"
    VIDEO = "video"
    TRACE = "trace"
    LOG = "log"
    REPORT = "report"
    HAR = "har"
    METADATA = "metadata"
    OTHER = "other"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    REVIEWER = "reviewer"
    ENGINEER = "engineer"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"


class StorageBackend(str, enum.Enum):
    LOCAL = "local"
    S3 = "s3"
    AZURE_BLOB = "azure_blob"
    GCS = "gcs"
    MINIO = "minio"


class CrawlStatus(str, enum.Enum):
    COMPLETED = "completed"
    PARTIAL = "partial"
    TIMEOUT = "timeout"
    ERROR = "error"


class AuditAction(str, enum.Enum):
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"
    RUN_STARTED = "run.started"
    RUN_COMPLETED = "run.completed"
    RUN_FAILED = "run.failed"
    RUN_CANCELLED = "run.cancelled"
    REVIEW_APPROVED = "review.approved"
    REVIEW_REJECTED = "review.rejected"
    REVIEW_CHANGES_REQUESTED = "review.changes_requested"
    EXECUTION_STARTED = "execution.started"
    EXECUTION_COMPLETED = "execution.completed"
    ARTIFACT_DELETED = "artifact.deleted"
    CONFIGURATION_UPDATED = "configuration.updated"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_SUSPENDED = "user.suspended"


# ===================================================================
# SQLAlchemy Type Decorators (one per enum)
# ===================================================================

RunStatusType = _make_enum_type(RunStatus)
NodeStatusType = _make_enum_type(NodeStatus)
ExecutionStatusType = _make_enum_type(ExecutionStatus)
ReviewStatusType = _make_enum_type(ReviewStatus)
ReviewDecisionType = _make_enum_type(ReviewDecision)
GenerationStatusType = _make_enum_type(GenerationStatus)
TestStatusType = _make_enum_type(TestStatus)
FailureTypeType = _make_enum_type(FailureType)
TriggerTypeType = _make_enum_type(TriggerType)
ArtifactTypeType = _make_enum_type(ArtifactType)
UserRoleType = _make_enum_type(UserRole)
UserStatusType = _make_enum_type(UserStatus)
StorageBackendType = _make_enum_type(StorageBackend)
CrawlStatusType = _make_enum_type(CrawlStatus)
AuditActionType = _make_enum_type(AuditAction)


# ===================================================================
# Registry — for Alembic autogenerate support and introspection
# ===================================================================

ALL_ENUM_TYPES: dict[str, type[TypeDecorator]] = {
    "RunStatus": RunStatusType,
    "NodeStatus": NodeStatusType,
    "ExecutionStatus": ExecutionStatusType,
    "ReviewStatus": ReviewStatusType,
    "ReviewDecision": ReviewDecisionType,
    "GenerationStatus": GenerationStatusType,
    "TestStatus": TestStatusType,
    "FailureType": FailureTypeType,
    "TriggerType": TriggerTypeType,
    "ArtifactType": ArtifactTypeType,
    "UserRole": UserRoleType,
    "UserStatus": UserStatusType,
    "StorageBackend": StorageBackendType,
    "CrawlStatus": CrawlStatusType,
    "AuditAction": AuditActionType,
}

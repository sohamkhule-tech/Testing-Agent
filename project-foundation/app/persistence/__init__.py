"""Persistence infrastructure for gradual PostgreSQL migration.

Components
----------
PersistenceConfig
    Central configuration object with feature flags.

RepositoryProvider
    Factory that creates all 13 repositories from a single ``AsyncSession``.

UnitOfWork
    Context manager that owns an ``AsyncSession``, manages transactions,
    and exposes repositories through a ``RepositoryProvider``.

DualWriteMetrics / PostgresRetryPolicy
    Infrastructure for the dual-write strategy.

DualRunRepository / DualProjectRepository / DualUserRepository
    Dual-write repository implementations.

RolloutManager
    Reports the current rollout mode and validates state transitions.

PersistenceMetrics
    Operational counters, gauges, and latency trackers.

StartupValidator
    Validates feature flag combinations at application boot.
"""

from app.persistence.config import PersistenceConfig, get_persistence_config, persistence_config
from app.persistence.dual_base import BaseDualRepository, DualWriteMetrics, PostgresRetryPolicy
from app.persistence.dual_project_repository import DualProjectRepository
from app.persistence.dual_run_repository import DualRunRepository
from app.persistence.dual_user_repository import DualUserRepository
from app.persistence.metrics import PersistenceMetrics, persistence_metrics
from app.persistence.rollout_manager import (
    PersistenceMode,
    RolloutManager,
    get_rollout_manager,
    rollout_manager,
)
from app.persistence.repository_provider import RepositoryProvider
from app.persistence.startup_validator import (
    validate_current_config,
    validate_feature_flags,
)
from app.persistence.unit_of_work import UnitOfWork

__all__ = [
    "BaseDualRepository",
    "DualProjectRepository",
    "DualRunRepository",
    "DualUserRepository",
    "DualWriteMetrics",
    "get_persistence_config",
    "get_rollout_manager",
    "persistence_config",
    "PersistenceConfig",
    "PersistenceMetrics",
    "persistence_metrics",
    "PersistenceMode",
    "PostgresRetryPolicy",
    "RepositoryProvider",
    "RolloutManager",
    "rollout_manager",
    "UnitOfWork",
    "validate_current_config",
    "validate_feature_flags",
]

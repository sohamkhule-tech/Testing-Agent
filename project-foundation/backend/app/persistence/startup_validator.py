"""
Startup Configuration Validation

Validates persistence feature flag combinations at application startup.
Fails fast with clear error messages if the configuration is invalid.

Validation rules:

    * ``dual_write_enabled`` requires ``filesystem_enabled`` AND ``postgres_enabled``.
    * ``database_read_enabled`` requires ``postgres_enabled``.
    * At least one write backend (filesystem or PostgreSQL) must be enabled.
"""

from __future__ import annotations

from app.exceptions.base import ConfigurationError


# Error message templates — kept as constants for testability
_REQUIRES_BOTH = (
    "Cannot enable dual_write_enabled when "
    "filesystem_enabled={fs} and postgres_enabled={pg}. "
    "Both must be True."
)
_REQUIRES_POSTGRES = (
    "Cannot enable database_read_enabled when "
    "postgres_enabled={pg}. "
    "PostgreSQL must be enabled to read from it."
)
_NO_BACKEND = (
    "At least one write backend must be enabled. "
    "Set filesystem_enabled=True or postgres_enabled=True."
)


def validate_feature_flags(
    filesystem_enabled: bool,
    postgres_enabled: bool,
    dual_write_enabled: bool,
    database_read_enabled: bool,
) -> None:
    """Validate persistence feature flag combinations.

    Args:
        filesystem_enabled: Whether filesystem persistence is active.
        postgres_enabled: Whether PostgreSQL persistence is active.
        dual_write_enabled: Whether dual-write (FS + PG) is active.
        database_read_enabled: Whether to read from PostgreSQL.

    Raises:
        ConfigurationError: If any combination is invalid.
            The error message describes exactly which flags are
            misconfigured and what the correct values should be.
    """
    if dual_write_enabled and not (filesystem_enabled and postgres_enabled):
        raise ConfigurationError(
            _REQUIRES_BOTH.format(fs=filesystem_enabled, pg=postgres_enabled)
        )

    if database_read_enabled and not postgres_enabled:
        raise ConfigurationError(
            _REQUIRES_POSTGRES.format(pg=postgres_enabled)
        )

    if not filesystem_enabled and not postgres_enabled:
        raise ConfigurationError(_NO_BACKEND)


def validate_current_config() -> None:
    """Shortcut that reads the current ``PersistenceConfig`` and validates it.

    Call this during application startup::

        from app.persistence.startup_validator import validate_current_config

        validate_current_config()
    """
    from app.persistence.config import get_persistence_config

    cfg = get_persistence_config()
    validate_feature_flags(
        filesystem_enabled=cfg.filesystem_enabled,
        postgres_enabled=cfg.postgres_enabled,
        dual_write_enabled=cfg.dual_write_enabled,
        database_read_enabled=cfg.database_read_enabled,
    )

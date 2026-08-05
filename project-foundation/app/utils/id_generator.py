"""
ID and Token Generation Utilities

Provides utilities for generating unique identifiers.
"""

import secrets
import uuid
from datetime import datetime


def generate_uuid() -> str:
    """
    Generate a UUID4 string.

    Returns:
        UUID string

    Example:
        >>> id = generate_uuid()
        >>> # "550e8400-e29b-41d4-a716-446655440000"
    """
    return str(uuid.uuid4())


def generate_correlation_id() -> str:
    """
    Generate a correlation ID for request tracking.

    Returns:
        Correlation ID

    Example:
        >>> corr_id = generate_correlation_id()
    """
    return generate_uuid()


def generate_run_id(prefix: str = "run") -> str:
    """
    Generate a run ID with timestamp.

    Args:
        prefix: Prefix for the run ID

    Returns:
        Run ID

    Example:
        >>> run_id = generate_run_id("test")
        >>> # "test_20240101_120000_abc123"
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    random_suffix = secrets.token_hex(4)
    return f"{prefix}_{timestamp}_{random_suffix}"


def generate_artifact_id(artifact_type: str) -> str:
    """
    Generate an artifact ID.

    Args:
        artifact_type: Type of artifact

    Returns:
        Artifact ID

    Example:
        >>> artifact_id = generate_artifact_id("crawl_package")
    """
    return generate_run_id(artifact_type)


def generate_api_key(length: int = 32) -> str:
    """
    Generate a random API key.

    Args:
        length: Length of the key

    Returns:
        API key

    Example:
        >>> api_key = generate_api_key()
    """
    return secrets.token_urlsafe(length)


def generate_short_id(length: int = 8) -> str:
    """
    Generate a short random ID.

    Args:
        length: Length of the ID

    Returns:
        Short ID

    Example:
        >>> short_id = generate_short_id()
    """
    return secrets.token_hex(length // 2)

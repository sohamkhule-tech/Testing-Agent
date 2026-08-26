"""
Artifact Management

Centralized registry for all run artifacts — inventory files,
screenshots, generated code, reports, execution logs, etc.
"""

from app.agent.artifacts.artifact_registry import ArtifactRegistry, ArtifactRecord, ArtifactType
from app.agent.artifacts.registry_backend import LocalFilesystemBackend

__all__ = [
    "ArtifactRegistry",
    "ArtifactRecord",
    "ArtifactType",
    "LocalFilesystemBackend",
]

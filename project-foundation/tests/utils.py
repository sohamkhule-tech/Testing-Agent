"""
Test Utilities and Helpers

Provides utility functions for tests.
"""

import json
from pathlib import Path
from typing import Any


def create_test_file(path: Path, content: str | bytes) -> None:
    """
    Create a test file with content.

    Args:
        path: File path
        content: File content
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)


def create_test_json_file(path: Path, data: dict[str, Any]) -> None:
    """
    Create a test JSON file.

    Args:
        path: File path
        data: JSON data
    """
    create_test_file(path, json.dumps(data, indent=2))


def assert_json_structure(data: dict, expected_keys: set[str]) -> None:
    """
    Assert JSON has expected structure.

    Args:
        data: JSON data
        expected_keys: Expected keys
    """
    actual_keys = set(data.keys())
    assert actual_keys >= expected_keys, f"Missing keys: {expected_keys - actual_keys}"


class MockLLMClient:
    """Mock LLM client for testing."""

    def __init__(self, responses: list[str] | None = None):
        """
        Initialize mock client.

        Args:
            responses: List of responses to return
        """
        self.responses = responses or ["Mock response"]
        self.call_count = 0
        self.calls = []

    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> str:
        """Return mock response."""
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, **kwargs})
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return response

    async def complete_structured(
        self,
        prompt: str,
        response_model: type,
        **kwargs: Any,
    ) -> Any:
        """Return mock structured response."""
        self.calls.append({"prompt": prompt, "response_model": response_model, **kwargs})
        # Return minimal instance
        return response_model()

    async def stream_complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ):
        """Async generator yielding the mock response as a single chunk."""
        self.calls.append({"prompt": prompt, "system_prompt": system_prompt, **kwargs})
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        yield response


class MockStorage:
    """Mock storage for testing."""

    def __init__(self):
        """Initialize mock storage."""
        self.storage = {}
        self.metadata = {}

    async def save(
        self, artifact_id: str, content: bytes, metadata: dict | None = None
    ) -> str:
        """Save to memory."""
        self.storage[artifact_id] = content
        self.metadata[artifact_id] = metadata or {}
        return f"mock://{artifact_id}"

    async def load(self, artifact_id: str) -> bytes:
        """Load from memory."""
        if artifact_id not in self.storage:
            raise KeyError(f"Artifact not found: {artifact_id}")
        return self.storage[artifact_id]

    async def exists(self, artifact_id: str) -> bool:
        """Check existence."""
        return artifact_id in self.storage

    async def delete(self, artifact_id: str) -> bool:
        """Delete from memory."""
        if artifact_id in self.storage:
            del self.storage[artifact_id]
            if artifact_id in self.metadata:
                del self.metadata[artifact_id]
            return True
        return False

    async def get_metadata(self, artifact_id: str) -> dict:
        """Get metadata."""
        return self.metadata.get(artifact_id, {})

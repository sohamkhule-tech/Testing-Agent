"""
Unit Tests for Utilities

Tests for utility modules.
"""

import pytest

from app.utils import (
    dumps,
    generate_correlation_id,
    generate_run_id,
    generate_uuid,
    loads,
    merge_dicts,
)


class TestJSONUtils:
    """Test JSON utilities."""

    @pytest.mark.unit
    def test_dumps_loads_roundtrip(self):
        """Test JSON serialization roundtrip."""
        data = {"key": "value", "number": 42, "nested": {"inner": "data"}}
        json_str = dumps(data)
        result = loads(json_str)
        assert result == data

    @pytest.mark.unit
    def test_dumps_with_indent(self):
        """Test JSON serialization with indentation."""
        data = {"key": "value"}
        json_str = dumps(data, indent=True)
        assert "\n" in json_str

    @pytest.mark.unit
    def test_merge_dicts(self):
        """Test dictionary merging."""
        base = {"a": 1, "b": {"c": 2}}
        update = {"b": {"d": 3}, "e": 4}
        result = merge_dicts(base, update)

        assert result["a"] == 1
        assert result["b"]["c"] == 2
        assert result["b"]["d"] == 3
        assert result["e"] == 4


class TestIDGenerator:
    """Test ID generation utilities."""

    @pytest.mark.unit
    def test_generate_uuid_format(self):
        """Test UUID generation format."""
        uuid = generate_uuid()
        assert isinstance(uuid, str)
        assert len(uuid) == 36
        assert uuid.count("-") == 4

    @pytest.mark.unit
    def test_generate_uuid_unique(self):
        """Test UUIDs are unique."""
        uuid1 = generate_uuid()
        uuid2 = generate_uuid()
        assert uuid1 != uuid2

    @pytest.mark.unit
    def test_generate_correlation_id(self):
        """Test correlation ID generation."""
        corr_id = generate_correlation_id()
        assert isinstance(corr_id, str)
        assert len(corr_id) > 0

    @pytest.mark.unit
    def test_generate_run_id_format(self):
        """Test run ID format."""
        run_id = generate_run_id("test")
        assert run_id.startswith("test_")
        parts = run_id.split("_")
        assert len(parts) >= 3

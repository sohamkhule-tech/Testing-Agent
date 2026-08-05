"""
JSON Utilities

Provides robust JSON serialization and deserialization.
"""

import json
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any

import orjson
from pydantic import BaseModel

from app.exceptions import ValidationError
from app.logging import get_logger

logger = get_logger("utils.json")


def default_serializer(obj: Any) -> Any:
    """
    Default serializer for JSON encoding.

    Args:
        obj: Object to serialize

    Returns:
        Serializable representation

    Raises:
        TypeError: If object cannot be serialized
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, BaseModel):
        return obj.model_dump()
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def dumps(obj: Any, *, indent: bool = False, sort_keys: bool = False) -> str:
    """
    Serialize object to JSON string using orjson.

    Args:
        obj: Object to serialize
        indent: Whether to indent output
        sort_keys: Whether to sort keys

    Returns:
        JSON string

    Example:
        >>> data = {"name": "test", "value": 123}
        >>> json_str = dumps(data, indent=True)
    """
    options = 0
    if indent:
        options |= orjson.OPT_INDENT_2
    if sort_keys:
        options |= orjson.OPT_SORT_KEYS

    try:
        return orjson.dumps(obj, default=default_serializer, option=options).decode()
    except Exception as e:
        logger.error("json_serialization_failed", error=str(e), object_type=type(obj).__name__)
        raise ValidationError(f"Failed to serialize object to JSON: {str(e)}")


def loads(json_str: str) -> Any:
    """
    Deserialize JSON string to object using orjson.

    Args:
        json_str: JSON string

    Returns:
        Deserialized object

    Raises:
        ValidationError: If JSON is invalid

    Example:
        >>> json_str = '{"name": "test"}'
        >>> data = loads(json_str)
    """
    try:
        return orjson.loads(json_str)
    except Exception as e:
        logger.error("json_deserialization_failed", error=str(e))
        raise ValidationError(f"Failed to deserialize JSON: {str(e)}")


async def load_file(file_path: Path) -> Any:
    """
    Load JSON from file asynchronously.

    Args:
        file_path: Path to JSON file

    Returns:
        Deserialized object

    Raises:
        ValidationError: If file cannot be loaded

    Example:
        >>> data = await load_file(Path("config.json"))
    """
    import aiofiles

    try:
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            return loads(content)
    except FileNotFoundError:
        raise ValidationError(f"JSON file not found: {file_path}")
    except Exception as e:
        logger.error("json_file_load_failed", file_path=str(file_path), error=str(e))
        raise ValidationError(f"Failed to load JSON file {file_path}: {str(e)}")


async def save_file(file_path: Path, obj: Any, *, indent: bool = True) -> None:
    """
    Save object to JSON file asynchronously.

    Args:
        file_path: Path to save JSON file
        obj: Object to serialize
        indent: Whether to indent output

    Raises:
        ValidationError: If file cannot be saved

    Example:
        >>> await save_file(Path("output.json"), {"key": "value"})
    """
    import aiofiles

    try:
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Serialize to JSON
        json_str = dumps(obj, indent=indent)

        # Write to file
        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json_str)

        logger.info("json_file_saved", file_path=str(file_path), size_bytes=len(json_str))
    except Exception as e:
        logger.error("json_file_save_failed", file_path=str(file_path), error=str(e))
        raise ValidationError(f"Failed to save JSON file {file_path}: {str(e)}")


def pretty_print(obj: Any) -> str:
    """
    Pretty print object as JSON.

    Args:
        obj: Object to print

    Returns:
        Pretty formatted JSON string

    Example:
        >>> print(pretty_print({"key": "value"}))
    """
    return dumps(obj, indent=True, sort_keys=True)


def merge_dicts(base: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively merge two dictionaries.

    Args:
        base: Base dictionary
        update: Dictionary with updates

    Returns:
        Merged dictionary

    Example:
        >>> base = {"a": 1, "b": {"c": 2}}
        >>> update = {"b": {"d": 3}}
        >>> result = merge_dicts(base, update)
        >>> # {"a": 1, "b": {"c": 2, "d": 3}}
    """
    result = base.copy()
    for key, value in update.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = merge_dicts(result[key], value)
        else:
            result[key] = value
    return result


def validate_json_structure(
    data: dict[str, Any], required_keys: set[str]
) -> bool:
    """
    Validate that JSON has required keys.

    Args:
        data: JSON data as dictionary
        required_keys: Set of required keys

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails

    Example:
        >>> data = {"name": "test", "value": 123}
        >>> validate_json_structure(data, {"name", "value"})
    """
    missing_keys = required_keys - set(data.keys())
    if missing_keys:
        raise ValidationError(
            f"Missing required keys in JSON: {', '.join(missing_keys)}",
            details={"missing_keys": list(missing_keys)},
        )
    return True

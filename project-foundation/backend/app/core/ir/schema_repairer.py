"""
Schema-aware IR Repairer

Applies deterministic, schema-derived repairs only: missing optional keys are
filled with their schema defaults and nothing else. Values are never invented
for required fields, and invalid values are never rewritten into "valid" ones
— those cases are surfaced to the LLM as validation feedback.
"""

from datetime import datetime
from enum import Enum
from typing import Any, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from app.logging import LoggerMixin
from app.schemas.ir import CodeGenerationIR


def _resolve_default(field: FieldInfo) -> Any:
    """Resolve a field's default value, or None if there is no safe default."""
    if field.is_required():
        return None
    if field.default_factory is not None:
        try:
            value = field.default_factory()
        except Exception:
            value = None
        return value if value is not None else None
    if field.default is not PydanticUndefined and field.default is not None:
        return field.default
    return None


def _normalize_default(value: Any) -> Any:
    """Convert a schema default into JSON-friendly form."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def _apply_defaults(value: Any, annotation: Any, inserted: list[str], path: str) -> Any:
    """Recursively fill missing optional keys with schema defaults."""
    if isinstance(value, dict):
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            for name, field in annotation.model_fields.items():
                child = value.get(name)
                if child is None:
                    default = _resolve_default(field)
                    if default is not None:
                        value[name] = _normalize_default(default)
                        child_path = f"{path}.{name}".lstrip(".")
                        if child_path not in inserted:
                            inserted.append(child_path)
                        child = value[name]
                if child is not None and isinstance(child, (dict, list)):
                    _apply_defaults(child, field.annotation, inserted, f"{path}.{name}".lstrip("."))
        return value
    if isinstance(value, list):
        origin = get_origin(annotation)
        if origin is list:
            args = get_args(annotation)
            inner = args[0] if args else Any
            for item in value:
                if isinstance(item, (dict, list)):
                    _apply_defaults(item, inner, inserted, path)
        return value
    return value


class SchemaAwareRepairer(LoggerMixin):
    """Applies schema-derived default repairs only; never fabricates values."""

    def __init__(self) -> None:
        """Initialize the repairer."""
        super().__init__()
        self.repairs_made: list[str] = []

    def repair(self, ir_data: dict[str, Any], model: type[BaseModel] = CodeGenerationIR) -> dict[str, Any]:
        """Fill missing optional keys with schema defaults.

        Args:
            ir_data: Parsed IR JSON dict
            model: Root schema model

        Returns:
            Repaired data (mutated in place)
        """
        self.repairs_made = []
        inserted: list[str] = []
        _apply_defaults(ir_data, model, inserted, "")
        self.repairs_made = sorted(set(inserted))

        self.logger.info(
            "schema_repair_complete",
            repairs=len(self.repairs_made),
        )
        return ir_data

"""
Schema Renderer for IR Generation

Renders the authoritative IR schema (from app.schemas.ir) as prompt text.
Everything is derived from the Pydantic models so the prompt never drifts
from the validated schema.
"""

import json
from datetime import datetime
from enum import Enum
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from app.logging import LoggerMixin
from app.schemas.ir import CodeGenerationIR


def _is_optional(annotation: Any) -> bool:
    """Check if an annotation is optional (allows None)."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        return any(a is type(None) for a in get_args(annotation))
    return False


def _type_name(annotation: Any) -> str:
    """Human-readable type name for a Pydantic field annotation."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        args = get_args(annotation)
        non_null = [a for a in args if a is not type(None)]
        if not non_null:
            return "null"
        base = _type_name(non_null[0]) if len(non_null) == 1 else " | ".join(_type_name(a) for a in non_null)
        if len(args) == 2 and len(non_null) == 1:
            return f"{base} | null"
        return base
    if origin is list:
        inner = get_args(annotation)
        item = _type_name(inner[0]) if inner else "any"
        return f"array[{item}]"
    if origin is dict:
        return "object"
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return "enum"
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation.__name__
    if isinstance(annotation, type):
        if issubclass(annotation, datetime):
            return "ISO 8601 datetime string"
        return annotation.__name__
    return str(annotation).replace("typing.", "")


def _enum_values(annotation: Any) -> list[Any]:
    """Return allowed values for an enum annotation (or empty list)."""
    origin = get_origin(annotation)
    if origin is Union or origin is UnionType:
        for arg in get_args(annotation):
            values = _enum_values(arg)
            if values:
                return values
        return []
    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return [member.value for member in annotation]
    return []


def _display_default(value: Any) -> str:
    """Serialize a default value for display in documentation."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str):
        return json.dumps(value)
    return json.dumps(value)


def _field_example(annotation: Any, field: FieldInfo, name: str) -> Any:
    """Build an example value for a field, preferring concrete defaults."""
    if field.is_required():
        return _example_for(annotation, name)

    if field.default_factory is not None:
        try:
            default = field.default_factory()
        except Exception:
            default = None
        if default is not None and not isinstance(default, (list, dict)):
            return default
        if isinstance(default, (list, dict)) and default:
            return default
        if isinstance(default, (list, dict)):
            origin = get_origin(annotation)
            if origin is list:
                inner = get_args(annotation)
                if inner and isinstance(inner[0], type) and issubclass(inner[0], BaseModel):
                    return [_example_for(inner[0], name)]
            return default
        return default

    if field.default is not PydanticUndefined and field.default is not None:
        return field.default

    return _example_for(annotation, name)


def _example_for(annotation: Any, name: str) -> Any:
    """Build a generic example value for an annotation."""
    if _is_optional(annotation):
        return None

    origin = get_origin(annotation)
    if origin is list:
        inner = get_args(annotation)
        if not inner:
            return []
        item = _example_for(inner[0], name)
        return [item] if item is not None else []
    if origin is dict:
        return {}

    if isinstance(annotation, type) and issubclass(annotation, Enum):
        return next(iter(annotation)).value
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return _model_example(annotation)
    if isinstance(annotation, type):
        if annotation is str:
            return f"<{name}>"
        if annotation is bool:
            return False
        if annotation is int:
            return 0
        if annotation is float:
            return 0.0
        if issubclass(annotation, datetime):
            return "2024-01-01T00:00:00Z"
    return None


def _model_example(model: type[BaseModel]) -> dict[str, Any]:
    """Build a nested example dict for a Pydantic model."""
    example: dict[str, Any] = {}
    for field_name, field in model.model_fields.items():
        example[field_name] = _field_example(field.annotation, field, field_name)
    return example


def _nested_models(ann: Any) -> list[type[BaseModel]]:
    """Collect nested BaseModel types from an annotation."""
    result: list[type[BaseModel]] = []
    origin = get_origin(ann)
    if origin is Union or origin is UnionType:
        for arg in get_args(ann):
            result.extend(_nested_models(arg))
    elif origin is list:
        inner = get_args(ann)
        if inner:
            result.extend(_nested_models(inner[0]))
    elif isinstance(ann, type) and issubclass(ann, BaseModel):
        result.append(ann)
    return result


def _collect_models(root: type[BaseModel]) -> list[type[BaseModel]]:
    """Collect all nested models reachable from a root model, in order."""
    seen: set[type[BaseModel]] = set()
    ordered: list[type[BaseModel]] = []

    def visit(model: type[BaseModel]) -> None:
        if model in seen:
            return
        seen.add(model)
        ordered.append(model)
        for field in model.model_fields.values():
            for candidate in _nested_models(field.annotation):
                visit(candidate)

    visit(root)
    return ordered


class SchemaRenderer(LoggerMixin):
    """Renders schema-derived documentation and JSON examples for prompts."""

    def __init__(self) -> None:
        """Initialize schema renderer."""
        super().__init__()

    def render_schema_documentation(self, model: type[BaseModel] = CodeGenerationIR) -> str:
        """Render per-model field documentation for a schema."""
        models = _collect_models(model)
        sections = ["## IR Schema (authoritative)", ""]
        sections.append(
            "The schema below is derived from the validated Pydantic models in "
            "`app.schemas.ir`. It is the single source of truth for the JSON you "
            "produce. Match it EXACTLY: every required field present, every enum "
            "value one of the listed allowed values, never null for required fields."
        )
        sections.append("")
        for nested in models:
            sections.append(f"### {nested.__name__}")
            sections.append("")
            for field_name, field in nested.model_fields.items():
                annotation = field.annotation
                type_text = _type_name(annotation)
                required_text = "required" if field.is_required() else "optional"
                line = f"- `{field_name}`: **{type_text}**, {required_text}"

                enum_values = _enum_values(annotation)
                if enum_values:
                    rendered = ", ".join(f'"{value}"' for value in enum_values)
                    line += f" — allowed: {rendered}"
                elif not field.is_required():
                    if field.default_factory is not None:
                        try:
                            default = field.default_factory()
                        except Exception:
                            default = None
                        if default is not None:
                            line += f", default: {_display_default(default)}"
                    elif field.default is not PydanticUndefined:
                        line += f", default: {_display_default(field.default)}"
                sections.append(line)
            sections.append("")
        return "\n".join(sections).rstrip()

    def render_json_example(self, model: type[BaseModel] = CodeGenerationIR) -> str:
        """Render a schema-conformant JSON example built from the model."""
        example = _model_example(model)
        return json.dumps(example, indent=2, default=_json_default)


def _json_default(value: Any) -> Any:
    """Serialize non-JSON values (e.g. datetime) for the example."""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return str(value)

"""
Structured Validation Feedback for IR Generation

Converts Pydantic validation errors and pre-validation findings into stable,
machine-readable feedback that can be fed back to the LLM on retries.
"""

import json
from typing import Any

from pydantic import ValidationError

from app.logging import LoggerMixin

_TYPE_EXPECTED = {
    "string_type": "str",
    "int_type": "int",
    "float_type": "float",
    "bool_type": "bool",
    "list_type": "array",
    "dict_type": "object",
    "missing": "a value (required field)",
    "none_required": "non-null value",
    "date_type": "ISO 8601 datetime string",
    "datetime_type": "ISO 8601 datetime string",
}


def format_path(loc: tuple[Any, ...]) -> str:
    """Format a Pydantic error location tuple as a JSONPath-like string."""
    path = ""
    for segment in loc:
        if isinstance(segment, int):
            path = f"{path}[{segment}]"
        else:
            path = f"{path}.{segment}" if path else str(segment)
    return path


def render_value(value: Any) -> str:
    """Render a received value for feedback without dumping sensitive content."""
    if value is None:
        return "null"
    if isinstance(value, str):
        if len(value) > 80:
            return json.dumps(value[:80] + "...")
        return json.dumps(value)
    if isinstance(value, (dict, list)):
        rendered = json.dumps(value)
        if len(rendered) > 80:
            rendered = rendered[:80] + "..."
        return rendered
    return repr(value)


def pydantic_errors_to_feedback(error: ValidationError) -> list[dict[str, Any]]:
    """Convert a Pydantic ValidationError into structured feedback dicts."""
    feedback: list[dict[str, Any]] = []
    for err in error.errors():
        err_type = str(err.get("type", "value_error"))
        ctx = err.get("ctx") or {}
        loc = err.get("loc", ())
        path = format_path(loc)

        if err_type == "enum":
            expected = f"one of {ctx.get('expected', 'the listed enum values')}"
        else:
            expected = _TYPE_EXPECTED.get(err_type, ctx.get("expected", f"expected {err_type}"))

        feedback.append({
            "path": path,
            "error_type": err_type,
            "expected": expected,
            "received": render_value(err.get("input")),
            "message": err.get("msg", ""),
        })
    return feedback


def render_validation_feedback(feedback: list[dict[str, Any]]) -> str:
    """Render structured feedback as a compact, LLM-consumable list."""
    lines = []
    for item in feedback:
        path = item.get("path", "")
        error_type = item.get("error_type", "error")
        expected = item.get("expected", "")
        received = item.get("received", "")
        lines.append(
            f"- [{error_type}] {path}: expected {expected}; received {received}"
        )
    return "\n".join(lines) if lines else "(no issues)"


class ValidationFeedbackBuilder(LoggerMixin):
    """Builds structured LLM feedback from schema validation failures."""

    def __init__(self) -> None:
        """Initialize feedback builder."""
        super().__init__()

    def from_pydantic(self, error: Exception) -> list[dict[str, Any]]:
        """Build structured feedback from a Pydantic ValidationError."""
        if not isinstance(error, ValidationError):
            return [{
                "path": "",
                "error_type": type(error).__name__,
                "expected": "valid IR",
                "received": str(error),
                "message": str(error),
            }]
        return pydantic_errors_to_feedback(error)

    def render(self, feedback: list[dict[str, Any]]) -> str:
        """Render feedback list to text for retry prompts."""
        return render_validation_feedback(feedback)

"""Supported model registry and validation helpers."""

from __future__ import annotations

import os
import re

from app.config import get_settings
from app.schemas.models import SupportedModel


class UnsupportedModelError(ValueError):
    """Raised when a requested model is not in the backend registry."""


def _display_name(model_id: str) -> str:
    words = re.split(r"[-_/]+", model_id.strip())
    return " ".join(word.upper() if word.isdigit() else word.capitalize() for word in words if word)


def _provider_name() -> str:
    settings = get_settings()
    base_url = (settings.llm.openai_base_url or "").lower()
    configured_provider = settings.llm.llm_provider
    if "mistral" in base_url:
        return "mistral"
    if "ollama" in base_url or configured_provider == "ollama":
        return "ollama"
    if "azure" in base_url or configured_provider == "azure":
        return "azure"
    return configured_provider


def get_default_model() -> str:
    """Return the configured global default model."""

    return get_settings().llm.openai_model


def get_supported_models() -> list[SupportedModel]:
    """Return supported models for the configured provider.

    By default the registry exposes the single configured model. Deployments can
    opt in additional models supported by the same configured endpoint via
    LLM_SUPPORTED_MODELS or SUPPORTED_LLM_MODELS, comma separated.
    """

    default_model = get_default_model()
    configured = os.getenv("LLM_SUPPORTED_MODELS") or os.getenv("SUPPORTED_LLM_MODELS") or ""
    model_ids = [m.strip() for m in configured.split(",") if m.strip()]
    if default_model not in model_ids:
        model_ids.insert(0, default_model)

    provider = _provider_name()
    return [
        SupportedModel(id=model_id, name=_display_name(model_id), provider=provider)
        for model_id in dict.fromkeys(model_ids)
    ]


def resolve_model(model: str | None) -> str:
    """Resolve and validate a requested model, falling back to the default."""

    requested = model.strip() if isinstance(model, str) else ""
    selected = requested or get_default_model()
    supported = {m.id for m in get_supported_models()}
    if selected not in supported:
        raise UnsupportedModelError(
            f"Unsupported AI model '{selected}'. Select one of: {', '.join(sorted(supported))}."
        )
    return selected

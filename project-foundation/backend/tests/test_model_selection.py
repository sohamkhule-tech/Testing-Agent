"""Tests for the single configured-model selection behavior (post-rollback).

The model list must be derived purely from configuration (``OPENAI_MODEL``)
with no provider ``/models`` discovery and no hardcoded model identifiers.
"""

import pytest

from app.llm.model_registry import (
    UnsupportedModelError,
    get_default_model,
    get_supported_models,
    resolve_model,
)


def _patch_settings(monkeypatch, model_id: str = "test-configured-model") -> None:
    class FakeLLM:
        openai_model = model_id
        openai_base_url = "https://example.com/v1"
        llm_provider = "openai"

    class FakeSettings:
        llm = FakeLLM()

    monkeypatch.setattr("app.llm.model_registry.get_settings", lambda: FakeSettings())


def test_default_model_comes_from_configuration(monkeypatch):
    _patch_settings(monkeypatch, "test-configured-model")
    assert get_default_model() == "test-configured-model"


def test_supported_models_returns_exactly_one_configured_model(monkeypatch):
    _patch_settings(monkeypatch, "test-configured-model")

    models = get_supported_models()

    assert len(models) == 1
    assert models[0].id == "test-configured-model"
    assert models[0].name  # display name derived from the id
    assert models[0].provider == "openai"


def test_supported_models_have_no_discovery_metadata(monkeypatch):
    _patch_settings(monkeypatch)

    models = get_supported_models()

    # The simple registry schema exposes only id/name/provider.
    assert not hasattr(models[0], "owned_by")
    assert not hasattr(models[0], "capabilities")


def test_resolve_model_none_returns_configured_model(monkeypatch):
    _patch_settings(monkeypatch, "test-configured-model")
    assert resolve_model(None) == "test-configured-model"


def test_resolve_model_accepts_configured_model(monkeypatch):
    _patch_settings(monkeypatch, "test-configured-model")
    assert resolve_model("test-configured-model") == "test-configured-model"


def test_resolve_model_rejects_unknown_model(monkeypatch):
    _patch_settings(monkeypatch, "test-configured-model")
    with pytest.raises(UnsupportedModelError):
        resolve_model("some-unknown-model")


def test_models_endpoint_returns_single_configured_model(test_client, monkeypatch):
    _patch_settings(monkeypatch, "test-configured-model")

    response = test_client.get("/api/v1/models")

    assert response.status_code == 200
    data = response.json()

    assert len(data["models"]) == 1
    assert data["models"][0]["id"] == "test-configured-model"
    assert data["defaultModel"] == "test-configured-model"

    # No dynamic-discovery fields may be present (proves no provider /models call).
    for key in ("status", "error", "source", "stale", "provider"):
        assert key not in data, f"unexpected discovery field '{key}' in response"


def test_historical_model_never_becomes_current(monkeypatch):
    # The registry is built solely from configuration. A historical run model
    # must never appear unless it is the currently configured model.
    _patch_settings(monkeypatch, "test-configured-model")

    models = get_supported_models()

    assert "deepseek-r1-distill-qwen-8b" not in [m.id for m in models]

"""
Unit and API tests for PromptOptimizationService and /api/v1/prompts/optimize endpoint.

All tests mock the ILLMClient interface so no external LLM API keys are required.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.interfaces import ILLMClient
from app.exceptions import LLMProviderError, LLMRateLimitError, LLMTimeoutError
from app.llm.model_registry import get_default_model
from app.main import app
from app.schemas.prompt_optimization import LLMOptimizationSchema
from app.services.prompt_optimization_service import PromptOptimizationService


@pytest.fixture
def mock_llm_client():
    """Mock ILLMClient for deterministic unit tests."""
    client = MagicMock(spec=ILLMClient)
    client.model = "gpt-4o"
    client.complete = AsyncMock()
    client.complete_structured = AsyncMock()
    return client


@pytest.fixture
def optimization_service(mock_llm_client):
    """Fixture providing PromptOptimizationService with mocked LLM client."""
    return PromptOptimizationService(llm_client=mock_llm_client)


@pytest.fixture
def client():
    """FastAPI TestClient."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Unit Tests — PromptOptimizationService
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_optimize_prompt_success_structured(optimization_service, mock_llm_client):
    """Test successful optimization using complete_structured."""
    mock_llm_client.complete_structured.return_value = LLMOptimizationSchema(
        optimized_prompt="Test the login form with valid and invalid credentials. Verify proper authentication."
    )

    response = await optimization_service.optimize_prompt("test login")

    assert response.original_prompt == "test login"
    assert "Test the login form" in response.optimized_prompt
    assert response.model == get_default_model()
    assert response.usage.total_tokens > 0
    mock_llm_client.complete_structured.assert_called_once()


@pytest.mark.asyncio
async def test_optimize_prompt_fallback_complete(optimization_service, mock_llm_client):
    """Test optimization fallback to complete() when complete_structured fails or is unconfigured."""
    mock_llm_client.complete_structured.side_effect = Exception("Structured unsupported")
    mock_llm_client.complete.return_value = '{"optimized_prompt": "Test login flow thoroughly."}'

    response = await optimization_service.optimize_prompt("test login")

    assert response.original_prompt == "test login"
    assert response.optimized_prompt == "Test login flow thoroughly."
    mock_llm_client.complete.assert_called_once()


@pytest.mark.asyncio
async def test_optimize_prompt_redacts_credentials(optimization_service, mock_llm_client):
    """Test that sensitive credentials in prompt are redacted before sending to LLM."""
    mock_llm_client.complete_structured.return_value = LLMOptimizationSchema(
        optimized_prompt="Test login with provided credentials."
    )

    sensitive_prompt = "test login username admin password secret123"
    response = await optimization_service.optimize_prompt(sensitive_prompt)

    # Assert original prompt is preserved for UI/audit
    assert response.original_prompt == sensitive_prompt

    # Assert LLM call received sanitized prompt without raw password
    call_args = mock_llm_client.complete_structured.call_args[1]
    prompt_sent = call_args["prompt"]
    assert "secret123" not in prompt_sent
    assert "[CREDENTIAL REDACTED]" in prompt_sent


@pytest.mark.asyncio
async def test_optimize_prompt_empty_raises_value_error(optimization_service):
    """Test that empty or whitespace prompt raises ValueError."""
    with pytest.raises(ValueError, match="empty or whitespace-only"):
        await optimization_service.optimize_prompt("")

    with pytest.raises(ValueError, match="empty or whitespace-only"):
        await optimization_service.optimize_prompt("   \n\t ")


@pytest.mark.asyncio
async def test_optimize_prompt_excessive_length_raises_value_error(optimization_service):
    """Test that prompt exceeding 10,000 characters raises ValueError."""
    huge_prompt = "a" * 10001
    with pytest.raises(ValueError, match="maximum length"):
        await optimization_service.optimize_prompt(huge_prompt)


@pytest.mark.asyncio
async def test_optimize_prompt_timeout_propagates(optimization_service, mock_llm_client):
    """Test that LLMTimeoutError propagates cleanly."""
    mock_llm_client.complete_structured.side_effect = LLMTimeoutError("LLM call timed out after 30s")
    mock_llm_client.complete.side_effect = LLMTimeoutError("LLM call timed out after 30s")

    with pytest.raises(LLMTimeoutError):
        await optimization_service.optimize_prompt("test login")


@pytest.mark.asyncio
async def test_optimize_prompt_rate_limit_propagates(optimization_service, mock_llm_client):
    """Test that LLMRateLimitError propagates cleanly."""
    mock_llm_client.complete_structured.side_effect = LLMRateLimitError("Rate limit exceeded")
    mock_llm_client.complete.side_effect = LLMRateLimitError("Rate limit exceeded")

    with pytest.raises(LLMRateLimitError):
        await optimization_service.optimize_prompt("test login")


@pytest.mark.asyncio
async def test_optimize_prompt_malformed_empty_llm_response(optimization_service, mock_llm_client):
    """Test that empty or malformed LLM completion raises LLMProviderError."""
    mock_llm_client.complete_structured.side_effect = Exception("Fallback")
    mock_llm_client.complete.return_value = ""

    with pytest.raises(LLMProviderError, match="empty response"):
        await optimization_service.optimize_prompt("test login")


# ---------------------------------------------------------------------------
# API Route Integration Tests — POST /api/v1/prompts/optimize
# ---------------------------------------------------------------------------


def test_api_optimize_prompt_success(client):
    """Test API POST /api/v1/prompts/optimize returns HTTP 200 with structured JSON."""
    from app.dependencies import get_prompt_optimization_service

    mock_service = MagicMock()
    mock_service.optimize_prompt = AsyncMock(return_value={
        "originalPrompt": "test login",
        "optimizedPrompt": "Test authentication form with valid and invalid credentials.",
        "model": "gpt-4o",
        "usage": {
            "promptTokens": 10,
            "completionTokens": 15,
            "totalTokens": 25,
        },
    })

    app.dependency_overrides[get_prompt_optimization_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/prompts/optimize",
            json={"prompt": "test login"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["originalPrompt"] == "test login"
        assert "Test authentication form" in data["optimizedPrompt"]
        assert data["model"] == "gpt-4o"
        assert data["usage"]["totalTokens"] == 25
    finally:
        app.dependency_overrides.pop(get_prompt_optimization_service, None)


def test_api_optimize_prompt_empty_validation_400(client):
    """Test API POST /api/v1/prompts/optimize returns HTTP 400 or 422 for empty prompt."""
    response = client.post(
        "/api/v1/prompts/optimize",
        json={"prompt": "   "},
    )
    assert response.status_code in (400, 422)


def test_api_optimize_prompt_timeout_408(client):
    """Test API POST /api/v1/prompts/optimize returns HTTP 408 on LLM timeout."""
    from app.dependencies import get_prompt_optimization_service

    mock_service = MagicMock()
    mock_service.optimize_prompt = AsyncMock(side_effect=LLMTimeoutError("Request timeout"))

    app.dependency_overrides[get_prompt_optimization_service] = lambda: mock_service
    try:
        response = client.post(
            "/api/v1/prompts/optimize",
            json={"prompt": "test login"},
        )
        assert response.status_code == 408
    finally:
        app.dependency_overrides.pop(get_prompt_optimization_service, None)

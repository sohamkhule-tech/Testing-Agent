"""LLM model discovery API."""

from fastapi import APIRouter

from app.llm.model_registry import get_default_model, get_supported_models
from app.schemas.models import ModelListResponse

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("", response_model=ModelListResponse)
async def list_models() -> ModelListResponse:
    """Return backend-approved models for user selection."""

    return ModelListResponse(models=get_supported_models(), defaultModel=get_default_model())

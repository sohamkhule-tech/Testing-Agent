"""Schemas for supported LLM model discovery."""

from pydantic import BaseModel, ConfigDict, Field


class SupportedModel(BaseModel):
    """Public model metadata safe to expose to the frontend."""

    id: str = Field(..., description="Stable provider model identifier")
    name: str = Field(..., description="Human-readable model name")
    provider: str = Field(..., description="Provider family")

    model_config = ConfigDict(populate_by_name=True)


class ModelListResponse(BaseModel):
    """Response for GET /api/v1/models."""

    models: list[SupportedModel]
    default_model: str = Field(..., alias="defaultModel")

    model_config = ConfigDict(populate_by_name=True)

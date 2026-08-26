"""
Prompt Optimization Schemas

Request and response schemas for LLM prompt optimization endpoints.
"""

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OptimizePromptRequest(BaseModel):
    """Request model for prompt optimization."""

    prompt: str = Field(..., description="Raw user prompt to optimize")
    model: str | None = Field(None, min_length=1, max_length=128, description="Optional backend-approved LLM model")

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, v: str) -> str:
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Prompt cannot be empty or whitespace-only.")
        if len(v) > 10000:
            raise ValueError("Prompt exceeds maximum length of 10,000 characters.")
        return trimmed

    @field_validator("model")
    @classmethod
    def validate_model(cls, v: str | None) -> str | None:
        if v is None:
            return None
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("Model cannot be empty.")
        return trimmed

    model_config = ConfigDict(populate_by_name=True)


class TokenUsageInfo(BaseModel):
    """Token usage tracking information."""

    prompt_tokens: int = Field(default=0, alias="promptTokens", description="Prompt token count")
    completion_tokens: int = Field(default=0, alias="completionTokens", description="Completion token count")
    total_tokens: int = Field(default=0, alias="totalTokens", description="Total token count")

    model_config = ConfigDict(populate_by_name=True)


class OptimizePromptResponse(BaseModel):
    """Response model for prompt optimization."""

    original_prompt: str = Field(..., alias="originalPrompt", description="User's original prompt")
    optimized_prompt: str = Field(..., alias="optimizedPrompt", description="LLM-optimized prompt")
    model: str = Field(..., description="LLM model used for optimization")
    usage: TokenUsageInfo = Field(..., description="Token usage details")

    model_config = ConfigDict(populate_by_name=True)


class LLMOptimizationSchema(BaseModel):
    """Internal Pydantic schema for structured LLM response."""

    optimized_prompt: str = Field(..., description="Optimized testing instruction prompt")

"""
Prompt Optimization API Router

Provides endpoint for optimizing raw user testing prompts.
"""

from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies import get_prompt_optimization_service
from app.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.logging import get_logger
from app.llm.model_registry import UnsupportedModelError
from app.schemas.prompt_optimization import (
    OptimizePromptRequest,
    OptimizePromptResponse,
)
from app.services.prompt_optimization_service import PromptOptimizationService

logger = get_logger("api.prompts")

router = APIRouter(prefix="/prompts", tags=["Prompts"])


@router.post(
    "/optimize",
    response_model=OptimizePromptResponse,
    status_code=status.HTTP_200_OK,
    summary="Optimize user testing prompt",
    description=(
        "Transforms a natural-language testing request into a clearer, more complete, "
        "structured testing instruction using the platform's existing LLM infrastructure. "
        "Preserves original intent and redacts sensitive credentials prior to LLM call."
    ),
    responses={
        200: {"description": "Successfully optimized prompt"},
        400: {"description": "Invalid or empty prompt"},
        408: {"description": "LLM call timed out"},
        429: {"description": "Rate limit exceeded"},
        500: {"description": "LLM provider or optimization error"},
    },
)
async def optimize_prompt(
    request: OptimizePromptRequest,
    service: PromptOptimizationService = Depends(get_prompt_optimization_service),
) -> OptimizePromptResponse:
    """Optimize user testing instruction prompt."""
    try:
        return await service.optimize_prompt(request.prompt, model=request.model)
    except UnsupportedModelError as model_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(model_err),
        ) from model_err
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(val_err),
        ) from val_err
    except LLMTimeoutError as timeout_err:
        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail=f"Prompt optimization timed out: {str(timeout_err)}",
        ) from timeout_err
    except LLMRateLimitError as rate_err:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded: {str(rate_err)}",
        ) from rate_err
    except LLMProviderError as provider_err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Prompt optimization error: {str(provider_err)}",
        ) from provider_err
    except Exception as err:
        logger.error("prompt_optimization_unhandled_error", error=str(err))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to optimize the prompt right now. Please try again.",
        ) from err

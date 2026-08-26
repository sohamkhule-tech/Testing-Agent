"""
Prompt Optimization Service

Uses the platform's existing LLM client infrastructure (ILLMClient) to transform
user testing requests into clearer, structured, actionable test instructions
while strictly preserving original intent and redacting credentials.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from app.config import get_settings
from app.core.interfaces import ILLMClient, IService
from app.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
)
from app.llm.model_registry import resolve_model
from app.logging import LoggerMixin
from app.schemas.prompt_optimization import (
    LLMOptimizationSchema,
    OptimizePromptResponse,
    TokenUsageInfo,
)
from app.services.prompt_builder import get_prompt_parser

OPTIMIZE_SYSTEM_PROMPT = (
    "You are an expert QA test-planning prompt optimizer.\n\n"
    "Your job is to improve a user's testing instruction so that a downstream AI testing system can generate accurate test scenarios.\n\n"
    "Rules:\n\n"
    "1. Preserve the user's original intent.\n"
    "2. Do not invent application functionality, URLs, credentials, business rules, UI elements, APIs, or expected behavior that the user did not provide.\n"
    "3. Make vague testing requirements clearer where possible without fabricating facts.\n"
    "4. Make the instruction actionable for an AI test-generation system.\n"
    "5. Structure the optimized prompt using clear markdown section headers:\n"
    "   ## Focus Areas\n"
    "   (List the specific pages or modules implied by the user request, e.g. Login, Dashboard, Forms)\n"
    "   ## Coverage\n"
    "   (List relevant testing dimensions implied by the request: functional testing, positive scenarios, negative scenarios, validation, boundary cases, authentication/authorization, error handling, security, usability)\n"
    "   ## Output\n"
    "   Playwright Page Object Model\n"
    "6. Do not generate actual test cases.\n"
    "7. Do not generate code.\n"
    "8. Do not explain the optimization.\n"
    "9. Return only the optimized prompt in the requested structured format."
)


class PromptOptimizationService(IService, LoggerMixin):
    """Service handling prompt optimization via ILLMClient."""

    def __init__(self, llm_client: ILLMClient) -> None:
        super().__init__()
        self.llm_client = llm_client

    async def initialize(self) -> None:
        self.logger.info("prompt_optimization_service_initialized")

    async def cleanup(self) -> None:
        self.logger.info("prompt_optimization_service_cleanup")

    async def optimize_prompt(self, raw_prompt: str, model: str | None = None) -> OptimizePromptResponse:
        """
        Optimize a raw user prompt into a structured testing instruction.

        Args:
            raw_prompt: Original user testing instruction prompt
            model: Optional backend-approved model id

        Returns:
            OptimizePromptResponse with original and optimized prompt + usage metrics

        Raises:
            ValueError: If prompt is empty / invalid
            LLMTimeoutError: On LLM timeout
            LLMRateLimitError: On rate limiting
            LLMProviderError: On LLM API or JSON parsing failure
        """
        cleaned_prompt = raw_prompt.strip() if raw_prompt else ""
        if not cleaned_prompt:
            raise ValueError("Prompt cannot be empty or whitespace-only.")

        if len(raw_prompt) > 10000:
            raise ValueError("Prompt exceeds maximum length of 10,000 characters.")

        # 1. Sanitize/redact sensitive credential patterns prior to sending to LLM
        parser = get_prompt_parser()
        sanitized_prompt = parser._redact_credentials(cleaned_prompt)
        try:
            from app.context.intent_parser import HybridIntentParser
            sanitized_prompt = HybridIntentParser()._redact_credentials(sanitized_prompt)
        except Exception:
            pass

        start_time = time.time()
        model_name = resolve_model(model)
        settings = get_settings()

        self.logger.info(
            "prompt_optimization_started",
            model=model_name,
            prompt_length=len(cleaned_prompt),
            operation="prompt_optimization",
        )

        user_instruction = (
            "Optimize the following user testing request into a clear, structured testing instruction.\n\n"
            f"User Request:\n{sanitized_prompt}"
        )

        try:
            # 2. Attempt structured completion if supported, else complete + extract_json
            optimized_text: str | None = None

            if settings.llm.llm_structured_output_enabled and hasattr(self.llm_client, "complete_structured"):
                try:
                    result: LLMOptimizationSchema = await self.llm_client.complete_structured(
                        prompt=user_instruction,
                        response_model=LLMOptimizationSchema,
                        system_prompt=OPTIMIZE_SYSTEM_PROMPT,
                        model=model_name,
                    )
                    optimized_text = result.optimized_prompt
                except Exception as struct_err:
                    self.logger.warning(
                        "structured_optimization_fallback",
                        error=str(struct_err)[:200],
                    )

            if not optimized_text:
                # Fallback to standard completion with JSON parsing
                completion_raw = await self.llm_client.complete(
                    prompt=(
                        f"{user_instruction}\n\n"
                        'Return strictly a JSON object: {"optimized_prompt": "..."}'
                    ),
                    system_prompt=OPTIMIZE_SYSTEM_PROMPT,
                    temperature=0.2,
                    max_tokens=1000,
                    model=model_name,
                )

                if not completion_raw or not completion_raw.strip():
                    raise LLMProviderError("LLM returned empty response during prompt optimization.")

                extracted = self._extract_json(completion_raw)
                optimized_text = extracted.get("optimized_prompt") or extracted.get("prompt") or completion_raw.strip()

            if not optimized_text or not str(optimized_text).strip():
                raise LLMProviderError("Failed to produce a valid non-empty optimized prompt.")

            final_optimized_prompt = str(optimized_text).strip()
            duration = time.time() - start_time

            # 3. Calculate token usage estimation or response metrics
            prompt_tokens = len(sanitized_prompt.split()) + len(OPTIMIZE_SYSTEM_PROMPT.split())
            completion_tokens = len(final_optimized_prompt.split())
            total_tokens = prompt_tokens + completion_tokens

            usage = TokenUsageInfo(
                promptTokens=prompt_tokens,
                completionTokens=completion_tokens,
                totalTokens=total_tokens,
            )

            self.logger.info(
                "prompt_optimization_completed",
                model=model_name,
                duration_seconds=duration,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                operation="prompt_optimization",
            )

            return OptimizePromptResponse(
                originalPrompt=cleaned_prompt,
                optimizedPrompt=final_optimized_prompt,
                model=model_name,
                usage=usage,
            )

        except (LLMTimeoutError, LLMRateLimitError, ValueError):
            raise
        except LLMProviderError as pe:
            self.logger.error("prompt_optimization_failed", error=str(pe), model=model_name)
            raise
        except Exception as exc:
            err_msg = str(exc)
            self.logger.error("prompt_optimization_failed", error=err_msg, model=model_name)
            if "timeout" in err_msg.lower():
                raise LLMTimeoutError(f"Optimization request timed out: {err_msg}")
            elif "rate limit" in err_msg.lower():
                raise LLMRateLimitError(f"Rate limit exceeded: {err_msg}")
            raise LLMProviderError(f"Prompt optimization failed: {err_msg}")

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        """Safely extract and parse JSON object from LLM response text."""
        cleaned = text.strip()
        first_brace = cleaned.find("{")
        last_brace = cleaned.rfind("}")
        if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
            cleaned = cleaned[first_brace:last_brace + 1]
        cleaned = re.sub(r",\s*}", "}", cleaned)
        cleaned = re.sub(r",\s*]", "]", cleaned)
        cleaned = re.sub(r"```json\s*", "", cleaned)
        cleaned = re.sub(r"```\s*", "", cleaned)
        try:
            return json.loads(cleaned)
        except Exception:
            return {"optimized_prompt": text.strip()}

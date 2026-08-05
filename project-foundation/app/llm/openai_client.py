"""
OpenAI LLM Client Implementation

Provider-agnostic LLM client wrapper using OpenAI SDK.
"""

from typing import Any, AsyncIterator

import asyncio
from openai import AsyncOpenAI
from pydantic import BaseModel

from app.config import get_settings
from app.core.interfaces import ILLMClient
from app.exceptions import (
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMTokenLimitError,
)
from app.logging import LoggerMixin
from app.utils import with_retry


class OpenAIClient(ILLMClient, LoggerMixin):
    """
    OpenAI API client implementation.

    Provides standardized interface for LLM operations.
    """

    def __init__(self) -> None:
        """Initialize OpenAI client."""
        super().__init__()
        settings = get_settings()

        client_kwargs = {
            "api_key": settings.llm.openai_api_key or "ollama",
            "timeout": settings.llm.openai_timeout,
        }
        if settings.llm.openai_base_url:
            client_kwargs["base_url"] = settings.llm.openai_base_url

        self.client = AsyncOpenAI(**client_kwargs)

        self.model = settings.llm.openai_model
        self.default_temperature = settings.llm.openai_temperature
        self.default_max_tokens = settings.llm.openai_max_tokens

    @with_retry(max_attempts=3, initial_wait=1.0, exceptions=(LLMRateLimitError, LLMTimeoutError, ConnectionError, TimeoutError, asyncio.TimeoutError))
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        **kwargs: Any,
    ) -> str:
        """
        Generate completion from prompt.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            **kwargs: Additional parameters

        Returns:
            Generated completion

        Raises:
            LLMProviderError: If API call fails
            LLMRateLimitError: If rate limit exceeded
            LLMTokenLimitError: If token limit exceeded
        """
        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Enforce a hard per-call deadline independent of SDK timeout so TCP hangs
            # don't block indefinitely even if the SDK timeout is misconfigured.
            settings = get_settings()
            call_timeout = settings.llm.openai_timeout  # seconds

            # Log detailed request information
            import time
            request_start_time = time.time()
            
            self.logger.info(
                "openai_request_starting",
                model=self.model,
                prompt_length=len(prompt),
                system_prompt_length=len(system_prompt) if system_prompt else 0,
                temperature=temperature,
                max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
                timeout_seconds=call_timeout,
                base_url=settings.llm.openai_base_url,
                timestamp=request_start_time,
            )

            # Call API with asyncio.wait_for for hard deadline
            self.logger.info("openai_sdk_call_initiated", timeout=call_timeout)
            
            response = await asyncio.wait_for(
                self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens if max_tokens is not None else self.default_max_tokens,
                    **kwargs,
                ),
                timeout=call_timeout,
            )
            
            request_duration = time.time() - request_start_time

            # Extract completion
            completion = response.choices[0].message.content

            self.logger.info(
                "llm_completion",
                model=self.model,
                prompt_tokens=response.usage.prompt_tokens if response.usage else 0,
                completion_tokens=response.usage.completion_tokens if response.usage else 0,
                total_tokens=response.usage.total_tokens if response.usage else 0,
                duration_seconds=request_duration,
                finish_reason=response.choices[0].finish_reason if response.choices else None,
            )

            return completion or ""

        except asyncio.TimeoutError as e:
            request_duration = time.time() - request_start_time
            self.logger.error(
                "openai_timeout",
                timeout_seconds=call_timeout,
                elapsed_seconds=request_duration,
                model=self.model,
            )
            raise LLMTimeoutError(f"LLM call timed out after {call_timeout}s (elapsed: {request_duration:.1f}s)") from e
        except Exception as e:
            request_duration = time.time() - request_start_time if 'request_start_time' in locals() else 0
            error_msg = str(e)
            
            self.logger.error(
                "openai_error",
                error=error_msg,
                error_type=type(e).__name__,
                duration_seconds=request_duration,
                model=self.model,
            )

            # Handle specific error types
            if "rate_limit" in error_msg.lower():
                raise LLMRateLimitError(f"Rate limit exceeded: {error_msg}")
            elif "maximum context length" in error_msg.lower():
                raise LLMTokenLimitError(f"Token limit exceeded: {error_msg}")
            elif "timeout" in error_msg.lower():
                raise LLMTimeoutError(f"Request timeout: {error_msg}")
            else:
                self.logger.error("llm_error", error=error_msg, traceback=True)
                raise LLMProviderError(f"LLM API error: {error_msg}")

    async def complete_structured(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> BaseModel:
        """
        Generate structured completion conforming to Pydantic model.

        Args:
            prompt: User prompt
            response_model: Pydantic model for response
            system_prompt: Optional system prompt
            **kwargs: Additional parameters

        Returns:
            Parsed Pydantic model instance

        Raises:
            LLMProviderError: If API call fails
        """
        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})

            # Add schema instruction to prompt
            schema = response_model.model_json_schema()
            structured_prompt = (
                f"{prompt}\n\n"
                f"Respond with valid JSON matching this schema:\n"
                f"```json\n{schema}\n```"
            )
            messages.append({"role": "user", "content": structured_prompt})

            # Call API with JSON mode
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                response_format={"type": "json_object"},
                **kwargs,
            )

            # Parse response
            completion = response.choices[0].message.content
            if not completion:
                raise LLMProviderError("Empty response from LLM")

            # Validate against model
            result = response_model.model_validate_json(completion)

            self.logger.info(
                "llm_structured_completion",
                model=self.model,
                response_model=response_model.__name__,
            )

            return result

        except Exception as e:
            self.logger.error("llm_structured_error", error=str(e))
            raise LLMProviderError(f"Structured completion failed: {str(e)}")

    async def stream_complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """
        Stream completion tokens.

        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            **kwargs: Additional parameters

        Yields:
            Token chunks

        Raises:
            LLMProviderError: If streaming fails
        """
        try:
            # Build messages
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            # Stream API call
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
                **kwargs,
            )

            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

            self.logger.info("llm_stream_complete", model=self.model)

        except Exception as e:
            self.logger.error("llm_stream_error", error=str(e))
            raise LLMProviderError(f"Streaming failed: {str(e)}")

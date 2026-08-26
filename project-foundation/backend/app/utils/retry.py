"""
Retry Utility with Exponential Backoff

Provides retry mechanisms for handling transient failures.
"""

import asyncio
import functools
from typing import Any, Callable, Type

from tenacity import (
    AsyncRetrying,
    RetryCallState,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.exceptions import MaxRetriesExceededError, NonRetryableError, RetryableError
from app.logging import get_logger

logger = get_logger("utils.retry")


def is_retryable_exception(exception: BaseException) -> bool:
    """
    Determine if an exception is retryable.

    Args:
        exception: Exception to check

    Returns:
        True if exception is retryable
    """
    # Non-retryable exceptions
    non_retryable = (
        NonRetryableError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
    )

    if isinstance(exception, non_retryable):
        return False

    # Retryable exceptions
    retryable = (
        RetryableError,
        ConnectionError,
        TimeoutError,
        asyncio.TimeoutError,
    )

    return isinstance(exception, retryable)


def log_retry_attempt(retry_state: RetryCallState) -> None:
    """
    Log retry attempt.

    Args:
        retry_state: Retry state information
    """
    if retry_state.outcome and retry_state.outcome.failed:
        exception = retry_state.outcome.exception()
        logger.warning(
            "retry_attempt",
            attempt=retry_state.attempt_number,
            exception_type=exception.__class__.__name__,
            exception_message=str(exception),
        )


async def retry_async(
    func: Callable[..., Any],
    *args: Any,
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    exponential_base: int = 2,
    exceptions: tuple[Type[Exception], ...] | None = None,
    **kwargs: Any,
) -> Any:
    """
    Retry an async function with exponential backoff.

    Args:
        func: Async function to retry
        *args: Positional arguments for func
        max_attempts: Maximum number of retry attempts
        initial_wait: Initial wait time in seconds
        max_wait: Maximum wait time in seconds
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exceptions to retry on (None = use default)
        **kwargs: Keyword arguments for func

    Returns:
        Result from func

    Raises:
        MaxRetriesExceededError: When max attempts exceeded
        Exception: Last exception if max attempts exceeded

    Example:
        >>> result = await retry_async(api_call, url, max_attempts=3)
    """
    # Default: only retry genuinely transient errors, never CancelledError/business logic.
    retry_exceptions = exceptions or (RetryableError, ConnectionError, TimeoutError, asyncio.TimeoutError)

    retry_policy = AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(
            multiplier=initial_wait, max=max_wait, exp_base=exponential_base
        ),
        retry=retry_if_exception_type(retry_exceptions),
        before_sleep=log_retry_attempt,
        reraise=True,
    )

    try:
        async for attempt in retry_policy:
            with attempt:
                return await func(*args, **kwargs)
    except asyncio.CancelledError:
        raise  # Never swallow cancellation
    except Exception as e:
        logger.error(
            "retry_exhausted",
            function=func.__name__,
            max_attempts=max_attempts,
            exception_type=e.__class__.__name__,
            exception_message=str(e),
        )
        raise MaxRetriesExceededError(
            f"Max retries ({max_attempts}) exceeded for {func.__name__}",
            attempts=max_attempts,
            max_attempts=max_attempts,
        ) from e


def with_retry(
    max_attempts: int = 3,
    initial_wait: float = 1.0,
    max_wait: float = 10.0,
    exponential_base: int = 2,
    exceptions: tuple[Type[Exception], ...] | None = None,
) -> Callable:
    """
    Decorator for automatic retry with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        initial_wait: Initial wait time in seconds
        max_wait: Maximum wait time in seconds
        exponential_base: Base for exponential backoff
        exceptions: Tuple of exceptions to retry on

    Returns:
        Decorator function

    Example:
        >>> @with_retry(max_attempts=3, initial_wait=1.0)
        ... async def fetch_data():
        ...     pass
    """
    # Default: only retry genuinely transient errors, never CancelledError/business logic.
    retry_exceptions = exceptions or (RetryableError, ConnectionError, TimeoutError, asyncio.TimeoutError)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await retry_async(
                func,
                *args,
                max_attempts=max_attempts,
                initial_wait=initial_wait,
                max_wait=max_wait,
                exponential_base=exponential_base,
                exceptions=retry_exceptions,
                **kwargs,
            )

        return wrapper

    return decorator


class RetryContext:
    """
    Context manager for retry operations.

    Example:
        >>> async with RetryContext(max_attempts=3) as retry:
        ...     result = await retry.execute(api_call, url)
    """

    def __init__(
        self,
        max_attempts: int = 3,
        initial_wait: float = 1.0,
        max_wait: float = 10.0,
        exponential_base: int = 2,
    ) -> None:
        """
        Initialize retry context.

        Args:
            max_attempts: Maximum number of retry attempts
            initial_wait: Initial wait time in seconds
            max_wait: Maximum wait time in seconds
            exponential_base: Base for exponential backoff
        """
        self.max_attempts = max_attempts
        self.initial_wait = initial_wait
        self.max_wait = max_wait
        self.exponential_base = exponential_base

    async def __aenter__(self) -> "RetryContext":
        """Enter context."""
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context."""
        pass

    async def execute(
        self,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """
        Execute function with retry.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from function
        """
        return await retry_async(
            func,
            *args,
            max_attempts=self.max_attempts,
            initial_wait=self.initial_wait,
            max_wait=self.max_wait,
            exponential_base=self.exponential_base,
            **kwargs,
        )

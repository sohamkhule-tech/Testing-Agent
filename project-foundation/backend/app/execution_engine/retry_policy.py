"""
Retry Policy — per-task retry with exponential backoff.

Each task defines max retries, backoff base, and retry-eligible failure conditions.
The planner's feedback loop consults this policy before deciding to retry.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from app.logging import LoggerMixin


@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_base: float = 1.0          # seconds
    backoff_multiplier: float = 2.0    # exponential
    max_backoff: float = 60.0
    retry_on_timeout: bool = True
    retry_on_connection_error: bool = True
    retry_on_server_error: bool = True

    def backoff_delay(self, attempt: int) -> float:
        delay = self.backoff_base * (self.backoff_multiplier ** (attempt - 1))
        return min(delay, self.max_backoff)


@dataclass
class RetryRecord:
    attempt: int
    error: str
    timestamp: str = ""
    delay_seconds: float = 0.0
    result: str = "pending"


class RetryPolicy(LoggerMixin):
    """
    Decides whether a failed task should be retried based on config, error type,
    and attempt count.
    """

    def __init__(self) -> None:
        super().__init__()
        self._retry_configs: dict[str, RetryConfig] = {}
        self._retry_history: dict[str, list[RetryRecord]] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_config(self, task_id: str, config: RetryConfig) -> None:
        self._retry_configs[task_id] = config

    def get_config(self, task_id: str) -> RetryConfig:
        return self._retry_configs.get(task_id, RetryConfig())

    def should_retry(self, task_id: str, error: str, attempt: int | None = None) -> bool:
        """Check whether the given task+error should be retried."""
        config = self.get_config(task_id)
        history = self._retry_history.get(task_id, [])
        current_attempt = attempt if attempt is not None else len(history) + 1

        if current_attempt > config.max_retries:
            return False

        error_lower = error.lower()
        if "timeout" in error_lower and not config.retry_on_timeout:
            return False
        if any(k in error_lower for k in ("connection", "network", "econnrefused")) and not config.retry_on_connection_error:
            return False
        if any(k in error_lower for k in ("500", "502", "503", "server error")) and not config.retry_on_server_error:
            return False

        return True

    def record_attempt(self, task_id: str, error: str, delay: float = 0.0) -> RetryRecord:
        history = self._retry_history.get(task_id, [])
        record = RetryRecord(
            attempt=len(history) + 1,
            error=error,
            delay_seconds=delay,
        )
        history.append(record)
        self._retry_history[task_id] = history
        return record

    def record_result(self, task_id: str, success: bool) -> None:
        history = self._retry_history.get(task_id, [])
        if history:
            history[-1].result = "success" if success else "failed"

    async def execute_with_retry(
        self,
        task_id: str,
        fn: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute fn with retries according to policy."""
        config = self.get_config(task_id)
        last_error: Exception | None = None

        for attempt in range(1, config.max_retries + 1):
            try:
                result = await fn(*args, **kwargs)
                self.record_result(task_id, success=True)
                return result
            except Exception as e:
                record = self.record_attempt(task_id, str(e))
                last_error = e
                if not self.should_retry(task_id, str(e), attempt=attempt):
                    self.record_result(task_id, success=False)
                    raise

                delay = config.backoff_delay(attempt)
                record.delay_seconds = delay
                self.logger.warning("retry_attempt", task_id=task_id, attempt=attempt, delay=delay, error=str(e))
                await asyncio.sleep(delay)

        self.record_result(task_id, success=False)
        raise last_error  # type: ignore[misc]

    def summary(self, task_id: str) -> dict[str, Any]:
        history = self._retry_history.get(task_id, [])
        return {
            "task_id": task_id,
            "attempts": len(history),
            "max_retries": self.get_config(task_id).max_retries,
            "history": [{"attempt": r.attempt, "error": r.error[:100], "result": r.result} for r in history],
        }

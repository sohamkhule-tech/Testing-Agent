"""
Enterprise Logging Configuration

Provides structured logging with correlation IDs, component tracking,
and execution time measurement.
"""

import logging
import sys
from pathlib import Path
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

from app.config import settings


def add_correlation_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Add correlation ID to log context.

    Args:
        logger: Logger instance
        method_name: Method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary
    """
    correlation_id = structlog.contextvars.get_contextvars().get("correlation_id")
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    return event_dict


def add_request_id(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Add request ID to log context.

    Args:
        logger: Logger instance
        method_name: Method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary
    """
    request_id = structlog.contextvars.get_contextvars().get("request_id")
    if request_id:
        event_dict["request_id"] = request_id
    return event_dict


def add_component(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Add component name to log context.

    Args:
        logger: Logger instance
        method_name: Method name
        event_dict: Event dictionary

    Returns:
        Updated event dictionary
    """
    component = structlog.contextvars.get_contextvars().get("component")
    if component:
        event_dict["component"] = component
    return event_dict


def configure_logging() -> None:
    """
    Configure structured logging for the application.

    Sets up:
    - JSON or text output format
    - File and console handlers
    - Correlation ID tracking
    - Request ID tracking
    - Component tracking
    - Execution time measurement
    """
    # Create logs directory if needed
    if settings.logging.log_file_enabled:
        settings.storage.logs_path.mkdir(parents=True, exist_ok=True)

    # Configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, settings.app.log_level.upper()),
    )

    # Shared processors for both stdlib and structlog
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # Add correlation tracking if enabled
    if settings.logging.log_correlation_enabled:
        shared_processors.extend([add_correlation_id, add_request_id, add_component])

    # Configure output format
    if settings.logging.log_format == "json":
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    # Configure structlog
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Configure standard library logging to use structlog
    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(console_handler)
    root_logger.setLevel(getattr(logging, settings.app.log_level.upper()))

    # Add file handler if enabled
    if settings.logging.log_file_enabled:
        log_file = settings.storage.logs_path / f"{settings.app.app_name.lower()}.log"
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


def get_logger(component: str | None = None) -> structlog.stdlib.BoundLogger:
    """
    Get a logger instance for a specific component.

    Args:
        component: Component name (e.g., 'api', 'agent.crawler')

    Returns:
        Bound logger instance with component context

    Example:
        >>> logger = get_logger("api.health")
        >>> logger.info("health_check_called", status="healthy")
    """
    logger = structlog.get_logger()
    if component:
        logger = logger.bind(component=component)
    return logger


class LoggerMixin:
    """
    Mixin to add logging capability to classes.

    Provides a logger instance bound to the class name.

    Example:
        >>> class MyService(LoggerMixin):
        ...     def process(self):
        ...         self.logger.info("processing_started")
    """

    @property
    def logger(self) -> structlog.stdlib.BoundLogger:
        """Get logger bound to the class name."""
        if not hasattr(self, "_logger"):
            component = f"{self.__class__.__module__}.{self.__class__.__name__}"
            self._logger = get_logger(component)
        return self._logger


def log_execution_time(func_name: str) -> Any:
    """
    Decorator to log execution time of a function.

    Args:
        func_name: Name to use in logs

    Returns:
        Decorator function

    Example:
        >>> @log_execution_time("process_data")
        ... async def process():
        ...     pass
    """
    import functools
    import time

    def decorator(func: Any) -> Any:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger(func.__module__)
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(
                    "function_executed",
                    function=func_name,
                    execution_time_seconds=round(execution_time, 3),
                    status="success",
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    "function_failed",
                    function=func_name,
                    execution_time_seconds=round(execution_time, 3),
                    error=str(e),
                    error_type=e.__class__.__name__,
                )
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            logger = get_logger(func.__module__)
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                logger.info(
                    "function_executed",
                    function=func_name,
                    execution_time_seconds=round(execution_time, 3),
                    status="success",
                )
                return result
            except Exception as e:
                execution_time = time.time() - start_time
                logger.error(
                    "function_failed",
                    function=func_name,
                    execution_time_seconds=round(execution_time, 3),
                    error=str(e),
                    error_type=e.__class__.__name__,
                )
                raise

        # Return appropriate wrapper based on function type
        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator

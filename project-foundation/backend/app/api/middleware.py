"""
FastAPI Middleware Components

Custom middleware for request processing.
"""

import time
import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.exceptions import PlatformException
from app.logging import get_logger
from app.models import ErrorResponse

logger = get_logger("middleware")


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    """
    Adds correlation ID to requests for distributed tracing.

    Checks for existing X-Correlation-ID header or generates new one.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Process request and add correlation ID."""
        # Get or generate correlation ID
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Store in request state
        request.state.correlation_id = correlation_id

        # Process request
        response = await call_next(request)

        # Add to response headers
        response.headers["X-Correlation-ID"] = correlation_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all HTTP requests and responses.

    Includes timing, status codes, and correlation IDs.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Log request and response."""
        start_time = time.time()

        # Get correlation ID
        correlation_id = getattr(request.state, "correlation_id", "unknown")

        # Log request
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            correlation_id=correlation_id,
        )

        # Process request
        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Log response
            logger.info(
                "http_response",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                correlation_id=correlation_id,
            )

            return response

        except Exception as e:
            # Calculate duration
            duration_ms = int((time.time() - start_time) * 1000)

            # Log error
            logger.error(
                "http_error",
                method=request.method,
                path=request.url.path,
                error=str(e),
                duration_ms=duration_ms,
                correlation_id=correlation_id,
            )

            raise


# ---------------------------------------------------------------------------
# Phase 4 / 10 — Credential scrubber
# Strips sensitive fields from all log entries and prevents them from leaking
# through any structured log sink.
# ---------------------------------------------------------------------------

# Exact-match sensitive key names (no substring matching to avoid false positives
# like user_prompt, user_id, email_verified, password_changed_at)
_SENSITIVE_KEYS = frozenset({
    "password", "passwd", "pwd", "pass",
    "secret", "token", "api_key", "apikey",
    "credential", "credentials",
    "username",
    "authorization",
})

# Additional suffix-based patterns for compound field names
_SENSITIVE_SUFFIXES = ("_password", "_passwd", "_secret", "_token", "_api_key")


def _is_sensitive_key(k: str) -> bool:
    """Exact match against known sensitive keys, or suffix match for compound names."""
    lower = k.lower()
    return lower in _SENSITIVE_KEYS or lower.endswith(_SENSITIVE_SUFFIXES)


def scrub_sensitive(data: dict) -> dict:
    """
    Recursively replace values whose keys match sensitive patterns with '[REDACTED]'.

    Uses exact key matching (not substring) to avoid false positives on fields
    like 'user_prompt', 'user_id', 'email_verified', 'password_changed_at'.
    Safe to call on any dict; does not mutate the input.
    """
    if not isinstance(data, dict):
        return data
    result = {}
    for k, v in data.items():
        if _is_sensitive_key(k):
            result[k] = "[REDACTED]"
        elif isinstance(v, dict):
            result[k] = scrub_sensitive(v)
        elif isinstance(v, list):
            result[k] = [scrub_sensitive(i) if isinstance(i, dict) else i for i in v]
        else:
            result[k] = v
    return result


class SensitiveDataScrubberMiddleware(BaseHTTPMiddleware):
    """
    Ensures request bodies containing sensitive fields are never written
    to access logs.  The middleware does NOT modify the body — it only
    controls what appears in logs.
    """

    _SENSITIVE_PATHS = {"/api/v1/runs"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in ("POST", "PUT", "PATCH") and request.url.path in self._SENSITIVE_PATHS:
            # Shadow-read the body for logging only — do NOT consume it for the handler
            try:
                import json as _json
                body_bytes = await request.body()
                body = _json.loads(body_bytes) if body_bytes else {}
                safe = scrub_sensitive(body)
                logger.debug("request_body_scrubbed", path=request.url.path, body=safe)
            except Exception:
                pass  # Non-JSON body; skip logging
        return await call_next(request)


class ExceptionHandlerMiddleware(BaseHTTPMiddleware):
    """
    Handles exceptions and converts them to standardized error responses.

    Catches all platform exceptions and converts to appropriate HTTP responses.
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """Handle exceptions."""
        try:
            return await call_next(request)

        except PlatformException as e:
            # Get correlation ID
            correlation_id = getattr(request.state, "correlation_id", None)

            # Create error response
            error_response = ErrorResponse(
                success=False,
                message=e.message,
                error_code=e.__class__.__name__,
                error_details=e.details,
                correlation_id=correlation_id,
            )

            # Log error
            logger.error(
                "platform_exception",
                error_code=e.__class__.__name__,
                message=e.message,
                details=e.details,
                correlation_id=correlation_id,
            )

            # Return appropriate status code
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=e.status_code,
                content=error_response.model_dump(),
            )

        except Exception as e:
            # Get correlation ID
            correlation_id = getattr(request.state, "correlation_id", None)

            # Create generic error response
            error_response = ErrorResponse(
                success=False,
                message="Internal server error",
                error_code="InternalError",
                error_details={"error": str(e)},
                correlation_id=correlation_id,
            )

            # Log unexpected error
            logger.exception(
                "unexpected_exception",
                error=str(e),
                correlation_id=correlation_id,
            )

            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500,
                content=error_response.model_dump(),
            )

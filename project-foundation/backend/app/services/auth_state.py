"""Generic, application-agnostic authentication state and evidence models.

These models describe the runtime *authentication lifecycle* without encoding any
application, provider, hostname, route, cookie name, page title, or success
keyword. They are the single source of truth for structured authentication
outcomes used by :mod:`app.services.crawler_service`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class AuthState(StrEnum):
    """Runtime authentication states (generic — no application semantics)."""

    UNAUTHENTICATED = "unauthenticated"
    AUTHENTICATION_STARTED = "authentication_started"
    CREDENTIALS_SUBMITTED = "credentials_submitted"
    REDIRECTING = "redirecting"
    OAUTH_AUTHENTICATION = "oauth_authentication"
    MFA_REQUIRED = "mfa_required"
    AUTHENTICATED = "authenticated"
    AUTHENTICATION_FAILED = "authentication_failed"
    AUTHENTICATION_TIMEOUT = "authentication_timeout"
    AUTHENTICATION_UNKNOWN = "authentication_unknown"
    AUTH_URL_NOT_FOUND = "auth_url_not_found"
    AUTH_STRATEGY_UNSUPPORTED = "auth_strategy_unsupported"


class AuthFailureReason(StrEnum):
    """Structured, generic authentication failure reasons."""

    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    LOGIN_TIMEOUT = "LOGIN_TIMEOUT"
    MFA_REQUIRED = "MFA_REQUIRED"
    CAPTCHA_REQUIRED = "CAPTCHA_REQUIRED"
    OAUTH_REDIRECT_TIMEOUT = "OAUTH_REDIRECT_TIMEOUT"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTHORIZATION_DENIED = "AUTHORIZATION_DENIED"
    LOGIN_SUCCESS_BUT_VALIDATION_FAILED = "LOGIN_SUCCESS_BUT_VALIDATION_FAILED"
    AUTH_URL_NOT_FOUND = "AUTH_URL_NOT_FOUND"
    AUTH_STRATEGY_UNSUPPORTED = "AUTH_STRATEGY_UNSUPPORTED"
    UNKNOWN_AUTH_ERROR = "UNKNOWN_AUTH_ERROR"


# Transient failure reasons that are safe to retry with a bounded budget.
# Non-transient reasons (invalid credentials, MFA, unsupported strategy, URL not
# found) must NOT be blindly retried.
RETRYABLE_AUTH_FAILURES: frozenset[AuthFailureReason] = frozenset({
    AuthFailureReason.NETWORK_ERROR,
    AuthFailureReason.LOGIN_TIMEOUT,
    AuthFailureReason.OAUTH_REDIRECT_TIMEOUT,
})


# States that are considered terminal "stop protected crawl" outcomes when the
# workflow requires authentication. MFA_REQUIRED is intentionally excluded: it is
# a challenge, not a terminal failure, and is surfaced as a distinct status.
STOP_CRAWL_AUTH_STATES: frozenset[AuthState] = frozenset({
    AuthState.AUTHENTICATION_FAILED,
    AuthState.AUTHENTICATION_TIMEOUT,
    AuthState.AUTH_URL_NOT_FOUND,
    AuthState.AUTH_STRATEGY_UNSUPPORTED,
})


@dataclass
class AuthResult:
    """Structured result of an authentication attempt."""

    state: AuthState
    post_login_url: str | None = None
    failure_reason: AuthFailureReason | None = None
    reason: str = ""

    @property
    def success(self) -> bool:
        return self.state is AuthState.AUTHENTICATED

    @property
    def stop_crawl(self) -> bool:
        """True when the outcome must stop protected crawling."""
        return self.state in STOP_CRAWL_AUTH_STATES or self.state is AuthState.MFA_REQUIRED

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "post_login_url": self.post_login_url,
            "failure_reason": self.failure_reason.value if self.failure_reason else None,
            "reason": self.reason,
        }


@dataclass
class AuthEvidence:
    """Generic runtime evidence observed around an authentication transition.

    No field names or values reference any application, cookie name, page title,
    or route. These are structural, application-agnostic observations only.
    """

    navigation_changed: bool = False
    redirect_completed: bool = False
    login_form_disappeared: bool = False
    cookies_changed: bool = False
    storage_changed: bool = False
    challenge_detected: bool = False
    network_auth_response: bool = False
    error_text_detected: bool = False
    detail: dict[str, Any] = field(default_factory=dict)

"""Unit tests for the generic, application-agnostic authentication logic.

These tests exercise the structured auth state model, the evidence-based
authentication classification, and the strategy/dispatch behavior of
``CrawlerService._perform_login`` — without requiring a live browser.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.infrastructure import BrowserManager
from app.services.auth_state import (
    RETRYABLE_AUTH_FAILURES,
    AuthEvidence,
    AuthFailureReason,
    AuthResult,
    AuthState,
)
from app.services.crawler_service import CrawlerService
from app.services.prompt_builder import AuthContext


def make_service():
    manager = MagicMock(spec=BrowserManager)
    manager.is_initialized = True
    service = CrawlerService(browser_manager=manager)
    # Suppress SSE emits during unit tests.
    service._event_run_id = None
    return service


@pytest.mark.unit
class TestAuthStateModel:
    def test_stop_crawl_states(self):
        for state in (
            AuthState.AUTHENTICATION_FAILED,
            AuthState.AUTHENTICATION_TIMEOUT,
            AuthState.AUTH_URL_NOT_FOUND,
            AuthState.AUTH_STRATEGY_UNSUPPORTED,
            AuthState.MFA_REQUIRED,
        ):
            assert AuthResult(state).stop_crawl is True
        assert AuthResult(AuthState.AUTHENTICATED).stop_crawl is False
        assert AuthResult(AuthState.AUTHENTICATION_UNKNOWN).stop_crawl is False

    def test_retryable_failures_are_transient_only(self):
        assert AuthFailureReason.NETWORK_ERROR in RETRYABLE_AUTH_FAILURES
        assert AuthFailureReason.LOGIN_TIMEOUT in RETRYABLE_AUTH_FAILURES
        assert AuthFailureReason.INVALID_CREDENTIALS not in RETRYABLE_AUTH_FAILURES
        assert AuthFailureReason.MFA_REQUIRED not in RETRYABLE_AUTH_FAILURES
        assert AuthFailureReason.AUTH_STRATEGY_UNSUPPORTED not in RETRYABLE_AUTH_FAILURES
        assert AuthFailureReason.AUTH_URL_NOT_FOUND not in RETRYABLE_AUTH_FAILURES

    def test_auth_result_success_flag(self):
        assert AuthResult(AuthState.AUTHENTICATED).success is True
        assert AuthResult(AuthState.AUTHENTICATION_UNKNOWN).success is False
        assert AuthResult(AuthState.MFA_REQUIRED).success is False


@pytest.mark.unit
class TestEvaluateAuthEvidence:
    @pytest.mark.asyncio
    async def test_authenticated_form_gone_and_cookies_changed(self):
        service = make_service()
        evidence = AuthEvidence(login_form_disappeared=True, cookies_changed=True)
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/home"}, None, None, None)
        assert result.state is AuthState.AUTHENTICATED

    @pytest.mark.asyncio
    async def test_authenticated_form_gone_and_navigation_changed(self):
        service = make_service()
        evidence = AuthEvidence(login_form_disappeared=True, navigation_changed=True)
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/home"}, None, None, None)
        assert result.state is AuthState.AUTHENTICATED

    @pytest.mark.asyncio
    async def test_authenticated_form_gone_and_storage_changed(self):
        service = make_service()
        evidence = AuthEvidence(login_form_disappeared=True, storage_changed=True)
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/login"}, None, None, None)
        assert result.state is AuthState.AUTHENTICATED

    @pytest.mark.asyncio
    async def test_failed_when_nothing_changed(self):
        service = make_service()
        evidence = AuthEvidence()
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/login"}, None, None, None)
        assert result.state is AuthState.AUTHENTICATION_FAILED
        assert result.failure_reason is AuthFailureReason.INVALID_CREDENTIALS

    @pytest.mark.asyncio
    async def test_failed_when_error_text_detected(self):
        service = make_service()
        evidence = AuthEvidence(error_text_detected=True)
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/login"}, None, "invalid username", None)
        assert result.state is AuthState.AUTHENTICATION_FAILED
        assert result.failure_reason is AuthFailureReason.INVALID_CREDENTIALS

    @pytest.mark.asyncio
    async def test_mfa_required_is_not_failure(self):
        service = make_service()
        evidence = AuthEvidence(challenge_detected=True)
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/login"}, "mfa", None, None)
        assert result.state is AuthState.MFA_REQUIRED
        assert result.failure_reason is AuthFailureReason.MFA_REQUIRED
        assert result.success is False

    @pytest.mark.asyncio
    async def test_captcha_is_failure(self):
        service = make_service()
        result = await service._evaluate_auth_evidence(AuthEvidence(), {"url": "https://app/login"}, "captcha", None, None)
        assert result.state is AuthState.AUTHENTICATION_FAILED
        assert result.failure_reason is AuthFailureReason.CAPTCHA_REQUIRED

    @pytest.mark.asyncio
    async def test_unknown_when_form_gone_but_no_state_change(self):
        service = make_service()
        evidence = AuthEvidence(login_form_disappeared=True)
        result = await service._evaluate_auth_evidence(evidence, {"url": "https://app/login"}, None, None, None)
        assert result.state is AuthState.AUTHENTICATION_UNKNOWN

    def test_build_evidence_is_generic(self):
        service = make_service()
        before = {"url": "https://app/login", "password_present": True, "cookie_names": {"a"}, "storage_keys": {"localStorage:x"}}
        after = {"url": "https://app/home", "password_present": False, "cookie_names": {"a", "custom_session_cookie"}, "storage_keys": {"localStorage:x", "sessionStorage:y"}}
        evidence = service._build_auth_evidence(before, after, [], False, False)
        assert evidence.login_form_disappeared is True
        assert evidence.navigation_changed is True
        assert evidence.cookies_changed is True
        assert evidence.storage_changed is True


@pytest.mark.unit
class TestPerformLoginDispatch:
    @pytest.mark.asyncio
    async def test_no_auth_context_returns_unauthenticated(self):
        service = make_service()
        service._auth_context = None
        result = await service._perform_login(AsyncMock())
        assert result.state is AuthState.UNAUTHENTICATED

    @pytest.mark.asyncio
    async def test_form_without_credentials_returns_unauthenticated(self):
        service = make_service()
        service._auth_context = AuthContext(username=None, password=None, login_url="https://app/login", auth_strategy="form")
        result = await service._perform_login(AsyncMock())
        assert result.state is AuthState.UNAUTHENTICATED

    @pytest.mark.asyncio
    async def test_no_login_url_returns_auth_url_not_found(self):
        service = make_service()
        service._auth_context = AuthContext(username="u", password="p", login_url=None, auth_strategy="form")
        result = await service._perform_login(AsyncMock())
        assert result.state is AuthState.AUTH_URL_NOT_FOUND
        assert result.failure_reason is AuthFailureReason.AUTH_URL_NOT_FOUND

    @pytest.mark.asyncio
    async def test_unsupported_strategy_returns_structured_outcome(self):
        service = make_service()
        service._auth_context = AuthContext(username="u", password="p", login_url="https://app/login", auth_strategy="api")
        result = await service._perform_login(AsyncMock())
        assert result.state is AuthState.AUTH_STRATEGY_UNSUPPORTED
        assert result.failure_reason is AuthFailureReason.AUTH_STRATEGY_UNSUPPORTED

    @pytest.mark.asyncio
    async def test_form_login_uses_only_explicit_url(self):
        service = make_service()
        service._auth_context = AuthContext(
            username="u", password="p", login_url="https://app/gateway/session", auth_strategy="form"
        )

        page = AsyncMock()
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        service._locate_username_field = AsyncMock(return_value=page)
        service._locate_password_field = AsyncMock(return_value=page)
        service._locate_submit_button = AsyncMock(return_value=None)
        service._submit_and_wait_for_auth = AsyncMock(
            return_value=AuthResult(AuthState.AUTHENTICATED, post_login_url="https://app/home")
        )

        result = await service._perform_login(context)

        assert result.state is AuthState.AUTHENTICATED
        goto_urls = [c.args[0] for c in page.goto.call_args_list]
        assert goto_urls == ["https://app/gateway/session"]
        # No conventional login route is ever generated/visited.
        for path in ("/login", "/signin", "/sign-in", "/auth/login"):
            assert not any(path in u for u in goto_urls)

    @pytest.mark.asyncio
    async def test_form_login_no_form_returns_auth_url_not_found(self):
        service = make_service()
        service._auth_context = AuthContext(
            username="u", password="p", login_url="https://app/portal", auth_strategy="form"
        )

        page = AsyncMock()
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        service._locate_username_field = AsyncMock(return_value=None)
        service._locate_password_field = AsyncMock(return_value=None)
        service._wait_for_login_form = AsyncMock(return_value=None)
        submit_mock = service._submit_and_wait_for_auth = AsyncMock()

        result = await service._perform_login(context)

        assert result.state is AuthState.AUTH_URL_NOT_FOUND
        assert result.failure_reason is AuthFailureReason.AUTH_URL_NOT_FOUND
        submit_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_transient_failure_is_retried_bounded(self):
        service = make_service()
        service._auth_context = AuthContext(
            username="u", password="p", login_url="https://app/login", auth_strategy="form"
        )

        page = AsyncMock()
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        service._locate_username_field = AsyncMock(return_value=page)
        service._locate_password_field = AsyncMock(return_value=page)
        service._locate_submit_button = AsyncMock(return_value=None)
        service._submit_and_wait_for_auth = AsyncMock(
            return_value=AuthResult(
                AuthState.AUTHENTICATION_TIMEOUT,
                failure_reason=AuthFailureReason.NETWORK_ERROR,
                reason="network",
            )
        )

        result = await service._perform_login(context)

        assert result.state is AuthState.AUTHENTICATION_TIMEOUT
        # Retried up to the bounded limit (2 attempts) for transient failures.
        assert service._submit_and_wait_for_auth.call_count == 2

    @pytest.mark.asyncio
    async def test_non_transient_failure_is_not_retried(self):
        service = make_service()
        service._auth_context = AuthContext(
            username="u", password="p", login_url="https://app/login", auth_strategy="form"
        )

        page = AsyncMock()
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        service._locate_username_field = AsyncMock(return_value=page)
        service._locate_password_field = AsyncMock(return_value=page)
        service._locate_submit_button = AsyncMock(return_value=None)
        service._submit_and_wait_for_auth = AsyncMock(
            return_value=AuthResult(
                AuthState.AUTHENTICATION_FAILED,
                failure_reason=AuthFailureReason.INVALID_CREDENTIALS,
                reason="bad password",
            )
        )

        result = await service._perform_login(context)

        assert result.state is AuthState.AUTHENTICATION_FAILED
        # Invalid credentials are NOT retried.
        assert service._submit_and_wait_for_auth.call_count == 1


@pytest.mark.unit
class TestLoginUrlDiscovery:
    @pytest.mark.asyncio
    async def test_resolve_prefers_explicit_login_url(self):
        service = make_service()
        service._target_url = "https://app.com"
        auth = AuthContext(username="u", password="p", login_url="https://app/gateway", auth_strategy="form")
        url = await service._resolve_login_url(AsyncMock(), auth)
        assert url == "https://app/gateway"

    @pytest.mark.asyncio
    async def test_resolve_discovers_when_no_explicit(self):
        service = make_service()
        service._target_url = "https://app.com"
        auth = AuthContext(username="u", password="p", login_url=None, auth_strategy="form")
        service._discover_login_url = AsyncMock(return_value="https://app.com/login")
        url = await service._resolve_login_url(AsyncMock(), auth)
        assert url == "https://app.com/login"

    @pytest.mark.asyncio
    async def test_resolve_returns_none_when_no_target(self):
        service = make_service()
        auth = AuthContext(username="u", password="p", login_url=None, auth_strategy="form")
        url = await service._resolve_login_url(AsyncMock(), auth)
        assert url is None

    @pytest.mark.asyncio
    async def test_discover_login_url_from_form_on_target(self):
        service = make_service()
        page = AsyncMock()
        page.url = "https://app.com/login"
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)
        service._wait_for_login_form = AsyncMock(return_value=None)
        service._password_field_present = AsyncMock(return_value=True)

        url = await service._discover_login_url(context, "https://app.com")
        assert url == "https://app.com/login"
        page.goto.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_form_login_discovers_when_no_explicit_url(self):
        service = make_service()
        service._target_url = "https://app.com"
        service._auth_context = AuthContext(username="u", password="p", login_url=None, auth_strategy="form")

        page = AsyncMock()
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        # Discovery returns the login page URL from the target.
        service._discover_login_url = AsyncMock(return_value="https://app.com/login")
        service._locate_username_field = AsyncMock(return_value=page)
        service._locate_password_field = AsyncMock(return_value=page)
        service._locate_submit_button = AsyncMock(return_value=None)
        service._submit_and_wait_for_auth = AsyncMock(
            return_value=AuthResult(AuthState.AUTHENTICATED, post_login_url="https://app/home")
        )

        result = await service._perform_login(context)

        assert result.state is AuthState.AUTHENTICATED
        # Navigated to the discovered login URL, never to a conventional route.
        goto_urls = [c.args[0] for c in page.goto.call_args_list]
        assert goto_urls == ["https://app.com/login"]


@pytest.mark.unit
class TestSubmitAndWaitForAuth:
    """Regression: _submit_and_wait_for_auth must return an awaited AuthResult."""

    @pytest.mark.asyncio
    async def test_returns_auth_result_not_coroutine(self):
        service = make_service()
        page = AsyncMock()
        page.keyboard = AsyncMock()

        # Force the "no full navigation" (SPA) fallback path.
        def _boom(*_a, **_k):
            raise RuntimeError("no navigation")

        page.expect_navigation = MagicMock(side_effect=_boom)
        service._capture_auth_snapshot = AsyncMock(side_effect=[
            {"url": "https://app/login", "password_present": True, "cookie_names": {"a"}, "storage_keys": set()},
            {"url": "https://app/home", "password_present": False, "cookie_names": {"a", "b"}, "storage_keys": set()},
        ])
        service._wait_for_auth_completion = AsyncMock(return_value=None)
        service._wait_for_auth_transition_settle = AsyncMock(return_value=None)
        service._detect_auth_challenge = AsyncMock(return_value=None)
        service._detect_auth_error_text = AsyncMock(return_value=None)

        result = await service._submit_and_wait_for_auth(page, None, "https://app/login", None)

        assert isinstance(result, AuthResult)
        assert result.state is AuthState.AUTHENTICATED
        assert result.post_login_url == "https://app/home"

    @pytest.mark.asyncio
    async def test_spa_dom_commit_race_is_not_misclassified_as_failed_login(self):
        """Regression: a Next.js/Angular-style login where the DOM still shows the
        password field right after submit must settle before the verdict snapshot,
        otherwise a successful login is misclassified as INVALID_CREDENTIALS."""
        service = make_service()
        page = AsyncMock()
        page.keyboard = AsyncMock()
        page.text_content = AsyncMock(return_value="dashboard content")
        page.remove_listener = MagicMock()

        def _boom(*_a, **_k):
            raise RuntimeError("no navigation")

        page.expect_navigation = MagicMock(side_effect=_boom)
        service._wait_for_auth_completion = AsyncMock(return_value=None)
        # The DOM swap lags the server response: password field is still present on
        # the first two polls, then disappears once the SPA commits the new route.
        service._password_field_present = AsyncMock(side_effect=[True, True, False])
        service._capture_auth_snapshot = AsyncMock(side_effect=[
            {"url": "https://app/login", "password_present": True, "cookie_names": {"a"}, "storage_keys": set()},
            {"url": "https://app/dashboard", "password_present": False, "cookie_names": {"a", "b"}, "storage_keys": set()},
        ])
        service._detect_auth_challenge = AsyncMock(return_value=None)
        service._detect_auth_error_text = AsyncMock(return_value=None)

        result = await service._submit_and_wait_for_auth(page, None, "https://app/login", None)

        assert service._password_field_present.call_count == 3
        assert result.state is AuthState.AUTHENTICATED
        assert result.post_login_url == "https://app/dashboard"
        assert result.failure_reason is None


@pytest.mark.unit
class TestAuthConfigGating:
    """AuthContext should carry an actionable auth config even without form credentials."""

    def test_has_auth_config_false_when_empty(self):
        assert AuthContext().has_auth_config() is False

    def test_has_auth_config_false_when_partial_credentials(self):
        assert AuthContext(username="u").has_auth_config() is False
        assert AuthContext(password="p").has_auth_config() is False

    def test_has_auth_config_true_with_credentials(self):
        assert AuthContext(username="u", password="p").has_auth_config() is True

    def test_has_auth_config_true_with_login_url_only(self):
        assert AuthContext(login_url="https://app/entry", auth_strategy="sso").has_auth_config() is True

    def test_is_populated_excludes_login_url_only(self):
        auth = AuthContext(login_url="https://app/entry", auth_strategy="sso")
        assert auth.is_populated() is False
        assert auth.has_auth_config() is True


@pytest.mark.unit
class TestPromptParserLoginUrl:
    """B: an explicitly supplied login URL with query parameters survives parsing."""

    def test_login_url_with_query_params_is_preserved(self):
        from app.services.prompt_builder import get_prompt_parser
        parser = get_prompt_parser()
        intent, auth = parser.parse(
            "Test the dashboard. Login URL: https://app.example.com/auth?next=%2Fdashboard"
        )
        assert auth.login_url == "https://app.example.com/auth?next=%2Fdashboard"
        assert auth.has_auth_config() is True


@pytest.mark.unit
class TestCredentialStoreSsoEntryPoint:
    """F: an SSO entry point (login_url, no form credentials) survives persistence."""

    def test_roundtrips_login_url_only_sso(self, tmp_path):
        from app.services.prompt_builder import CredentialStore
        store = CredentialStore()
        store.save(
            str(tmp_path),
            AuthContext(login_url="https://app/sso/entry?next=/home", auth_strategy="sso"),
        )
        loaded = store.load(str(tmp_path))
        assert loaded.has_auth_config() is True
        assert loaded.login_url == "https://app/sso/entry?next=/home"
        assert loaded.auth_strategy == "sso"
        assert loaded.username is None
        assert loaded.password is None

    def test_roundtrips_form_credentials_with_login_url(self, tmp_path):
        from app.services.prompt_builder import CredentialStore
        store = CredentialStore()
        store.save(
            str(tmp_path),
            AuthContext(
                username="u",
                password="p",
                login_url="https://app/session?next=%2Fdashboard",
                auth_strategy="form",
            ),
        )
        loaded = store.load(str(tmp_path))
        assert loaded.username == "u"
        assert loaded.password == "p"
        assert loaded.login_url == "https://app/session?next=%2Fdashboard"

    def test_empty_auth_is_not_saved(self, tmp_path):
        from app.services.prompt_builder import CredentialStore
        store = CredentialStore()
        store.save(str(tmp_path), AuthContext())
        assert not (tmp_path / "run_credentials.enc").exists()
        assert not (tmp_path / "run_credentials.json").exists()


@pytest.mark.unit
class TestOauthSsoEntryPoint:
    """F: SSO/OAuth with a login URL but no form credentials attempts auth."""

    @pytest.mark.asyncio
    async def test_login_url_only_routes_to_oauth_flow(self):
        service = make_service()
        service._auth_context = AuthContext(login_url="https://app/entry/sso", auth_strategy="sso")

        service._perform_oauth_sso_flow = AsyncMock(
            return_value=AuthResult(AuthState.AUTHENTICATED, post_login_url="https://app/home")
        )

        result = await service._perform_login(AsyncMock())

        assert result.state is AuthState.AUTHENTICATED
        service._perform_oauth_sso_flow.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_form_without_credentials_still_returns_unauthenticated(self):
        # Form strategy requires both username and password even with a login URL.
        service = make_service()
        service._auth_context = AuthContext(login_url="https://app/entry/login", auth_strategy="form")
        result = await service._perform_login(AsyncMock())
        assert result.state is AuthState.UNAUTHENTICATED


@pytest.mark.unit
class TestDistinctLoginVsTargetUrl:
    """C: a login URL distinct from the target URL is used for auth, never the target."""

    @pytest.mark.asyncio
    async def test_explicit_login_url_distinct_from_target_is_visited(self):
        service = make_service()
        service._target_url = "https://app.com"
        service._auth_context = AuthContext(
            username="u", password="p", login_url="https://idp.example.com/entry/sso", auth_strategy="form"
        )

        page = AsyncMock()
        page.goto = AsyncMock(return_value=object())
        context = AsyncMock()
        context.new_page = AsyncMock(return_value=page)

        service._locate_username_field = AsyncMock(return_value=page)
        service._locate_password_field = AsyncMock(return_value=page)
        service._locate_submit_button = AsyncMock(return_value=None)
        service._submit_and_wait_for_auth = AsyncMock(
            return_value=AuthResult(AuthState.AUTHENTICATED, post_login_url="https://app.com/home")
        )

        result = await service._perform_login(context)

        assert result.state is AuthState.AUTHENTICATED
        goto_urls = [c.args[0] for c in page.goto.call_args_list]
        assert goto_urls == ["https://idp.example.com/entry/sso"]
        # The target URL is never treated as the login page.
        assert "https://app.com" not in goto_urls



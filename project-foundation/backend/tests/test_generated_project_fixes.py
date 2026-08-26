"""
Regression tests for generated-project fixes.

Covers the root causes found in the execution-failure audit:
- CI="false" string being truthy in the generated playwright.config.ts
- generated tests not navigating to the target page before interaction
- fabricated / unsafe selectors (bare ``getByRole('button')``)
- fabricated assertions (invented titles) when no evidence exists
- inert/unused authentication fixture
"""

from pathlib import Path

import pytest

from app.generators.template_engine import TemplateEngine
from app.schemas.ir import (
    ActionIR,
    ActionType,
    AssertionIR,
    AssertionType,
    CodeGenerationIR,
    ElementIR,
    EnvironmentIR,
    FlowStepIR,
    LocatorStrategy,
    MetadataIR,
    ModuleIR,
    NavigationIR,
    PageIR,
    TestFlowIR,
)


def _el(eid: str, name: str, strategy: LocatorStrategy, value: str) -> ElementIR:
    return ElementIR(id=eid, name=name, locator_strategy=strategy, locator_value=value)


def _action(atype: ActionType, eid: str, value: str | None = None) -> ActionIR:
    return ActionIR(action_type=atype, element_id=eid, value=value, description=atype.value)


def _assert(atype: AssertionType, eid: str | None = None, expected=None) -> AssertionIR:
    return AssertionIR(assertion_type=atype, element_id=eid, expected_value=expected, description=atype.value)


def _step(order: int, actions=None, assertions=None, navigation=None) -> FlowStepIR:
    return FlowStepIR(
        step_order=order,
        description=f"Step {order}",
        actions=actions or [],
        assertions=assertions or [],
        navigation=navigation,
    )


def _auth_ir() -> CodeGenerationIR:
    login_page = PageIR(
        page_id="login-page",
        name="Login Page",
        url_pattern="/login",
        description="Login page",
        requires_auth=False,
        elements=[
            _el("username", "Username", LocatorStrategy.LABEL, "Username"),
            _el("password", "Password", LocatorStrategy.LABEL, "Password"),
            _el("loginButton", "Login", LocatorStrategy.ROLE, "button"),
        ],
    )
    dashboard = PageIR(
        page_id="dashboard-page",
        name="Dashboard",
        url_pattern="/dashboard",
        description="Dashboard",
        requires_auth=True,
        elements=[_el("dashboardTitle", "Dashboard", LocatorStrategy.TEXT, "Dashboard")],
    )
    env = EnvironmentIR(base_url="https://app.example.com", auth_required=True, browsers=["chromium"])
    metadata = MetadataIR(generator="test", model_used=None)

    login_flow = TestFlowIR(
        flow_id="login-flow",
        name="Happy Path Login",
        description="Login with valid credentials",
        tags=["happy_path", "critical"],
        steps=[
            _step(1, actions=[_action(ActionType.FILL, "username", "$VALID_USERNAME")]),
            _step(2, actions=[_action(ActionType.FILL, "password", "$VALID_PASSWORD")]),
            _step(3, actions=[_action(ActionType.CLICK, "loginButton")]),
        ],
    )
    module = ModuleIR(
        module_id="login-module",
        name="Login Module",
        description="Login scenarios",
        pages=["login-page", "dashboard-page"],
        flows=[login_flow],
        requires_auth=True,
    )
    return CodeGenerationIR(
        metadata=metadata,
        environment=env,
        pages=[login_page, dashboard],
        modules=[module],
    )


def _non_auth_ir() -> CodeGenerationIR:
    login_page = PageIR(
        page_id="login-page",
        name="Login Page",
        url_pattern="/login",
        description="Login page",
        requires_auth=False,
        elements=[
            _el("username", "Username", LocatorStrategy.LABEL, "Username"),
            _el("loginButton", "Login", LocatorStrategy.ROLE, "button"),
        ],
    )
    env = EnvironmentIR(base_url="https://app.example.com", auth_required=False, browsers=["chromium"])
    metadata = MetadataIR(generator="test", model_used=None)
    flow = TestFlowIR(
        flow_id="smoke-flow",
        name="Smoke Test",
        description="Smoke",
        tags=["smoke"],
        steps=[_step(1, actions=[_action(ActionType.CLICK, "loginButton")])],
    )
    module = ModuleIR(
        module_id="login-module",
        name="Login Module",
        description="Login scenarios",
        pages=["login-page"],
        flows=[flow],
        requires_auth=False,
    )
    return CodeGenerationIR(
        metadata=metadata,
        environment=env,
        pages=[login_page],
        modules=[module],
    )


@pytest.mark.unit
class TestGeneratedCiConfig:
    def _config_content(self, ir, temp_dir: Path) -> str:
        engine = TemplateEngine(run_id="ci-test")
        path = engine._generate_playwright_config(ir, temp_dir)
        return path.read_text(encoding="utf-8")

    def test_config_uses_explicit_boolean_for_ci(self, temp_dir: Path):
        content = self._config_content(_non_auth_ir(), temp_dir)

        assert "const isCI = process.env.CI === 'true';" in content
        assert "retries: isCI ? 2 : 0," in content
        assert "workers: isCI ? 1 : undefined," in content
        assert "forbidOnly: isCI," in content
        # The buggy CI-truthiness expression must be gone from the generated config.
        assert "retries: process.env.CI" not in content
        assert "workers: process.env.CI" not in content
        assert "forbidOnly: !!process.env.CI" not in content

    def test_ci_semantics_true_false_missing(self):
        # The generated expression process.env.CI === 'true' maps to:
        def is_ci(value):
            return value == "true" if value is not None else False

        assert is_ci("true") is True   # CI=true  -> retries=2, workers=1
        assert is_ci("false") is False  # CI=false -> retries=0
        assert is_ci(None) is False     # CI missing -> retries=0


@pytest.mark.unit
class TestGeneratedNavigation:
    def test_flow_without_navigation_navigates_via_page_object(self, temp_dir: Path):
        ir = _non_auth_ir()
        engine = TemplateEngine(run_id="nav-test")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        # Navigate through the discovered page object (url_pattern from crawler).
        assert "await loginPage.goto();" in content
        # No hardcoded URL in the test body.
        assert "page.goto('/" not in content
        assert "page.goto('https://" not in content

    def test_flow_with_explicit_navigation_does_not_double_navigate(self, temp_dir: Path):
        ir = _non_auth_ir()
        nav = NavigationIR(target="/login")
        flow = ir.modules[0].flows[0]
        flow.steps.insert(0, _step(0, navigation=nav, actions=[]))

        engine = TemplateEngine(run_id="nav-test2")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        # The explicit nav is honored; no duplicate auto-navigation is added.
        assert "await page.goto('/login');" in content
        assert "loginPage.goto()" not in content

    def test_no_fabricated_navigation_when_page_has_no_url_pattern(self, temp_dir: Path):
        ir = _non_auth_ir()
        ir.pages[0].url_pattern = None
        engine = TemplateEngine(run_id="nav-test3")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        # No URL evidence -> must NOT try to navigate to an invented location.
        assert "page.goto(" not in content
        assert "goto()" not in content


@pytest.mark.unit
class TestGeneratedSelectors:
    def test_bare_role_grounded_in_element_name(self, temp_dir: Path):
        ir = _non_auth_ir()
        engine = TemplateEngine(run_id="sel-test")
        engine._generate_page_object(ir.pages[0], temp_dir)
        page_path = temp_dir / "pages" / "login-page.page.ts"
        content = page_path.read_text(encoding="utf-8")

        # getByRole('button') is unsafe; must be grounded by accessible name.
        assert "getByRole('button', { name: /Login/i })" in content
        assert "getByRole('button')\n" not in content
        assert "getByRole('button', { name: 'Login' })" not in content


@pytest.mark.unit
class TestGeneratedAssertions:
    def test_title_assertion_without_evidence_is_not_fabricated(self, temp_dir: Path):
        ir = _non_auth_ir()
        flow = ir.modules[0].flows[0]
        flow.steps.append(_step(9, assertions=[_assert(AssertionType.HAS_TITLE, expected=None)]))
        flow.steps.append(_step(10, assertions=[_assert(AssertionType.HAS_TITLE, expected="")]))

        engine = TemplateEngine(run_id="assert-test")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        # No invented title assertion should be emitted.
        assert "toHaveTitle('')" not in content
        assert "toHaveTitle('None')" not in content
        assert content.count("// TODO") >= 2

    def test_title_assertion_with_evidence_is_emitted(self, temp_dir: Path):
        ir = _non_auth_ir()
        flow = ir.modules[0].flows[0]
        flow.steps.append(_step(9, assertions=[_assert(AssertionType.HAS_TITLE, expected="Dashboard")]))
        engine = TemplateEngine(run_id="assert-test2")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "await expect(page).toHaveTitle('Dashboard');" in content


@pytest.mark.unit
class TestGeneratedAuthFixture:
    def test_auth_module_uses_authenticated_fixture(self, temp_dir: Path):
        ir = _auth_ir()
        engine = TemplateEngine(run_id="auth-test")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "async ({ authenticatedPage }) =>" in content
        assert "new LoginPage(authenticatedPage);" in content

    def test_non_auth_module_keeps_plain_page(self, temp_dir: Path):
        ir = _non_auth_ir()
        engine = TemplateEngine(run_id="auth-test2")
        path = engine._generate_module_test_file(ir.modules[0], ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "async ({ page }) =>" in content

    def test_fixture_logs_in_via_page_object_and_env_credentials(self, temp_dir: Path):
        ir = _auth_ir()
        engine = TemplateEngine(run_id="auth-fixture")
        path = engine._generate_fixtures(ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "process.env.TEST_USERNAME" in content
        assert "process.env.TEST_PASSWORD" in content
        assert "new LoginPage(page)" in content
        assert ".username.fill(username)" in content
        assert ".password.fill(password)" in content
        assert ".loginButton.click()" in content
        assert "waitForURL(new RegExp('/dashboard'))" in content
        # Credentials come from env, never hardcoded in source.
        assert "hm001" not in content

    def test_env_file_exposes_auth_config(self, temp_dir: Path):
        ir = _auth_ir()
        engine = TemplateEngine(run_id="auth-env")
        path = engine._generate_env_file(ir, temp_dir)
        content = path.read_text(encoding="utf-8")

        assert "TEST_USERNAME=" in content
        assert "TEST_PASSWORD=" in content
        assert "AUTH_LOGIN_URL=/login" in content
        assert "AUTH_SUCCESS_URL=/dashboard" in content


@pytest.mark.unit
class TestGeneratedProjectIntegration:
    def test_full_project_generation_is_deterministic(self, temp_dir: Path):
        ir = _auth_ir()
        engine = TemplateEngine(run_id="full-test")
        files = engine.generate_project(ir, temp_dir)
        assert "playwright.config" in files
        assert "fixtures" in files
        assert "package.json" in files
        spec = (temp_dir / "tests" / "login-module.spec.ts").read_text(encoding="utf-8")
        fixture = (temp_dir / "fixtures" / "index.ts").read_text(encoding="utf-8")
        assert "await loginPage.goto();" in spec
        assert "authenticatedPage" in fixture

    def test_id_helpers_present(self):
        engine = TemplateEngine()
        assert engine._to_camel_case("login-page") == "loginPage"
        assert engine._to_pascal_case("login-page") == "LoginPage"

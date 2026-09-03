"""
Unit regression tests for Playwright test-generator fixes:
1. Checkbox locator isolation (no text input fallback)
2. FOCUS and PRESS action generation
3. Environment variable expansion in assertions
4. Password visibility toHaveAttribute assertion
5. Happy path login URL normalization
"""

import pytest
from pathlib import Path
from app.generators.template_engine import TemplateEngine
from app.schemas.ir import (
    CodeGenerationIR,
    ElementIR,
    LocatorStrategy,
    ActionIR,
    ActionType,
    AssertionIR,
    AssertionType,
    PageIR,
    ModuleIR,
    TestFlowIR,
    FlowStepIR
)
from app.agents.ir_generation_agent import IRGenerationAgent


def test_checkbox_locator_does_not_contain_text_input_fallback():
    """Verify checkbox elements never receive generic text/email input fallbacks."""
    engine = TemplateEngine()
    element = ElementIR(
        id="login_remember_me_checkbox",
        name="Remember me",
        locator_strategy=LocatorStrategy.LABEL,
        locator_value="Remember me"
    )

    expr = engine._generate_locator_expression(element)
    assert 'input[type="text"]' not in expr
    assert 'input[type="email"]' not in expr
    assert 'getByRole(\'checkbox\'' in expr or 'input[type="checkbox"]' in expr


def test_focus_and_press_action_code_generation():
    """Verify FOCUS and PRESS actions generate executable Playwright code without TODOs."""
    engine = TemplateEngine()

    # Mock IR
    page = PageIR(
        page_id="login_page",
        name="Login Page",
        description="Login Page",
        elements=[
            ElementIR(id="login_password_input", name="Password", locator_strategy=LocatorStrategy.LABEL, locator_value="Password")
        ]
    )
    ir = CodeGenerationIR(
        metadata={"generator": "test", "ir_version": "1.0"},
        environment={"base_url": "https://example.com", "auth_required": False},
        pages=[page],
        modules=[],
        dependencies=[]
    )

    focus_action = ActionIR(action_type=ActionType.FOCUS, element_id="login_password_input")
    focus_code = engine._generate_action_code(focus_action, ir)
    assert "// TODO" not in focus_code
    assert "await loginPage.loginPasswordInput.focus();" in focus_code

    press_enter_action = ActionIR(action_type=ActionType.PRESS, element_id="login_password_input", value="Enter")
    press_enter_code = engine._generate_action_code(press_enter_action, ir)
    assert "// TODO" not in press_enter_code
    assert "await loginPage.loginPasswordInput.press('Enter');" in press_enter_code

    press_tab_action = ActionIR(action_type=ActionType.PRESS, element_id="login_password_input", value="Tab")
    press_tab_code = engine._generate_action_code(press_tab_action, ir)
    assert "// TODO" not in press_tab_code
    assert "await loginPage.loginPasswordInput.press('Tab');" in press_tab_code


def test_env_var_expansion_in_assertions():
    """Verify $ENV_VAR references in assertions generate process.env calls."""
    engine = TemplateEngine()

    page = PageIR(
        page_id="login_page",
        name="Login Page",
        description="Login Page",
        elements=[
            ElementIR(id="login_password_input", name="Password", locator_strategy=LocatorStrategy.LABEL, locator_value="Password")
        ]
    )
    ir = CodeGenerationIR(
        metadata={"generator": "test", "ir_version": "1.0"},
        environment={"base_url": "https://example.com", "auth_required": False},
        pages=[page],
        modules=[],
        dependencies=[]
    )

    value_assertion = AssertionIR(
        assertion_type=AssertionType.HAS_VALUE,
        element_id="login_password_input",
        expected_value="$VALID_PASSWORD"
    )
    code = engine._generate_assertion_code(value_assertion, ir)
    assert "process.env.VALID_PASSWORD" in code
    assert "'$VALID_PASSWORD'" not in code


def test_password_visibility_attribute_assertion():
    """Verify toHaveAttribute generates expected attribute assertion."""
    engine = TemplateEngine()

    page = PageIR(
        page_id="login_page",
        name="Login Page",
        description="Login Page",
        elements=[
            ElementIR(id="login_password_input", name="Password", locator_strategy=LocatorStrategy.LABEL, locator_value="Password")
        ]
    )
    ir = CodeGenerationIR(
        metadata={"generator": "test", "ir_version": "1.0"},
        environment={"base_url": "https://example.com", "auth_required": False},
        pages=[page],
        modules=[],
        dependencies=[]
    )

    attr_assertion = AssertionIR(
        assertion_type=AssertionType.HAS_ATTRIBUTE,
        element_id="login_password_input",
        expected_value="type=text"
    )
    code = engine._generate_assertion_code(attr_assertion, ir)
    assert "await expect(loginPage.loginPasswordInput).toHaveAttribute('type', 'text');" in code


def test_happy_path_login_url_normalization():
    """Verify IR normalization repairs happy-path login expected URL to post-login route."""
    data = {
        "pages": [
            {"page_id": "login_page", "url_pattern": "https://rrf-portal.dfstage.space/login"},
            {"page_id": "dashboard_page", "url_pattern": "https://rrf-portal.dfstage.space/dashboard"}
        ],
        "modules": [
            {
                "module_id": "login_module",
                "name": "Login Module",
                "flows": [
                    {
                        "flow_id": "TC-004",
                        "name": "Successful login with valid credentials via Login button",
                        "tags": ["happy_path", "login"],
                        "steps": [
                            {
                                "step_order": 1,
                                "description": "Submit login",
                                "assertions": [
                                    {"assertion_type": "toHaveURL", "expected_value": "https://rrf-portal.dfstage.space/login"}
                                ]
                            }
                        ]
                    }
                ]
            }
        ]
    }

    normalized = IRGenerationAgent._normalize_ir_data(data)
    flow = normalized["modules"][0]["flows"][0]
    assertion = flow["steps"][0]["assertions"][0]
    assert assertion["expected_value"] == "https://rrf-portal.dfstage.space/dashboard"

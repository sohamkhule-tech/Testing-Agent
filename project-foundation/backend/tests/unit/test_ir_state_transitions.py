"""
Regression tests for dynamic UI state-transition representation in the IR.

Covers:
1. Password visibility toggle  Show -> Hide -> Show
2. Generic toggle            Off -> On -> Off
3. Accordion                 Collapsed -> Expanded -> Collapsed
4. Menu                      Closed -> Open -> Closed
5. Normal button clicked twice with NO state transition (must stay valid)
6. Existing static IR without state info (must keep working)
7. IR validator detects repeated stateful interaction without a state transition
8. IR validator does NOT reject legitimate repeated interactions (non-stateful)
"""

import pytest

from app.core.ir.ir_validator import IRValidator
from app.generators.template_engine import TemplateEngine
from app.schemas.ir import (
    ActionIR,
    ActionType,
    CodeGenerationIR,
    ElementIR,
    ElementStateIR,
    EnvironmentIR,
    FlowStepIR,
    LocatorStrategy,
    MetadataIR,
    ModuleIR,
    PageIR,
    StateTransitionIR,
    TestFlowIR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _state(state_id: str, value: str, strategy: LocatorStrategy = LocatorStrategy.ROLE) -> ElementStateIR:
    return ElementStateIR(id=state_id, name=state_id, locator_strategy=strategy, locator_value=value)


def _toggle_element(element_id: str = "password_toggle") -> ElementIR:
    return ElementIR(
        id=element_id,
        name="Password Toggle",
        locator_strategy=LocatorStrategy.ROLE,
        locator_value="button:Show password",
        states=[
            _state("hidden", "button:Show password"),
            _state("visible", "button:Hide password"),
        ],
    )


def _build_ir(element: ElementIR, steps: list[FlowStepIR]) -> CodeGenerationIR:
    page = PageIR(
        page_id="login_page",
        name="Login Page",
        description="Login",
        url_pattern="/login",
        elements=[element],
    )
    flow = TestFlowIR(
        flow_id="flow-1",
        name="Toggle flow",
        description="Toggle",
        steps=steps,
    )
    module = ModuleIR(
        module_id="login_module",
        name="Login Module",
        description="Login",
        pages=["login_page"],
        flows=[flow],
    )
    return CodeGenerationIR(
        metadata=MetadataIR(generator="IRGenerationAgent", ir_version="1.0.0"),
        environment=EnvironmentIR(base_url="http://localhost:3000", auth_required=False),
        pages=[page],
        modules=[module],
        dependencies=[],
    )


def _click_action(element_id: str, transition: StateTransitionIR | None = None) -> ActionIR:
    return ActionIR(
        action_type=ActionType.CLICK,
        element_id=element_id,
        state_transition=transition,
    )


def _warnings(ir: CodeGenerationIR):
    result = IRValidator().validate(ir)
    return [i for i in result.issues if i.severity == "warning"]


# ---------------------------------------------------------------------------
# 1. Password visibility toggle  Show -> Hide -> Show
# ---------------------------------------------------------------------------


class TestPasswordToggleCodegen:
    def test_state_locator_expression_uses_state_locator(self):
        engine = TemplateEngine()
        element = _toggle_element()
        visible = element.states[1]
        expr = engine._generate_state_locator_expression(element, visible)
        assert "Hide password" in expr

    def test_action_locator_resolves_from_state(self):
        engine = TemplateEngine()
        element = _toggle_element()
        transition = StateTransitionIR(from_state="visible", to_state="hidden")
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="show", actions=[_click_action("password_toggle", StateTransitionIR(from_state="hidden", to_state="visible"))]),
                FlowStepIR(step_order=2, description="hide", actions=[_click_action("password_toggle", transition)]),
            ],
        )
        action = ir.modules[0].flows[0].steps[1].actions[0]
        locator = engine._resolve_action_locator(action, ir)
        assert locator == "loginPage.passwordToggle_visible"

    def test_second_click_uses_hide_password_locator(self):
        engine = TemplateEngine()
        element = _toggle_element()
        transition = StateTransitionIR(from_state="visible", to_state="hidden")
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="show", actions=[_click_action("password_toggle", StateTransitionIR(from_state="hidden", to_state="visible"))]),
                FlowStepIR(step_order=2, description="hide", actions=[_click_action("password_toggle", transition)]),
            ],
        )
        action = ir.modules[0].flows[0].steps[1].actions[0]
        code = engine._generate_action_code(action, ir)
        assert "loginPage.passwordToggle_visible.click()" in code

    def test_page_object_emits_per_state_locators(self, tmp_path):
        engine = TemplateEngine()
        element = _toggle_element()
        page = PageIR(
            page_id="login_page",
            name="Login Page",
            description="Login",
            url_pattern="/login",
            elements=[element],
        )
        path = engine._generate_page_object(page, tmp_path)
        content = path.read_text(encoding="utf-8")
        assert "readonly passwordToggle_hidden: Locator;" in content
        assert "readonly passwordToggle_visible: Locator;" in content
        assert "Hide password" in content


# ---------------------------------------------------------------------------
# 2-4. Generic toggles (Off/On, Accordion, Menu) — the representation is generic
# ---------------------------------------------------------------------------


class TestGenericToggleRepresentation:
    def test_generic_toggle_off_on_off(self):
        engine = TemplateEngine()
        element = ElementIR(
            id="switch",
            name="Switch",
            locator_strategy=LocatorStrategy.ROLE,
            locator_value="switch:Off",
            states=[
                _state("off", "switch:Off"),
                _state("on", "switch:On"),
            ],
        )
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="on", actions=[_click_action("switch", StateTransitionIR(from_state="off", to_state="on"))]),
                FlowStepIR(step_order=2, description="off", actions=[_click_action("switch", StateTransitionIR(from_state="on", to_state="off"))]),
            ],
        )
        action = ir.modules[0].flows[0].steps[1].actions[0]
        assert engine._resolve_action_locator(action, ir) == "loginPage.switch_on"

    def test_accordion_collapsed_expanded_collapsed(self):
        element = ElementIR(
            id="accordion_header",
            name="Accordion Header",
            locator_strategy=LocatorStrategy.ROLE,
            locator_value="button:Details",
            states=[
                _state("collapsed", "button:Details"),
                _state("expanded", "button:Details"),
            ],
        )
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="expand", actions=[_click_action("accordion_header", StateTransitionIR(from_state="collapsed", to_state="expanded"))]),
                FlowStepIR(step_order=2, description="collapse", actions=[_click_action("accordion_header", StateTransitionIR(from_state="expanded", to_state="collapsed"))]),
            ],
        )
        engine = TemplateEngine()
        action = ir.modules[0].flows[0].steps[1].actions[0]
        assert engine._resolve_action_locator(action, ir) == "loginPage.accordionHeader_expanded"

    def test_menu_closed_open_closed(self):
        element = ElementIR(
            id="menu_button",
            name="Menu Button",
            locator_strategy=LocatorStrategy.ROLE,
            locator_value="button:Menu",
            states=[
                _state("closed", "button:Menu"),
                _state("open", "button:Close"),
            ],
        )
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="open", actions=[_click_action("menu_button", StateTransitionIR(from_state="closed", to_state="open"))]),
                FlowStepIR(step_order=2, description="close", actions=[_click_action("menu_button", StateTransitionIR(from_state="open", to_state="closed"))]),
            ],
        )
        engine = TemplateEngine()
        action = ir.modules[0].flows[0].steps[1].actions[0]
        assert engine._resolve_action_locator(action, ir) == "loginPage.menuButton_open"


# ---------------------------------------------------------------------------
# 5. Normal button clicked twice (no state transition) — must remain valid
# ---------------------------------------------------------------------------


class TestNonStatefulRepeatedClick:
    def test_repeated_click_without_states_produces_no_warning(self):
        element = ElementIR(
            id="normal_button",
            name="Normal Button",
            locator_strategy=LocatorStrategy.ROLE,
            locator_value="button:Refresh",
        )
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="click once", actions=[_click_action("normal_button")]),
                FlowStepIR(step_order=2, description="click twice", actions=[_click_action("normal_button")]),
            ],
        )
        warnings = _warnings(ir)
        assert not any(w.issue_type == "state_transition_missing" for w in warnings)

    def test_repeated_click_without_states_uses_same_locator(self):
        engine = TemplateEngine()
        element = ElementIR(
            id="normal_button",
            name="Normal Button",
            locator_strategy=LocatorStrategy.ROLE,
            locator_value="button:Refresh",
        )
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="click once", actions=[_click_action("normal_button")]),
                FlowStepIR(step_order=2, description="click twice", actions=[_click_action("normal_button")]),
            ],
        )
        action = ir.modules[0].flows[0].steps[1].actions[0]
        assert engine._resolve_action_locator(action, ir) == "loginPage.normalButton"


# ---------------------------------------------------------------------------
# 6. Existing static IR without state info — backward compatible
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_element_without_states_has_empty_states(self):
        element = ElementIR(
            id="username",
            name="Username",
            locator_strategy=LocatorStrategy.LABEL,
            locator_value="Username",
        )
        assert element.states == []

    def test_action_without_state_transition_is_none(self):
        action = ActionIR(action_type=ActionType.CLICK, element_id="x")
        assert action.state_transition is None

    def test_static_element_locator_unchanged(self):
        engine = TemplateEngine()
        element = ElementIR(
            id="username",
            name="Username",
            locator_strategy=LocatorStrategy.LABEL,
            locator_value="Username",
        )
        expr = engine._generate_locator_expression(element)
        assert "getByLabel" in expr
        assert "getByPlaceholder" in expr


# ---------------------------------------------------------------------------
# 7. IR validator detects repeated stateful interaction without transition
# ---------------------------------------------------------------------------


class TestValidatorDetectsMissingTransition:
    def test_stateful_repeated_click_without_transition_warns(self):
        element = _toggle_element()
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="show", actions=[_click_action("password_toggle")]),
                FlowStepIR(step_order=2, description="show again", actions=[_click_action("password_toggle")]),
            ],
        )
        warnings = _warnings(ir)
        assert any(w.issue_type == "state_transition_missing" for w in warnings)

    def test_stateful_repeated_click_with_transition_no_missing_warning(self):
        element = _toggle_element()
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="show", actions=[_click_action("password_toggle", StateTransitionIR(from_state="hidden", to_state="visible"))]),
                FlowStepIR(step_order=2, description="hide", actions=[_click_action("password_toggle", StateTransitionIR(from_state="visible", to_state="hidden"))]),
            ],
        )
        warnings = _warnings(ir)
        assert not any(w.issue_type == "state_transition_missing" for w in warnings)

    def test_unknown_state_reference_warns(self):
        element = _toggle_element()
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="show", actions=[_click_action("password_toggle", StateTransitionIR(from_state="hidden", to_state="visible"))]),
                FlowStepIR(step_order=2, description="hide", actions=[_click_action("password_toggle", StateTransitionIR(from_state="visible", to_state="bogus_state"))]),
            ],
        )
        warnings = _warnings(ir)
        assert any(w.issue_type == "unknown_state" for w in warnings)


# ---------------------------------------------------------------------------
# 8. IR validator does NOT reject legitimate repeated interactions
# ---------------------------------------------------------------------------


class TestValidatorAllowsLegitimateInteractions:
    def test_first_click_on_stateful_element_needs_no_transition(self):
        element = _toggle_element()
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="single show", actions=[_click_action("password_toggle")]),
            ],
        )
        warnings = _warnings(ir)
        assert not any(w.issue_type == "state_transition_missing" for w in warnings)

    def test_warnings_do_not_invalidate_ir(self):
        element = _toggle_element()
        ir = _build_ir(
            element,
            [
                FlowStepIR(step_order=1, description="show", actions=[_click_action("password_toggle")]),
                FlowStepIR(step_order=2, description="show again", actions=[_click_action("password_toggle")]),
            ],
        )
        result = IRValidator().validate(ir)
        # Warnings (not errors) must not invalidate the IR
        assert result.is_valid is True


pytestmark = pytest.mark.unit

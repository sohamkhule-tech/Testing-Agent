"""
Regression and unit tests for TemplateEngine._js_regex() and its
application inside _generate_locator_expression().
"""

import re
import pytest

from app.generators.template_engine import TemplateEngine
from app.schemas.ir import ElementIR, LocatorStrategy


def _elem(elem_id: str, strategy: LocatorStrategy, value: str, name: str = "") -> ElementIR:
    return ElementIR(
        id=elem_id,
        name=name or elem_id,
        locator_strategy=strategy,
        locator_value=value,
    )


def _locator(elem_id: str, strategy: LocatorStrategy, value: str, name: str = "") -> str:
    engine = TemplateEngine()
    element = _elem(elem_id, strategy, value, name)
    return engine._generate_locator_expression(element)


def _assert_no_bare_slash_in_regex(generated: str) -> None:
    regex_literals = re.findall(r"/([^/]*?)/i", generated)
    for body in regex_literals:
        bare = [i for i, ch in enumerate(body)
                if ch == "/" and (i == 0 or body[i - 1] != "\\")]
        assert bare == [], (
            f"Bare unescaped '/' inside regex literal body: /{body}/i\n"
            f"Full expression: {generated}"
        )


class TestJsRegexHelper:
    def test_forward_slash_is_escaped(self):
        assert TemplateEngine._js_regex("a/b") == r"a\/b"

    def test_email_address_slash_user_id(self):
        result = TemplateEngine._js_regex("email address / user id")
        assert r"\/" in result
        bare = [i for i, c in enumerate(result) if c == "/" and (i == 0 or result[i-1] != "\\")]
        assert bare == []

    def test_backslash_is_escaped(self):
        result = TemplateEngine._js_regex("Back\\Slash")
        assert r"\\" in result

    def test_dot_is_escaped(self):
        assert r"\." in TemplateEngine._js_regex("foo.bar")

    def test_asterisk_is_escaped(self):
        assert r"\*" in TemplateEngine._js_regex("a*b")

    def test_plus_is_escaped(self):
        assert r"\+" in TemplateEngine._js_regex("A+B")

    def test_question_mark_is_escaped(self):
        assert r"\?" in TemplateEngine._js_regex("What?")

    def test_caret_is_escaped(self):
        assert r"\^" in TemplateEngine._js_regex("^start")

    def test_dollar_is_escaped(self):
        assert r"\$" in TemplateEngine._js_regex("Price $100.00")

    def test_open_paren_is_escaped(self):
        assert r"\(" in TemplateEngine._js_regex("Search (All)")

    def test_close_paren_is_escaped(self):
        assert r"\)" in TemplateEngine._js_regex("Search (All)")

    def test_open_bracket_is_escaped(self):
        assert r"\[" in TemplateEngine._js_regex("[Required]")

    def test_close_bracket_is_escaped(self):
        assert r"\]" in TemplateEngine._js_regex("[Required]")

    def test_open_brace_is_escaped(self):
        assert r"\{" in TemplateEngine._js_regex("{value}")

    def test_close_brace_is_escaped(self):
        assert r"\}" in TemplateEngine._js_regex("{value}")

    def test_pipe_is_escaped(self):
        assert r"\|" in TemplateEngine._js_regex("A|B")

    def test_plain_text_unchanged(self):
        assert TemplateEngine._js_regex("email") == "email"

    def test_empty_string(self):
        assert TemplateEngine._js_regex("") == ""

    def test_multiple_slashes(self):
        result = TemplateEngine._js_regex("a/b/c")
        assert result.count(r"\/") == 2

    def test_all_metacharacters_combined(self):
        label = "Save/Continue (All) [Req] $100.00 A+B foo.bar What?"
        result = TemplateEngine._js_regex(label)
        bare = [i for i, c in enumerate(result) if c == "/" and (i == 0 or result[i-1] != "\\")]
        assert bare == []


class TestPrimaryRegressionEmailSlash:
    IR_VALUE = "Email Address / User ID"
    LOWER = "email address / user id"

    def test_old_broken_literal_not_present(self):
        generated = _locator("user_field", LocatorStrategy.LABEL, self.IR_VALUE)
        assert f"/{self.LOWER}/i" not in generated, f"Old broken regex still present!\n{generated}"

    def test_escaped_slash_present(self):
        generated = _locator("user_field", LocatorStrategy.LABEL, self.IR_VALUE)
        assert r"\/" in generated

    def test_no_bare_slash_in_any_regex_literal(self):
        _assert_no_bare_slash_in_regex(_locator("user_field", LocatorStrategy.LABEL, self.IR_VALUE))

    def test_still_uses_getByLabel(self):
        assert "getByLabel" in _locator("user_field", LocatorStrategy.LABEL, self.IR_VALUE)

    def test_still_uses_getByPlaceholder(self):
        assert "getByPlaceholder" in _locator("user_field", LocatorStrategy.LABEL, self.IR_VALUE)


class TestLabelUsernameEmailBranch:
    @pytest.mark.parametrize("label,expected_fragment", [
        ("Save/Continue", r"save\/continue"),
        ("Search (All)", r"search\ \(all\)"),
        ("Price $100.00", r"price\ \$100\.00"),
        ("[Required]", r"\[required\]"),
        ("A+B", r"a\+b"),
        ("foo.bar", r"foo\.bar"),
        ("email address / user id", r"email\ address\ \/\ user\ id"),
    ])
    def test_metachar_escaped_in_label_regex(self, label, expected_fragment):
        generated = _locator("user_field", LocatorStrategy.LABEL, label)
        assert expected_fragment in generated, f"Expected '{expected_fragment}' not in:\n{generated}"
        _assert_no_bare_slash_in_regex(generated)

    def test_plain_email_label_unchanged(self):
        assert "getByLabel(/email/i)" in _locator("email_input", LocatorStrategy.LABEL, "Email")

    def test_plain_username_label_unchanged(self):
        assert "getByLabel(/username/i)" in _locator("username_input", LocatorStrategy.LABEL, "Username")

    def test_type_fallback_still_present(self):
        generated = _locator("user_field", LocatorStrategy.LABEL, "Email Address / User ID")
        assert "input[type" in generated


class TestLabelPasswordBranch:
    def test_password_uses_css_selector_not_getByLabel(self):
        generated = _locator("password_field", LocatorStrategy.LABEL, "Password")
        assert "getByLabel" not in generated
        assert "input[type" in generated

    def test_password_with_slash_no_bare_slash(self):
        _assert_no_bare_slash_in_regex(_locator("password_field", LocatorStrategy.LABEL, "Password / PIN"))

    def test_plain_password_getByPlaceholder_unchanged(self):
        assert "getByPlaceholder(/password/i)" in _locator("password_input", LocatorStrategy.LABEL, "Password")


class TestLabelGenericBranch:
    def test_generic_plain_label(self):
        assert r"getByLabel(/search\ query/i)" in _locator("search_box", LocatorStrategy.LABEL, "Search Query")

    def test_generic_label_with_slash(self):
        generated = _locator("field_a", LocatorStrategy.LABEL, "Category / Subcategory")
        _assert_no_bare_slash_in_regex(generated)
        assert r"\/" in generated

    def test_generic_label_with_parens(self):
        _assert_no_bare_slash_in_regex(_locator("field_b", LocatorStrategy.LABEL, "Search (All)"))


class TestRoleStrategyNameSplit:
    def test_plain_role_name_unchanged(self):
        generated = _locator("login_btn", LocatorStrategy.ROLE, "button:Login")
        assert "getByRole('button', { name: /Login/i })" in generated

    def test_role_name_with_slash(self):
        generated = _locator("btn", LocatorStrategy.ROLE, "button:Save/Continue")
        _assert_no_bare_slash_in_regex(generated)
        assert r"\/" in generated

    def test_role_name_with_paren(self):
        _assert_no_bare_slash_in_regex(_locator("btn", LocatorStrategy.ROLE, "button:Search (All)"))

    def test_alert_role_unaffected(self):
        generated = _locator("err", LocatorStrategy.ROLE, "alert:Error Message")
        assert "getByRole('alert')" in generated


class TestRoleStrategyBareElementName:
    def test_plain_element_name(self):
        elem = _elem("submit_btn", LocatorStrategy.ROLE, "button", name="Submit")
        generated = TemplateEngine()._generate_locator_expression(elem)
        assert "getByRole('button', { name: /Submit/i })" in generated

    def test_element_name_with_slash(self):
        elem = _elem("ok_btn", LocatorStrategy.ROLE, "button", name="OK/Cancel")
        generated = TemplateEngine()._generate_locator_expression(elem)
        _assert_no_bare_slash_in_regex(generated)
        assert r"\/" in generated


class TestNormalLabelsUnchanged:
    @pytest.mark.parametrize("label", [
        "Email", "Password", "Username", "First Name",
        "Last Name", "Phone Number", "Remember me", "Submit",
    ])
    def test_plain_label_lowercased_text_in_output(self, label):
        generated = _locator("some_field", LocatorStrategy.LABEL, label)
        escaped_lower = re.escape(label.lower())
        assert escaped_lower in generated


class TestFullStructuralValidity:
    LABELS = [
        ("Email Address / User ID", "user_field"),
        ("Save/Continue", "btn"),
        ("Search (All)", "search_btn"),
        ("[Required]", "req_field"),
        ("A+B", "ab_field"),
        ("foo.bar", "foo_field"),
        ("What's New?", "new_field"),
    ]

    @pytest.mark.parametrize("label,elem_id", LABELS)
    def test_label_strategy_no_bare_slash(self, label, elem_id):
        _assert_no_bare_slash_in_regex(_locator(elem_id, LocatorStrategy.LABEL, label))

    @pytest.mark.parametrize("label,elem_id", LABELS)
    def test_role_strategy_no_bare_slash(self, label, elem_id):
        _assert_no_bare_slash_in_regex(_locator(elem_id, LocatorStrategy.ROLE, f"button:{label}"))

    def test_canonical_regression_full(self):
        generated = _locator("user_field", LocatorStrategy.LABEL, "Email Address / User ID")
        assert "/email address / user id/i" not in generated
        assert r"\/" in generated
        assert "getByLabel" in generated
        _assert_no_bare_slash_in_regex(generated)

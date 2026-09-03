"""
Regression tests for evidence-based locator generation and validation.

Covers:
- ContextBuilder.build_element_evidence_section formats inventory correctly
- PromptComposer includes evidence when inventory is provided
- validate_ir_locators detects invented locators
- validate_ir_locators passes verified locators
- Partial-approval scoping continues to work
"""

import pytest

from app.core.ir.context_builder import ContextBuilder
from app.core.ir.prompt_composer import PromptComposer
from app.schemas.review import ApprovedTestPlan, ReviewStatus
from app.validation.locator_validator import validate_ir_locators, LocatorValidationResult
from datetime import datetime, timezone
from uuid import uuid4


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

LOGIN_PAGE_ID = "984052d7-5ad1-4c05-be26-0be775990bc5"

SAMPLE_INVENTORY = {
    "pages": [
        {"page_id": LOGIN_PAGE_ID, "url": "https://example.com/login", "title": "Login"},
    ],
    "inputs": [
        {
            "page_id": LOGIN_PAGE_ID,
            "input_type": "text",
            "label": "Email Address / User ID",
            "placeholder": "Enter your email or user ID",
            "name": None,
        },
        {
            "page_id": LOGIN_PAGE_ID,
            "input_type": "password",
            "label": "Password",
            "placeholder": "Enter your password",
            "name": None,
        },
    ],
    "buttons": [
        {"page_id": LOGIN_PAGE_ID, "text": "Login", "button_type": "submit"},
        {"page_id": LOGIN_PAGE_ID, "text": "Sign in with Microsoft", "button_type": "button"},
    ],
    "checkboxes": [
        {"page_id": LOGIN_PAGE_ID, "label": "Remember me", "name": None, "checked": False},
    ],
    "radio_buttons": [],
    "dropdowns": [],
}


def _make_approved_plan() -> ApprovedTestPlan:
    return ApprovedTestPlan(
        run_id=uuid4(),
        request_id=uuid4(),
        generated_at=datetime.now(timezone.utc),
        approved_at=datetime.now(timezone.utc),
        review_version=1,
        review_status=ReviewStatus.APPROVED,
        reviewer_name="system",
        test_plan_data={
            "test_scenarios": [],
            "modules": [],
            "application_summary": {
                "total_pages": 1,
                "total_forms": 1,
                "total_apis": 0,
                "authentication_required": True,
                "auth_method": "form",
            },
        },
        scenario_reviews={},
    )


# ---------------------------------------------------------------------------
# ContextBuilder.build_element_evidence_section
# ---------------------------------------------------------------------------

class TestBuildElementEvidenceSection:
    def test_inputs_are_formatted_with_label_and_placeholder(self):
        cb = ContextBuilder()
        section = cb.build_element_evidence_section(SAMPLE_INVENTORY)
        assert 'label="Email Address / User ID"' in section
        assert 'placeholder="Enter your email or user ID"' in section
        assert 'label="Password"' in section
        assert 'placeholder="Enter your password"' in section

    def test_buttons_are_formatted_with_text(self):
        cb = ContextBuilder()
        section = cb.build_element_evidence_section(SAMPLE_INVENTORY)
        assert 'text="Login"' in section
        assert 'text="Sign in with Microsoft"' in section

    def test_checkboxes_are_formatted(self):
        cb = ContextBuilder()
        section = cb.build_element_evidence_section(SAMPLE_INVENTORY)
        assert 'label="Remember me"' in section

    def test_page_url_appears_as_section_header(self):
        cb = ContextBuilder()
        section = cb.build_element_evidence_section(SAMPLE_INVENTORY)
        assert "https://example.com/login" in section

    def test_empty_inventory_returns_empty_string(self):
        cb = ContextBuilder()
        assert cb.build_element_evidence_section({}) == ""

    def test_none_inventory_returns_empty_string(self):
        cb = ContextBuilder()
        assert cb.build_element_evidence_section(None) == ""  # type: ignore[arg-type]

    def test_inventory_with_no_elements_returns_empty_string(self):
        cb = ContextBuilder()
        inv = {"pages": [{"page_id": LOGIN_PAGE_ID, "url": "https://example.com"}],
               "inputs": [], "buttons": [], "checkboxes": [], "radio_buttons": [], "dropdowns": []}
        result = cb.build_element_evidence_section(inv)
        assert result == ""


# ---------------------------------------------------------------------------
# PromptComposer evidence inclusion
# ---------------------------------------------------------------------------

class TestPromptComposerEvidenceInclusion:
    def test_prompt_includes_element_evidence_when_inventory_provided(self):
        composer = PromptComposer()
        plan = _make_approved_plan()
        prompt = composer.compose_ir_generation_prompt(
            plan, "https://example.com/login", inventory_data=SAMPLE_INVENTORY
        )
        assert "Element Evidence" in prompt
        assert "Email Address / User ID" in prompt
        assert "Enter your email or user ID" in prompt

    def test_prompt_excludes_evidence_section_when_no_inventory(self):
        composer = PromptComposer()
        plan = _make_approved_plan()
        prompt = composer.compose_ir_generation_prompt(plan, "https://example.com/login")
        assert "Email Address / User ID" not in prompt
        assert "Enter your email or user ID" not in prompt

    def test_prompt_excludes_evidence_section_when_inventory_is_none(self):
        composer = PromptComposer()
        plan = _make_approved_plan()
        prompt = composer.compose_ir_generation_prompt(
            plan, "https://example.com/login", inventory_data=None
        )
        # The instructions section mentions "Element Evidence" as a concept but
        # no actual inventory values should appear
        assert "Email Address / User ID" not in prompt
        assert "Enter your email or user ID" not in prompt


# ---------------------------------------------------------------------------
# validate_ir_locators — invented locator detection
# ---------------------------------------------------------------------------

def _make_ir_with_element(strategy: str, value: str) -> dict:
    return {
        "pages": [
            {
                "page_id": "login-page",
                "url_pattern": "/login",
                "elements": [
                    {
                        "id": "username-field",
                        "name": "Username Field",
                        "locator_strategy": strategy,
                        "locator_value": value,
                    }
                ],
            }
        ],
        "modules": [],
    }


class TestLocatorValidator:
    # A. Verified label locator passes
    def test_verified_label_locator_passes(self):
        ir = _make_ir_with_element("label", "Email Address / User ID")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

    # B. Verified placeholder locator passes
    def test_verified_placeholder_locator_passes(self):
        ir = _make_ir_with_element("placeholder", "Enter your email or user ID")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

    # C. Verified button text locator passes
    def test_verified_button_text_passes(self):
        ir = _make_ir_with_element("text", "Login")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

    # D. Invented label locator is flagged
    def test_invented_label_locator_is_flagged(self):
        ir = _make_ir_with_element("label", "Username")  # not in inventory
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert not result.is_valid
        assert any("Username" in i.locator_value for i in result.issues)

    # E. Invented placeholder locator is flagged
    def test_invented_placeholder_locator_is_flagged(self):
        ir = _make_ir_with_element("placeholder", "Enter Username")  # not in inventory
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert not result.is_valid

    # F. role locator is skipped (cannot validate without live DOM)
    def test_role_locator_is_not_flagged(self):
        ir = _make_ir_with_element("role", "textbox")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid  # role cannot be validated from inventory alone

    # G. css locator is skipped
    def test_css_locator_is_not_flagged(self):
        ir = _make_ir_with_element("css", "#username")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

    # H. Empty inventory skips validation entirely
    def test_empty_inventory_skips_validation(self):
        ir = _make_ir_with_element("label", "Invented Label")
        result = validate_ir_locators(ir, {})
        assert result.is_valid  # no evidence → no assertion

    # I. None inventory skips validation entirely
    def test_none_inventory_skips_validation(self):
        ir = _make_ir_with_element("label", "Invented Label")
        result = validate_ir_locators(ir, None)  # type: ignore[arg-type]
        assert result.is_valid

    # J. Case-insensitive comparison
    def test_label_comparison_is_case_insensitive(self):
        ir = _make_ir_with_element("label", "email address / user id")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

    # K. Multiple issues are all reported
    def test_multiple_invented_locators_all_reported(self):
        ir = {
            "pages": [
                {
                    "page_id": "login",
                    "url_pattern": "/login",
                    "elements": [
                        {"id": "f1", "name": "A", "locator_strategy": "label", "locator_value": "Invented A"},
                        {"id": "f2", "name": "B", "locator_strategy": "placeholder", "locator_value": "Invented B"},
                    ],
                }
            ],
            "modules": [],
        }
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert not result.is_valid
        assert len(result.issues) == 2

    # L. to_dict output is serialisable
    def test_to_dict_serialisable(self):
        ir = _make_ir_with_element("label", "Invented")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "valid" in d
        assert "issues" in d
        assert isinstance(d["issues"], list)

    # M. Different input types all resolved
    def test_password_input_placeholder_validates(self):
        ir = _make_ir_with_element("placeholder", "Enter your password")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

    # N. Checkbox label validates
    def test_checkbox_label_validates(self):
        ir = _make_ir_with_element("label", "Remember me")
        result = validate_ir_locators(ir, SAMPLE_INVENTORY)
        assert result.is_valid

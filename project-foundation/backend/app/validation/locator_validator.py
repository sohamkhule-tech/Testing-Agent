"""
Locator Validator

Validates that IR-generated locators correspond to element evidence captured
during crawling. Detects invented locators before Playwright execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LocatorIssue:
    element_id: str
    locator_strategy: str
    locator_value: str
    reason: str
    page_url: str = ""


@dataclass
class LocatorValidationResult:
    issues: list[LocatorIssue] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.issues) == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.is_valid,
            "issue_count": len(self.issues),
            "issues": [
                {
                    "element_id": i.element_id,
                    "locator_strategy": i.locator_strategy,
                    "locator_value": i.locator_value,
                    "reason": i.reason,
                    "page_url": i.page_url,
                }
                for i in self.issues
            ],
        }


def _build_evidence_index(inventory_data: dict[str, Any]) -> dict[str, set[str]]:
    """Build a mapping: locator_strategy → set of known values (lowercased).

    Strategies covered: label, placeholder, text (buttons/links), name.
    role and css/xpath cannot be validated from inventory alone without
    rendering the page, so they are excluded from hard validation.
    """
    index: dict[str, set[str]] = {
        "label": set(),
        "placeholder": set(),
        "text": set(),
        "name": set(),
    }

    for inp in inventory_data.get("inputs") or []:
        if inp.get("label"):
            index["label"].add(inp["label"].strip().lower())
        if inp.get("placeholder"):
            index["placeholder"].add(inp["placeholder"].strip().lower())
        if inp.get("name"):
            index["name"].add(inp["name"].strip().lower())

    for btn in inventory_data.get("buttons") or []:
        if btn.get("text"):
            index["text"].add(btn["text"].strip().lower())

    for cb in inventory_data.get("checkboxes") or []:
        if cb.get("label"):
            index["label"].add(cb["label"].strip().lower())
        if cb.get("name"):
            index["name"].add(cb["name"].strip().lower())

    for rb in inventory_data.get("radio_buttons") or []:
        if rb.get("label"):
            index["label"].add(rb["label"].strip().lower())
        if rb.get("name"):
            index["name"].add(rb["name"].strip().lower())

    for dd in inventory_data.get("dropdowns") or []:
        if dd.get("label"):
            index["label"].add(dd["label"].strip().lower())
        if dd.get("name"):
            index["name"].add(dd["name"].strip().lower())

    return index


# Strategies that can be validated against inventory evidence
_VALIDATABLE_STRATEGIES = {"label", "placeholder", "text"}

# Strategies that are inherently untestable without live DOM — we skip them
_SKIP_STRATEGIES = {"role", "css", "xpath", "testId"}


def validate_ir_locators(
    ir_data: dict[str, Any],
    inventory_data: dict[str, Any],
) -> LocatorValidationResult:
    """Validate every IR element's primary locator against inventory evidence.

    Args:
        ir_data: Serialised CodeGenerationIR dict.
        inventory_data: Raw inventory.json dict.

    Returns:
        LocatorValidationResult listing any elements whose locators are not
        supported by the crawled inventory.
    """
    result = LocatorValidationResult()
    if not inventory_data or not isinstance(inventory_data, dict):
        return result  # no evidence → skip validation

    evidence = _build_evidence_index(inventory_data)

    # Build page_id → url mapping
    pages = inventory_data.get("pages") or []
    page_id_to_url = {str(p.get("page_id", "")): p.get("url", "") for p in pages}

    for page in ir_data.get("pages") or []:
        page_url = page.get("url_pattern") or page.get("url") or ""
        # Try to resolve page_id → URL from inventory for better diagnostics
        matched_url = page_url
        for inv_url in page_id_to_url.values():
            if inv_url and (inv_url.endswith(page_url) or page_url in inv_url):
                matched_url = inv_url
                break

        for element in page.get("elements") or []:
            elem_id = element.get("id", "?")
            strategy = (element.get("locator_strategy") or "").lower()
            value = (element.get("locator_value") or "").strip()

            if strategy in _SKIP_STRATEGIES:
                continue  # cannot validate without live DOM

            if strategy not in _VALIDATABLE_STRATEGIES:
                continue

            known_values = evidence.get(strategy, set())
            if value.lower() not in known_values:
                result.issues.append(
                    LocatorIssue(
                        element_id=elem_id,
                        locator_strategy=strategy,
                        locator_value=value,
                        reason=(
                            f"Locator value '{value}' for strategy '{strategy}' was not "
                            f"found in crawled inventory. Possible invented locator."
                        ),
                        page_url=matched_url,
                    )
                )

    return result

from typing import Any

from app.logging import LoggerMixin
from app.schemas.review import ApprovedTestPlan


class ContextBuilder(LoggerMixin):

    def __init__(self) -> None:
        super().__init__()

    def _get_plan_data(self, approved_plan: ApprovedTestPlan) -> dict:
        data = approved_plan.test_plan_data
        return data if isinstance(data, dict) else {}

    def build_application_context(
        self,
        approved_plan: ApprovedTestPlan,
        base_url: str
    ) -> dict[str, Any]:
        plan_data = self._get_plan_data(approved_plan)
        app_summary = plan_data.get("application_summary", {}) or {}

        context = {
            "base_url": base_url,
            "total_pages": app_summary.get("total_pages", 0),
            "total_forms": app_summary.get("total_forms", 0),
            "total_apis": app_summary.get("total_apis", app_summary.get("totalApis", 0)),
            "authentication_required": app_summary.get("authentication_required", False),
            "auth_method": app_summary.get("auth_method", "None"),
            "assumptions": [],
            "constraints": [],
        }

        assumptions_data = plan_data.get("assumptions", {}) or plan_data.get("test_assumptions", {}) or {}
        if isinstance(assumptions_data, dict):
            context["assumptions"] = assumptions_data.get("assumptions", [])
            context["constraints"] = assumptions_data.get("constraints", [])

        return context

    def build_environment_context(
        self,
        approved_plan: ApprovedTestPlan,
        base_url: str
    ) -> dict[str, Any]:
        plan_data = self._get_plan_data(approved_plan)
        app_summary = plan_data.get("application_summary", {}) or {}

        return {
            "base_url": base_url,
            "browsers": ["chromium", "firefox", "webkit"],
            "auth_required": app_summary.get("authentication_required", False),
            "auth_type": app_summary.get("auth_method", "None"),
            "parallel_execution": True,
            "retries": 2,
        }

    def format_context_for_prompt(self, context: dict[str, Any]) -> str:
        lines = ["## Application Context\n"]

        lines.append(f"**Base URL:** `{context.get('base_url', 'Unknown')}`\n")
        lines.append(f"**Pages:** {context.get('total_pages', 0)}")
        lines.append(f"**Forms:** {context.get('total_forms', 0)}")
        lines.append(f"**APIs:** {context.get('total_apis', 0)}")
        lines.append(f"**Authentication:** {context.get('authentication_required', False)}")

        if context.get('auth_method'):
            lines.append(f"**Auth Method:** {context['auth_method']}")

        if context.get('assumptions'):
            lines.append("\n**Assumptions:**")
            for assumption in context['assumptions']:
                lines.append(f"- {assumption}")

        if context.get('constraints'):
            lines.append("\n**Constraints:**")
            for constraint in context['constraints']:
                lines.append(f"- {constraint}")

        return "\n".join(lines)

    def build_element_evidence_section(self, inventory_data: dict[str, Any]) -> str:
        """Build an element evidence section from inventory data for the IR generation prompt.

        Groups inputs, buttons, and checkboxes by page URL so the LLM can select
        locators that are actually present in the crawled DOM.
        """
        if not isinstance(inventory_data, dict):
            return ""

        pages: list[dict] = inventory_data.get("pages") or []
        inputs: list[dict] = inventory_data.get("inputs") or []
        buttons: list[dict] = inventory_data.get("buttons") or []
        checkboxes: list[dict] = inventory_data.get("checkboxes") or []
        radio_buttons: list[dict] = inventory_data.get("radio_buttons") or []
        dropdowns: list[dict] = inventory_data.get("dropdowns") or []

        # Build page_id → URL index
        page_id_to_url: dict[str, str] = {
            str(p.get("page_id", "")): p.get("url", "") for p in pages if p.get("page_id")
        }

        # Collect evidence per page URL
        evidence_by_page: dict[str, list[str]] = {}

        def _page_url(record: dict) -> str:
            pid = str(record.get("page_id", ""))
            return page_id_to_url.get(pid, pid)

        def _append(url: str, line: str) -> None:
            evidence_by_page.setdefault(url, []).append(line)

        for inp in inputs:
            url = _page_url(inp)
            parts = [f"input type={inp.get('input_type', 'text')}"]
            if inp.get("label"):
                parts.append(f'label="{inp["label"]}"')
            if inp.get("placeholder"):
                parts.append(f'placeholder="{inp["placeholder"]}"')
            if inp.get("name"):
                parts.append(f'name="{inp["name"]}"')
            _append(url, "  - " + ", ".join(parts))

        for btn in buttons:
            url = _page_url(btn)
            parts = [f"button type={btn.get('button_type', 'button')}"]
            if btn.get("text"):
                parts.append(f'text="{btn["text"]}"')
            _append(url, "  - " + ", ".join(parts))

        for cb in checkboxes:
            url = _page_url(cb)
            parts = ["checkbox"]
            if cb.get("label"):
                parts.append(f'label="{cb["label"]}"')
            if cb.get("name"):
                parts.append(f'name="{cb["name"]}"')
            _append(url, "  - " + ", ".join(parts))

        for rb in radio_buttons:
            url = _page_url(rb)
            parts = ["radio"]
            if rb.get("label"):
                parts.append(f'label="{rb["label"]}"')
            if rb.get("name"):
                parts.append(f'name="{rb["name"]}"')
            _append(url, "  - " + ", ".join(parts))

        for dd in dropdowns:
            url = _page_url(dd)
            parts = ["select"]
            if dd.get("label"):
                parts.append(f'label="{dd["label"]}"')
            if dd.get("name"):
                parts.append(f'name="{dd["name"]}"')
            _append(url, "  - " + ", ".join(parts))

        if not evidence_by_page:
            return ""

        lines = ["## Element Evidence\n",
                 "The following elements were discovered on each page during crawling.",
                 "Use ONLY these values as locator candidates. Do not invent locators not listed here.\n"]
        for url, element_lines in evidence_by_page.items():
            lines.append(f"### {url}")
            lines.extend(element_lines)
            lines.append("")

        return "\n".join(lines)

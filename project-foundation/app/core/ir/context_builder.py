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

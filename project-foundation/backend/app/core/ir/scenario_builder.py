"""
Scenario Builder for IR Generation Prompts

Builds scenario descriptions from approved test plans.
"""

from typing import Any

from app.logging import LoggerMixin
from app.schemas.review import ApprovedTestPlan


class ScenarioBuilder(LoggerMixin):
    """
    Builds scenario section of prompts.
    
    Single Responsibility: Extract and format test scenarios.
    """

    def __init__(self) -> None:
        """Initialize scenario builder."""
        super().__init__()

    def build_scenarios_data(
        self,
        approved_plan: ApprovedTestPlan
    ) -> list[dict[str, Any]]:
        """
        Build structured scenario data.

        Args:
            approved_plan: Approved test plan

        Returns:
            List of scenario dictionaries
        """
        scenarios = []
        
        for scenario in approved_plan.test_scenarios:
            meta = scenario.get("metadata", {}) if isinstance(scenario, dict) else getattr(scenario, "metadata", {})
            if isinstance(meta, dict):
                scenario_data = {
                    "id": meta.get("id", ""),
                    "title": meta.get("title", ""),
                    "description": meta.get("description", ""),
                    "module": meta.get("module", ""),
                    "priority": meta.get("priority", "medium"),
                    "category": meta.get("category", "functional"),
                    "risk_level": meta.get("risk_level", "medium"),
                    "target_page": meta.get("target_page"),
                    "preconditions": meta.get("preconditions", []),
                    "test_steps": meta.get("test_steps", []),
                    "expected_result": meta.get("expected_result", ""),
                    "required_data": meta.get("required_test_data", []),
                    "tags": meta.get("tags", []),
                    "dependencies": meta.get("dependencies", []),
                }
            else:
                scenario_data = {
                    "id": meta.id,
                    "title": meta.title,
                    "description": meta.description,
                    "module": meta.module,
                    "priority": meta.priority.value if hasattr(meta.priority, "value") else meta.priority,
                    "category": meta.category.value if hasattr(meta.category, "value") else meta.category,
                    "risk_level": meta.risk_level.value if hasattr(meta.risk_level, "value") else meta.risk_level,
                    "target_page": meta.target_page,
                    "preconditions": meta.preconditions,
                    "test_steps": meta.test_steps,
                    "expected_result": meta.expected_result,
                    "required_data": meta.required_test_data,
                    "tags": meta.tags,
                    "dependencies": meta.dependencies,
                }
            scenarios.append(scenario_data)
        
        return scenarios

    def group_scenarios_by_module(
        self,
        scenarios: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Group scenarios by module.

        Args:
            scenarios: List of scenario dictionaries

        Returns:
            Dictionary mapping module names to scenarios
        """
        grouped = {}
        
        for scenario in scenarios:
            module = scenario["module"]
            if module not in grouped:
                grouped[module] = []
            grouped[module].append(scenario)
        
        return grouped

    def format_scenarios_for_prompt(
        self,
        scenarios: list[dict[str, Any]]
    ) -> str:
        """Format scenarios as condensed prompt text for IR generation."""

        lines = [f"## Test Scenarios ({len(scenarios)} approved)\n"]

        for idx, scenario in enumerate(scenarios, 1):
            desc = (scenario.get('description') or '')[:200]
            steps = (scenario.get('test_steps') or [])
            steps_display = '\n'.join(
                f"{i}. {step}"
                for i, step in enumerate(steps[:5], 1)
            )

            lines.append(f"### {idx}: {scenario['title']}")
            lines.append(f"  ID: `{scenario['id']}` | Module: {scenario['module']} | Priority: {scenario['priority']} | Category: {scenario['category']}")
            if scenario.get('target_page'):
                lines.append(f"  Page: {scenario['target_page']}")
            if desc:
                lines.append(f"  Desc: {desc}")
            if steps_display:
                lines.append(f"  Steps:\n{steps_display}")
            if scenario.get('expected_result'):
                lines.append(f"  Expected: {scenario['expected_result'][:150]}")

            deps = scenario.get('dependencies')
            if deps:
                lines.append(f"  Deps: {', '.join(deps[:5])}")
            lines.append("")

        return "\n".join(lines)

    def build_module_summary(
        self,
        grouped_scenarios: dict[str, list[dict[str, Any]]]
    ) -> dict[str, Any]:
        """
        Build summary of modules.

        Args:
            grouped_scenarios: Scenarios grouped by module

        Returns:
            Module summary dictionary
        """
        return {
            "total_modules": len(grouped_scenarios),
            "modules": {
                module: {
                    "scenario_count": len(scenarios),
                    "priorities": [s["priority"] for s in scenarios],
                    "categories": list(set(s["category"] for s in scenarios)),
                }
                for module, scenarios in grouped_scenarios.items()
            },
        }

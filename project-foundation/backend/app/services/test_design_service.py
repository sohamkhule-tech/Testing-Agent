from pathlib import Path

from app.exceptions import ValidationError
from app.logging import LoggerMixin
from app.schemas.inventory import Inventory
from app.schemas.test_plan import TestPlan
from app.utils import load_file, save_file


class TestDesignService(LoggerMixin):
    """
    Service for loading inventory and persisting test plans.

    Validates inventory existence and schema before passing to agent.
    Persists test-plan.json after plan generation.
    """

    def __init__(self) -> None:
        super().__init__()

    async def load_inventory(self, workspace_path: str) -> Inventory:
        """
        Load and validate inventory from workspace.

        Args:
            workspace_path: Run workspace directory path

        Returns:
            Validated Inventory

        Raises:
            ValidationError: If inventory is missing or invalid
        """
        workspace = Path(workspace_path)
        if not workspace.exists():
            raise ValidationError(f"Workspace not found: {workspace_path}")

        inventory_path = workspace / "contracts" / "inventory.json"
        if not inventory_path.exists():
            raise ValidationError(f"Inventory not found: {inventory_path}")

        try:
            data = await load_file(inventory_path)
            return Inventory(**data)
        except Exception as e:
            raise ValidationError(f"Invalid inventory: {str(e)}")

    async def persist_test_plan(
        self, workspace_path: str, test_plan: TestPlan
    ) -> str:
        """
        Persist test plan to workspace contracts directory.

        Args:
            workspace_path: Run workspace directory path
            test_plan: Generated test plan

        Returns:
            Path to persisted JSON file

        Raises:
            ValidationError: If persistence fails
        """
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "test-plan.json"

        try:
            data = test_plan.model_dump(mode="json")
            await save_file(output_path, data)
            self.logger.info(
                "test_plan_persisted",
                path=str(output_path),
                scenarios=test_plan.coverage_summary.total_scenarios,
            )
            return str(output_path)
        except Exception as e:
            raise ValidationError(f"Failed to persist test plan: {str(e)}")

    async def generate_markdown_summary(
        self, workspace_path: str, test_plan: TestPlan
    ) -> str:
        """
        Generate human-readable markdown summary of test plan.

        Args:
            workspace_path: Run workspace directory path
            test_plan: Generated test plan

        Returns:
            Path to persisted markdown file

        Raises:
            ValidationError: If generation fails
        """
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "test-plan.md"

        try:
            markdown_content = self._build_markdown(test_plan)
            output_path.write_text(markdown_content, encoding="utf-8")
            self.logger.info(
                "test_plan_markdown_generated",
                path=str(output_path),
            )
            return str(output_path)
        except Exception as e:
            raise ValidationError(f"Failed to generate markdown summary: {str(e)}")

    def _build_markdown(self, test_plan: TestPlan) -> str:
        """Build markdown content from test plan."""
        lines = []
        
        # Header
        lines.append("# Test Plan Summary")
        lines.append("")
        lines.append(f"**Generated:** {test_plan.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        lines.append(f"**Run ID:** {test_plan.run_id}")
        lines.append("")
        
        # Application Overview
        lines.append("## Application Overview")
        lines.append("")
        app_sum = test_plan.application_summary
        lines.append(f"- **Application:** {app_sum.name}")
        if app_sum.version:
            lines.append(f"- **Version:** {app_sum.version}")
        lines.append(f"- **Total Pages:** {app_sum.total_pages}")
        lines.append(f"- **Total Forms:** {app_sum.total_forms}")
        lines.append(f"- **Total APIs:** {app_sum.total_apis}")
        lines.append(f"- **Authentication Required:** {'Yes' if app_sum.authentication_required else 'No'}")
        lines.append(f"- **Authentication Method:** {app_sum.auth_method}")
        lines.append("")
        
        # Coverage Summary
        lines.append("## Test Coverage Summary")
        lines.append("")
        coverage = test_plan.coverage_summary
        lines.append(f"- **Total Scenarios:** {coverage.total_scenarios}")
        lines.append(f"- **Estimated Duration:** {coverage.estimated_duration_minutes} minutes")
        lines.append("")
        
        if coverage.by_priority:
            lines.append("### By Priority")
            lines.append("")
            for priority, count in sorted(coverage.by_priority.items()):
                lines.append(f"- **{priority.title()}:** {count} scenarios")
            lines.append("")
        
        if coverage.by_category:
            lines.append("### By Category")
            lines.append("")
            for category, count in sorted(coverage.by_category.items()):
                lines.append(f"- **{category.replace('_', ' ').title()}:** {count} scenarios")
            lines.append("")
        
        if coverage.by_module:
            lines.append("### By Module")
            lines.append("")
            for module, count in sorted(coverage.by_module.items()):
                lines.append(f"- **{module}:** {count} scenarios")
            lines.append("")
        
        # Test Modules
        lines.append("## Test Modules")
        lines.append("")
        for module in test_plan.modules:
            lines.append(f"### {module.name}")
            lines.append("")
            lines.append(f"{module.description}")
            lines.append("")
            lines.append(f"**Pages Covered:** {', '.join(module.pages) if module.pages else 'None'}")
            lines.append("")
            lines.append(f"**Scenarios:** {len(module.scenarios)}")
            lines.append("")
            
            if module.scenarios:
                for scenario in module.scenarios:
                    meta = scenario.metadata
                    lines.append(f"#### {meta.id}: {meta.title}")
                    lines.append("")
                    lines.append(f"- **Priority:** {meta.priority}")
                    lines.append(f"- **Category:** {meta.category}")
                    lines.append(f"- **Risk Level:** {meta.risk_level}")
                    if meta.target_page:
                        lines.append(f"- **Target Page:** {meta.target_page}")
                    lines.append("")
                    lines.append(f"**Description:** {meta.description}")
                    lines.append("")
                    
                    if meta.preconditions:
                        lines.append("**Preconditions:**")
                        for precond in meta.preconditions:
                            lines.append(f"- {precond}")
                        lines.append("")
                    
                    if meta.test_steps:
                        lines.append("**Test Steps:**")
                        for i, step in enumerate(meta.test_steps, 1):
                            lines.append(f"{i}. {step}")
                        lines.append("")
                    
                    lines.append(f"**Expected Result:** {meta.expected_result}")
                    lines.append("")
                    
                    if meta.required_test_data:
                        lines.append(f"**Required Test Data:** {', '.join(meta.required_test_data)}")
                        lines.append("")
                    
                    if meta.dependencies:
                        lines.append(f"**Dependencies:** {', '.join(meta.dependencies)}")
                        lines.append("")
                    
                    if meta.tags:
                        lines.append(f"**Tags:** {', '.join(meta.tags)}")
                        lines.append("")
        
        # Test Priorities
        lines.append("## Test Priorities")
        lines.append("")
        priorities = test_plan.test_priorities
        if priorities.critical_paths:
            lines.append(f"### Critical Paths ({len(priorities.critical_paths)})")
            lines.append("")
            for scenario_id in priorities.critical_paths:
                lines.append(f"- {scenario_id}")
            lines.append("")
        
        if priorities.high_priority:
            lines.append(f"### High Priority ({len(priorities.high_priority)})")
            lines.append("")
            for scenario_id in priorities.high_priority:
                lines.append(f"- {scenario_id}")
            lines.append("")
        
        # High Risk Areas
        if test_plan.high_risk_areas:
            lines.append("## High Risk Areas")
            lines.append("")
            for area in test_plan.high_risk_areas:
                lines.append(f"- {area}")
            lines.append("")
        
        # Regression Candidates
        if test_plan.regression_candidates:
            lines.append("## Regression Test Candidates")
            lines.append("")
            for candidate in test_plan.regression_candidates:
                lines.append(f"- {candidate}")
            lines.append("")
        
        # Assumptions
        lines.append("## Test Assumptions")
        lines.append("")
        assumptions = test_plan.assumptions
        if assumptions.assumptions:
            lines.append("### Assumptions")
            for assumption in assumptions.assumptions:
                lines.append(f"- {assumption}")
            lines.append("")
        
        if assumptions.constraints:
            lines.append("### Constraints")
            for constraint in assumptions.constraints:
                lines.append(f"- {constraint}")
            lines.append("")
        
        if assumptions.risks:
            lines.append("### Risks")
            for risk in assumptions.risks:
                lines.append(f"- {risk}")
            lines.append("")
        
        # Recommendations
        if test_plan.accessibility_recommendations:
            lines.append("## Accessibility Recommendations")
            lines.append("")
            for rec in test_plan.accessibility_recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        
        if test_plan.performance_recommendations:
            lines.append("## Performance Recommendations")
            lines.append("")
            for rec in test_plan.performance_recommendations:
                lines.append(f"- {rec}")
            lines.append("")
        
        return "\n".join(lines)

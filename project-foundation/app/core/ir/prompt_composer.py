"""
Prompt Composer for IR Generation

Composes complete prompts from modular components.
"""

from typing import Any

from app.core.ir.context_builder import ContextBuilder
from app.core.ir.instruction_builder import InstructionBuilder
from app.core.ir.scenario_builder import ScenarioBuilder
from app.logging import LoggerMixin
from app.schemas.review import ApprovedTestPlan


class PromptComposer(LoggerMixin):
    """
    Composes complete prompts for IR generation.
    
    Single Responsibility: Combine prompt components into final prompt.
    """

    def __init__(self) -> None:
        """Initialize prompt composer."""
        super().__init__()
        self.context_builder = ContextBuilder()
        self.scenario_builder = ScenarioBuilder()
        self.instruction_builder = InstructionBuilder()

    def compose_ir_generation_prompt(
        self,
        approved_plan: ApprovedTestPlan,
        base_url: str = "http://localhost:3000"
    ) -> str:
        """
        Compose complete IR generation prompt.

        Args:
            approved_plan: Approved test plan
            base_url: Application base URL

        Returns:
            Complete prompt text
        """
        self.logger.info("composing_ir_generation_prompt")

        # Build context
        app_context = self.context_builder.build_application_context(
            approved_plan, base_url
        )
        context_text = self.context_builder.format_context_for_prompt(app_context)

        # Build scenarios
        scenarios_data = self.scenario_builder.build_scenarios_data(approved_plan)
        scenarios_text = self.scenario_builder.format_scenarios_for_prompt(scenarios_data)

        # Build instructions
        instructions = self.instruction_builder.build_ir_generation_instructions()
        validation = self.instruction_builder.build_validation_instructions()
        quality = self.instruction_builder.build_quality_guidelines()

        # Compose prompt
        prompt_parts = [
            instructions,
            "",
            context_text,
            "",
            scenarios_text,
            "",
            validation,
            "",
            quality,
            "",
            "Generate the complete framework-independent IR as valid JSON now.",
        ]

        prompt = "\n".join(prompt_parts)

        self.logger.info(
            "ir_generation_prompt_composed",
            prompt_length=len(prompt),
            scenario_count=len(scenarios_data)
        )

        return prompt

    def compose_ir_refinement_prompt(
        self,
        ir: dict[str, Any],
        validation_issues: list[dict[str, Any]]
    ) -> str:
        """
        Compose prompt for refining IR based on validation issues.

        Args:
            ir: Current IR
            validation_issues: Validation issues to fix

        Returns:
            Refinement prompt
        """
        self.logger.info("composing_ir_refinement_prompt")

        issues_text = []
        for issue in validation_issues:
            issues_text.append(
                f"- **{issue['severity'].upper()}** in {issue['component_type']} "
                f"`{issue['component_id']}`: {issue['message']}"
            )

        prompt = f"""# IR Refinement Required

The generated Intermediate Representation has validation issues that need to be fixed.

## Current IR Summary
- Pages: {len(ir.get('pages', []))}
- Modules: {len(ir.get('modules', []))}
- Total Issues: {len(validation_issues)}

## Validation Issues

{chr(10).join(issues_text)}

## Instructions

1. Review each validation issue
2. Fix the issues in the IR
3. Maintain all existing functionality
4. Ensure no new issues are introduced
5. Return the complete corrected IR as JSON

Generate the refined IR now."""

        return prompt

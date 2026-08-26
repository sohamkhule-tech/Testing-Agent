"""
Constraint Resolver — propagates constraints through all downstream stages.

Ensures that user-specified constraints (scope, auth, data, environment, stop,
test_type) influence every stage of execution.
"""

from __future__ import annotations

from typing import Any

from app.context.execution_planner import ExecutionPlan
from app.logging import LoggerMixin
from app.reasoning.models import Constraint, ReasoningResult


class ConstraintResolver(LoggerMixin):
    """
    Applies constraints from reasoning results to ExecutionPlan and AgentState.
    Constraints propagate through crawler → inventory → test_design → code_gen → execution.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def apply_to_plan(
        self,
        plan: ExecutionPlan,
        reasoning: ReasoningResult,
    ) -> ExecutionPlan:
        """
        Apply all reasoning constraints to the ExecutionPlan's workflow_scope
        and constraints list. Returns the modified plan.
        """
        for constraint in reasoning.constraints:
            self._apply_constraint(constraint, plan, reasoning)

        # Merge execution strategy into plan
        if reasoning.execution_strategy.stopping_conditions:
            plan.constraints.extend(
                f"STOP_CONDITION: {c}" for c in reasoning.execution_strategy.stopping_conditions
            )

        return plan

    def apply_to_agent_state(
        self,
        agent_state: Any,
        reasoning: ReasoningResult,
    ) -> None:
        """Update AgentState fields from reasoning constraints."""
        for constraint in reasoning.constraints:
            if constraint.type == "scope" and constraint.rule:
                if "excluded_modules" in constraint.rule:
                    current = getattr(agent_state, "excluded_modules", []) or []
                    agent_state.excluded_modules = current
            if constraint.type == "auth":
                agent_state.merge(clarification_required=False)

        # Mirror testing intent
        if reasoning.testing_intent.strategies:
            agent_state.merge(priorities=reasoning.testing_intent.strategies)

    def apply_to_config(
        self,
        reasoning: ReasoningResult,
    ) -> dict[str, Any]:
        """Return runtime config overrides from constraints."""
        config: dict[str, Any] = {}
        for constraint in reasoning.constraints:
            if constraint.type == "data" and constraint.rule == "destructive_allowed = false":
                config["destructive_allowed"] = False
            if constraint.type == "environment":
                env = constraint.rule.replace("environment = ", "").strip("'\"")
                config["environment"] = env
        return config

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _apply_constraint(
        self,
        constraint: Constraint,
        plan: ExecutionPlan,
        reasoning: ReasoningResult,
    ) -> None:
        ctype = constraint.type
        applies = constraint.applies_to or []

        if ctype == "scope":
            if "crawler" in applies or not applies:
                excluded_pages = list(plan.workflow_scope.get("excluded_pages") or [])
                for mod in reasoning.testing_intent.excluded_modules:
                    pattern = f"/{mod.lower().replace(' ', '-')}"
                    if pattern not in excluded_pages:
                        excluded_pages.append(pattern)
                plan.workflow_scope["excluded_modules"] = list(reasoning.testing_intent.excluded_modules)
                plan.workflow_scope["excluded_pages"] = excluded_pages

            if "test_design" in applies or not applies:
                plan.workflow_scope["included_modules"] = list(reasoning.testing_intent.focus_modules)
                plan.workflow_scope["coverage_preferences"] = list(reasoning.testing_intent.strategies)

        if ctype == "test_type" and ("execution" in applies or not applies):
            for strategy in reasoning.testing_intent.strategies:
                existing = plan.workflow_scope.get("coverage_preferences") or []
                if strategy not in existing:
                    existing.append(strategy)
                plan.workflow_scope["coverage_preferences"] = existing

        if ctype == "data":
            plan.workflow_scope["destructive_allowed"] = reasoning.testing_intent.destructive_allowed

    def resolve_conversation_update(
        self,
        previous: ReasoningResult,
        update_prompt: str,
        deterministic: bool = True,
    ) -> ReasoningResult:
        """
        Handle conversational refinement: 'Ignore Reports' then 'Actually include Reports'.

        For deterministic mode, we parse the update and merge into the previous result.
        The LLM path handles this via the engine's LLM reasoning with conversation context.
        """
        if not deterministic:
            return previous

        lower = update_prompt.lower()

        if "include" in lower or "actually" in lower:
            prev_excluded = set(previous.testing_intent.excluded_modules) | set(previous.navigation_intent.pages_to_skip)
            for mod in list(prev_excluded):
                if mod.lower() in lower:
                    prev_excluded.discard(mod)
            previous.testing_intent.excluded_modules = [m for m in previous.testing_intent.excluded_modules if m.lower() not in lower]
            previous.navigation_intent.pages_to_skip = [m for m in previous.navigation_intent.pages_to_skip if m.lower() not in lower]

        if "also test" in lower or "and" in lower:
            new_modules = self._extract_new(lower)
            previous.testing_intent.focus_modules = list(set(previous.testing_intent.focus_modules) | set(new_modules))
            previous.navigation_intent.pages_to_visit = list(set(previous.navigation_intent.pages_to_visit) | set(new_modules))

        if "remove" in lower and "constraint" in lower:
            previous.constraints = [c for c in previous.constraints if c.description.lower() not in lower]

        return previous

    @staticmethod
    def _extract_new(text: str) -> list[str]:
        """Extract new module names from an update prompt."""
        import re
        words = re.findall(r"\b[A-Z][a-zA-Z\s]{2,20}\b", text)
        noise = {"Reports", "Login", "Dashboard", "Settings", "Module", "Test", "The", "Also", "Actually", "Include", "Ignore", "And"}
        return [w.strip() for w in words if w.strip() not in noise]

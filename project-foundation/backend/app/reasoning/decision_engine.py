"""
Decision Engine — continue/stop/skip/retry/ask_user/replan before each major step.

Evaluates based on goal, constraints, planner state, execution state, and reasoning —
NOT hardcoded rules. Uses logic gates but is designed to be extended with LLM.
"""

from __future__ import annotations

from typing import Any

from app.execution_engine.execution_graph import GraphNode
from app.logging import LoggerMixin
from app.reasoning.models import Constraint, DecisionNode, ReasoningResult


class DecisionEngine(LoggerMixin):
    """
    Decides whether to continue, stop, skip, retry, ask_user, or replan
    before each execution step.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def decide(
        self,
        *,
        stage: str,
        task_id: str,
        current_status: str,
        reasoning: ReasoningResult | None = None,
        constraints: list[Constraint] | None = None,
        node: GraphNode | None = None,
        last_error: str | None = None,
    ) -> DecisionNode:
        """
        Produce a decision for the next execution step.

        Evaluates stopping conditions, constraints, and failure state.
        """
        constraints = constraints or (reasoning.constraints if reasoning else [])

        # Check stopping conditions first
        stop_decision = self._check_stopping(stage, reasoning, constraints)
        if stop_decision:
            return stop_decision

        # Check current status
        if current_status == "completed":
            return DecisionNode(stage=stage, question=f"Continue after {stage}?", decision="continue", reasoning=f"{stage} completed successfully")

        if current_status == "failed":
            return self._decide_on_failure(stage, task_id, last_error, node)

        if current_status in ("pending", "ready"):
            return DecisionNode(stage=stage, question=f"Start {stage}?", decision="continue", reasoning="Task is ready")

        if current_status == "blocked":
            return DecisionNode(stage=stage, question=f"Proceed despite blocked {stage}?", decision="ask_user", reasoning=f"{stage} is blocked")

        return DecisionNode(stage=stage, question=f"What next for {stage}?", decision="continue", reasoning="Default: proceed")

    def evaluate_constraint(
        self,
        constraint: Constraint,
        current_state: dict[str, Any],
    ) -> bool:
        """Check if a constraint is satisfied given the current state."""
        ctype = constraint.type
        if ctype == "stop":
            stop_after = constraint.rule.replace("stop_after = ", "").strip("'\"")
            if stop_after and current_state.get("current_stage") == stop_after:
                return False
        if ctype == "scope":
            if constraint.rule:
                excluded = constraint.rule.replace("excluded_modules = ", "").strip()
                if excluded and current_state.get("visited_pages"):
                    pass
        if ctype == "data" and constraint.rule == "destructive_allowed = false":
            if current_state.get("attempting_write"):
                return False
        return True

    def all_go_constraints_clear(
        self,
        stage: str,
        constraints: list[Constraint],
        current_state: dict[str, Any],
    ) -> bool:
        """True if no constraint blocks execution at this stage."""
        stage_constraints = [c for c in constraints if not c.applies_to or stage in c.applies_to]
        return all(self.evaluate_constraint(c, current_state) for c in stage_constraints if c.severity == "must")

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _check_stopping(
        self,
        stage: str,
        reasoning: ReasoningResult | None,
        constraints: list[Constraint],
    ) -> DecisionNode | None:
        stopping_conditions = reasoning.execution_strategy.stopping_conditions if reasoning else []
        if not stopping_conditions:
            return None
        lower_stage = stage.lower()
        if any(c.lower() in lower_stage for c in stopping_conditions):
            return DecisionNode(
                stage=stage, question="Should execution continue?",
                decision="stop", reasoning=f"Stopping condition met: stage={stage} matches stopping_conditions",
            )
        return None

    def _decide_on_failure(
        self,
        stage: str,
        task_id: str,
        last_error: str | None,
        node: GraphNode | None,
    ) -> DecisionNode:
        error = last_error or getattr(node, "error", None) or "Unknown error"
        retry_count = getattr(node, "retry_count", 0) if node else 0
        max_retries = getattr(node, "max_retries", 3) if node else 3

        if retry_count < max_retries:
            return DecisionNode(stage=stage, question=f"Retry {stage}?", decision="retry", reasoning=f"Attempt {retry_count + 1}/{max_retries}: {error[:100]}")

        return DecisionNode(stage=stage, question=f"Skip {stage} after failures?", decision="skip", reasoning=f"Retries exhausted ({max_retries}/{max_retries}): {error[:100]}")

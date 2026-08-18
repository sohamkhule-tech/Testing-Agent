"""
GoalCompletionEngine — semantics-free evaluation of observed history against
the intent-derived ExpectedStateGraph.

The engine does NOT know what "Create", "Approval", "Reports", "Login", or any
other business workflow means. It only knows:

1. What the current user's intent requires (the graph).
2. What the ExecutionPlan expects (the graph).
3. What the agent actually executed (evidence history).
4. What evidence was observed (observed states / diffs).
5. Whether the observed state transitions satisfy the expected plan.

A capability being successfully executed (e.g. authenticate()) does NOT
automatically mean GOAL_COMPLETED — the graph decides whether that capability
leads to a prerequisite, a milestone, or the final goal.

A missing ExpectedStateGraph never produces GOAL_COMPLETED and never lifts
scope enforcement — the crawler's ExecutionScopeResolver remains authoritative.
"""

from __future__ import annotations

from typing import Any

from app.graph.expected_state import (
    CompletionEvidence,
    ExpectedStateGraph,
    GoalEvaluation,
    GoalStatus,
)
from app.graph.transition_evaluator import TransitionEvaluator


class GoalCompletionEngine:
    """Evaluates chronological completion evidence against the expected graph."""

    @staticmethod
    def evaluate_history(
        history: list[CompletionEvidence],
        graph: ExpectedStateGraph | None,
    ) -> GoalEvaluation:
        """
        Trace expected transitions chronologically against the observed history.

        Returns:
            GoalEvaluation with status GOAL_COMPLETED / CONTINUE / BLOCKED.
        """
        if graph is None:
            return GoalEvaluation(
                status=GoalStatus.CONTINUE,
                reason="No ExpectedStateGraph available — continuing crawl under ExecutionScopeResolver scope",
                history_index=len(history or []),
            )

        if not graph.transitions:
            return GoalEvaluation(
                status=GoalStatus.CONTINUE,
                reason="Empty expected graph — nothing to satisfy",
                history_index=len(history or []),
            )

        history = history or []
        completed: set[str] = set()
        matched_targets: list[str] = []
        history_index = 0

        for transition in graph.transitions:
            # Prerequisite completion must hold before this transition is possible.
            missing_prereqs = [
                p for p in transition.prerequisites
                if p not in completed and p != graph.initial_state
            ]
            if missing_prereqs:
                return GoalEvaluation(
                    status=GoalStatus.BLOCKED,
                    reason=f"Prerequisites not completed for '{transition.source} -> {transition.target}': {missing_prereqs}",
                    completed_nodes=sorted(completed),
                    matched_transitions=matched_targets,
                    next_expected=transition.target,
                    history_index=history_index,
                )

            matched = False
            for i in range(history_index, len(history)):
                evidence = history[i]
                evaluation = TransitionEvaluator.evaluate(evidence, transition, graph, completed)
                if evaluation.matched:
                    completed.add(transition.target)
                    matched_targets.append(transition.target)
                    history_index = i + 1
                    matched = True
                    break

            if not matched:
                # The goal transition (or a required milestone) has not fired yet.
                # Progress may still be happening — report CONTINUE, never a
                # premature GOAL_COMPLETED.
                return GoalEvaluation(
                    status=GoalStatus.CONTINUE,
                    reason=(
                        f"Awaiting transition '{transition.source} -> {transition.target}' "
                        f"(capability '{transition.capability or 'any'}'): "
                        f"{evaluation.unmet_requirements or 'no matching evidence yet'}"
                    ),
                    completed_nodes=sorted(completed),
                    matched_transitions=matched_targets,
                    next_expected=transition.target,
                    history_index=history_index,
                )

        if graph.goal_state and graph.goal_state in completed:
            return GoalEvaluation(
                status=GoalStatus.GOAL_COMPLETED,
                reason=f"Expected goal state '{graph.goal_state}' reached via planned transitions",
                completed_nodes=sorted(completed),
                matched_transitions=matched_targets,
                next_expected=None,
                history_index=history_index,
            )

        return GoalEvaluation(
            status=GoalStatus.CONTINUE,
            reason=f"All transitions matched but goal state '{graph.goal_state}' not marked final",
            completed_nodes=sorted(completed),
            matched_transitions=matched_targets,
            next_expected=graph.goal_state,
            history_index=history_index,
        )

    @staticmethod
    def evaluate_latest(
        history: list[CompletionEvidence],
        graph: ExpectedStateGraph | None,
    ) -> GoalEvaluation:
        """Evaluate only the most recent evidence against the graph.

        Convenience wrapper that preserves the chronological history while
        performing a single-step evaluation. Kept for callers that want the
        latest decision only.
        """
        return GoalCompletionEngine.evaluate_history(history, graph)

    @staticmethod
    def _state_ok(state: Any, node_name: str, graph: ExpectedStateGraph) -> bool:
        node = graph.node(node_name) if graph else None
        if node is None or not node.state_constraint:
            return True
        from app.graph.expected_state import _satisfies_constraint
        return _satisfies_constraint(state, node.state_constraint)

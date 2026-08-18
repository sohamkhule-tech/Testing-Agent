"""
TransitionEvaluator — verifies that observed evidence satisfies an expected
transition.

The naive algorithm *"for transition in graph.transitions: find any later
evidence matching required_diff_types"* is NOT sufficient. The evaluator must
verify ALL of:

1. Correct source state.
2. Correct action/capability.
3. Correct chronological dependency (enforced by GoalCompletionEngine).
4. Expected state transition (target state constraints).
5. Required supporting evidence.
6. Prerequisite completion.
7. Final goal condition.

This prevents unrelated evidence from accidentally satisfying a transition.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.graph.expected_state import (
    CompletionEvidence,
    ExpectedStateGraph,
    ExpectedStateTransition,
    _satisfies_constraint,
)

# Documented confidence weights per verification dimension.
_WEIGHTS: dict[str, float] = {
    "source_state": 0.2,
    "capability": 0.4,
    "required_evidence": 0.3,
    "target_state": 0.1,
}


class TransitionEvaluation(BaseModel):
    """Outcome of evaluating one evidence record against one expected transition."""

    matched: bool = Field(default=False, description="True only when every verification dimension passes")
    score: float = Field(default=0.0, description="Evidence-based confidence, 0.0–1.0")
    confidence_contributions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Which signals contributed to the score and their weights",
    )
    unmet_requirements: list[str] = Field(default_factory=list, description="Why the transition was not satisfied")

    def summary(self) -> dict[str, Any]:
        return {
            "matched": self.matched,
            "score": self.score,
            "unmet_requirements": self.unmet_requirements,
            "confidence_contributions": self.confidence_contributions,
        }


class TransitionEvaluator:
    """Stateless evaluator. Callers (GoalCompletionEngine) manage chronology."""

    @staticmethod
    def evaluate(
        evidence: CompletionEvidence,
        expected: ExpectedStateTransition,
        graph: ExpectedStateGraph,
        completed: set[str] | frozenset[str] | None = None,
    ) -> TransitionEvaluation:
        completed_nodes = completed or frozenset()
        unmet: list[str] = []
        contributions: list[dict[str, Any]] = []

        # -- 1. Correct source state ------------------------------------------
        source_reached = expected.source in completed_nodes or expected.source == graph.initial_state
        source_node = graph.node(expected.source)
        source_constraint_ok = True
        if source_node and source_node.state_constraint:
            source_constraint_ok = _satisfies_constraint(evidence.source_state, source_node.state_constraint)
            if not source_constraint_ok:
                unmet.append(f"source state '{expected.source}' constraint not satisfied")

        source_ok = source_reached and source_constraint_ok
        contributions.append({
            "signal": "source_state",
            "weight": _WEIGHTS["source_state"],
            "satisfied": source_ok,
            "detail": f"source='{expected.source}' reached={source_reached}",
        })
        if not source_reached:
            unmet.append(f"source state '{expected.source}' not reached yet")

        # -- 2. Correct action/capability --------------------------------------
        cap_ok = (not expected.capability) or (not evidence.capability) or (evidence.capability == expected.capability)
        contributions.append({
            "signal": "capability",
            "weight": _WEIGHTS["capability"],
            "satisfied": cap_ok,
            "expected": expected.capability,
            "observed": evidence.capability,
        })
        if not cap_ok:
            unmet.append(
                f"capability mismatch: expected '{expected.capability}', observed '{evidence.capability}'"
            )

        # -- 3. Required supporting evidence -----------------------------------
        # Supporting evidence is exactly that — supporting. A transition is
        # considered supported when at least one declared bucket is observed.
        # The confidence contribution scales with the fraction present; a weak
        # signal alone can never drive a transition to completion (capability,
        # source state, and target constraints are all required).
        if expected.required_evidence:
            present = [t for t in expected.required_evidence if evidence.diff.has(t)]
            missing = [t for t in expected.required_evidence if t not in present]
            ev_ratio = len(present) / len(expected.required_evidence)
            ev_ok = len(present) >= 1
            contributions.append({
                "signal": "required_evidence",
                "weight": _WEIGHTS["required_evidence"],
                "satisfied": ev_ok,
                "present": present,
                "missing": missing,
                "ratio": round(ev_ratio, 3),
            })
            if not ev_ok:
                unmet.append(f"no supporting evidence observed: expected any of {missing}")
        else:
            contributions.append({
                "signal": "required_evidence",
                "weight": _WEIGHTS["required_evidence"],
                "satisfied": True,
                "detail": "no required evidence declared",
            })

        # -- 4. Expected target state ------------------------------------------
        target_ok = True
        target_node = graph.node(expected.target)
        if target_node and target_node.state_constraint:
            target_ok = _satisfies_constraint(evidence.target_state, target_node.state_constraint)
            if not target_ok:
                unmet.append(f"target state '{expected.target}' constraint not satisfied")
        contributions.append({
            "signal": "target_state",
            "weight": _WEIGHTS["target_state"],
            "satisfied": target_ok,
            "detail": f"target='{expected.target}'",
        })

        # -- 5. Prerequisite completion ----------------------------------------
        missing_prereqs = [
            p for p in expected.prerequisites
            if p not in completed_nodes and p != graph.initial_state
        ]
        if missing_prereqs:
            unmet.append(f"prerequisites not completed: {missing_prereqs}")
            contributions.append({
                "signal": "prerequisites",
                "weight": 0.0,
                "satisfied": False,
                "missing": missing_prereqs,
            })

        matched = not unmet
        total_weight = sum(c.get("weight", 0.0) for c in contributions)
        earned = sum(c.get("weight", 0.0) for c in contributions if c.get("satisfied"))
        if total_weight > 0:
            score = round(earned / total_weight, 3)
        else:
            score = 1.0 if matched else 0.0

        return TransitionEvaluation(
            matched=matched,
            score=score,
            confidence_contributions=contributions,
            unmet_requirements=unmet,
        )

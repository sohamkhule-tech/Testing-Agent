"""
Semantic Expected State Graph — intent-derived, dynamic, semantics-free.

The ``ExpectedStateGraph`` encodes NO business semantics. The engine does not
know what "Create", "Approval", "Reports", or "Login" mean. It only describes
what the current ExecutionPlan expects in terms of generic states, generic
capabilities, prerequisite completion, supporting evidence, and the final goal
state.

The graph is generated dynamically from the user's instruction, the
ReasoningResult (intent), the ExecutionPlan, discovered inventory, available
capabilities and execution dependencies. There are no fixed workflow
templates.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Evidence types — generic, framework-level observation categories.
#
# These are the *supporting* evidence buckets any application can expose. No
# single evidence type may declare goal completion on its own.
# ---------------------------------------------------------------------------
EVIDENCE_AUTH_CHANGED = "auth_changed"
EVIDENCE_NAVIGATION_OCCURRED = "navigation_occurred"
EVIDENCE_ELEMENTS_MUTATED = "elements_mutated"
EVIDENCE_NETWORK_ACTIVITY = "network_activity_detected"
EVIDENCE_STORAGE_CHANGED = "storage_changed"
EVIDENCE_DIALOG_VISIBILITY_CHANGED = "dialog_visibility_changed"

EVIDENCE_TYPES: frozenset[str] = frozenset({
    EVIDENCE_AUTH_CHANGED,
    EVIDENCE_NAVIGATION_OCCURRED,
    EVIDENCE_ELEMENTS_MUTATED,
    EVIDENCE_NETWORK_ACTIVITY,
    EVIDENCE_STORAGE_CHANGED,
    EVIDENCE_DIALOG_VISIBILITY_CHANGED,
})

# Map each evidence type to the StateDiff field that reports it.
_DIFF_FIELD_BY_EVIDENCE: dict[str, str] = {
    EVIDENCE_AUTH_CHANGED: "auth_changed",
    EVIDENCE_NAVIGATION_OCCURRED: "navigation_occurred",
    EVIDENCE_ELEMENTS_MUTATED: "elements_mutated",
    EVIDENCE_NETWORK_ACTIVITY: "network_activity_detected",
    EVIDENCE_STORAGE_CHANGED: "storage_changed",
    EVIDENCE_DIALOG_VISIBILITY_CHANGED: "dialog_visibility_changed",
}


class GoalStatus(StrEnum):
    """Outcome of a goal-completion evaluation."""

    GOAL_COMPLETED = "GOAL_COMPLETED"
    CONTINUE = "CONTINUE"
    BLOCKED = "BLOCKED"


# ---------------------------------------------------------------------------
# Expected State Graph
# ---------------------------------------------------------------------------


class ExpectedStateNode(BaseModel):
    """A single expected state in the intent-derived graph."""

    name: str = Field(..., description="Node name — dynamically derived from the plan, never a hardcoded business string")
    phase: str = Field(default="milestone", description="initial | prerequisite | milestone | goal")
    capability: str = Field(default="", description="Generic capability that transitions into this node")
    description: str = Field(default="", description="Human-readable description of the expected state")
    state_constraint: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional constraints the observed target state must satisfy (e.g. {'authenticated': True})",
    )
    is_final: bool = Field(default=False, description="True when reaching this node completes the goal")


class ExpectedStateTransition(BaseModel):
    """A generic capability-driven transition between two expected states."""

    source: str = Field(..., description="Source node name")
    target: str = Field(..., description="Target node name")
    capability: str = Field(
        default="",
        description="Generic action/capability required (navigate, click, fill, submit, upload, download, select, approve, reject, search, authenticate, wait, api_action, browser_interaction, ...)",
    )
    required_evidence: list[str] = Field(
        default_factory=list,
        description="Supporting evidence types. Never a hard success rule on their own.",
    )
    prerequisites: list[str] = Field(
        default_factory=list,
        description="Node names that must be completed first (in addition to 'source').",
    )
    semantic_change_description: str = Field(
        default="",
        description="Human-readable expected state change derived from the plan.",
    )


class ExpectedStateGraph(BaseModel):
    """Intent-derived, dynamic expected state graph."""

    nodes: list[ExpectedStateNode] = Field(default_factory=list)
    transitions: list[ExpectedStateTransition] = Field(default_factory=list)
    initial_state: str = Field(default="initial", description="Starting node name")
    goal_state: str | None = Field(default=None, description="Goal node whose completion yields GOAL_COMPLETED")
    source: str = Field(default="", description="Origin description (reasoning result, plan, inventory)")

    def node(self, name: str) -> ExpectedStateNode | None:
        for n in self.nodes:
            if n.name == name:
                return n
        return None

    def add_node(self, node: ExpectedStateNode) -> None:
        if self.node(node.name) is None:
            self.nodes.append(node)

    def add_transition(self, transition: ExpectedStateTransition) -> None:
        self.transitions.append(transition)

    def has_goal(self) -> bool:
        goal = self.goal_state
        return goal is not None and self.node(goal) is not None

    def summary(self) -> dict[str, Any]:
        return {
            "initial_state": self.initial_state,
            "goal_state": self.goal_state,
            "node_count": len(self.nodes),
            "transition_count": len(self.transitions),
            "nodes": [n.name for n in self.nodes],
            "transitions": [f"{t.source} -> {t.target}" for t in self.transitions],
        }


# ---------------------------------------------------------------------------
# Observed State & State Diff
# ---------------------------------------------------------------------------


class ObservedState(BaseModel):
    """A semantic snapshot of application state after an action."""

    timestamp: float = Field(default=0.0, description="Unix epoch seconds")
    authenticated: bool = False
    navigation_url_path: str = Field(default="", description="URL path/query only — hostname and domain excluded")
    page_title: str = ""

    # Supporting evidence buckets — observations only, never goal verdicts.
    dom_observations: dict[str, Any] = Field(default_factory=dict)
    network_observations: list[dict[str, Any]] = Field(default_factory=list)
    storage_observations: dict[str, Any] = Field(default_factory=dict)
    accessibility_observations: dict[str, Any] = Field(default_factory=dict)
    browser_events: list[dict[str, Any]] = Field(default_factory=list)
    screenshots: list[dict[str, Any]] = Field(default_factory=list)
    action_results: dict[str, Any] = Field(default_factory=dict)


class StateDiff(BaseModel):
    """Generic structural differences between two observed states."""

    auth_changed: bool = False
    navigation_occurred: bool = False
    elements_mutated: bool = False
    network_activity_detected: bool = False
    storage_changed: bool = False
    dialog_visibility_changed: bool = False
    detail: dict[str, Any] = Field(default_factory=dict)

    def has(self, evidence_type: str) -> bool:
        field = _DIFF_FIELD_BY_EVIDENCE.get(evidence_type)
        if field is None:
            return False
        return bool(getattr(self, field, False))


def _counts_changed(before: dict[str, Any], after: dict[str, Any]) -> bool:
    keys = set(before) | set(after)
    return any(int(before.get(k, 0)) != int(after.get(k, 0)) for k in keys)


def _network_summary(observations: list[dict[str, Any]]) -> list[int]:
    return sorted(int(r.get("status") or 0) for r in observations)


def calculate_state_diff(before: ObservedState, after: ObservedState) -> StateDiff:
    """Compute a generic structural diff between two observed states.

    The diff is purely structural and generic — it never encodes what a
    particular business workflow means.
    """
    diff = StateDiff()

    if after.authenticated != before.authenticated:
        diff.auth_changed = True

    before_path = before.navigation_url_path or ""
    after_path = after.navigation_url_path or ""
    if before_path != after_path:
        diff.navigation_occurred = True

    before_dom = before.dom_observations or {}
    after_dom = after.dom_observations or {}
    if _counts_changed(before_dom, after_dom):
        diff.elements_mutated = True

    before_net = _network_summary(before.network_observations or [])
    after_net = _network_summary(after.network_observations or [])
    if before_net != after_net:
        diff.network_activity_detected = True

    before_storage = before.storage_observations or {}
    after_storage = after.storage_observations or {}
    if before_storage != after_storage:
        diff.storage_changed = True

    before_dialogs = int((before.accessibility_observations or {}).get("visible_dialogs", 0))
    after_dialogs = int((after.accessibility_observations or {}).get("visible_dialogs", 0))
    if before_dialogs != after_dialogs:
        diff.dialog_visibility_changed = True

    diff.detail = {
        "before_path": before_path,
        "after_path": after_path,
        "before_auth": before.authenticated,
        "after_auth": after.authenticated,
    }
    return diff


# ---------------------------------------------------------------------------
# CompletionEvidence
# ---------------------------------------------------------------------------


class CompletionEvidence(BaseModel):
    """Chronological record of one executed action and its observed delta."""

    timestamp: float = Field(default=0.0)
    source_state: ObservedState = Field(default_factory=ObservedState)
    target_state: ObservedState = Field(default_factory=ObservedState)
    diff: StateDiff = Field(default_factory=StateDiff)
    capability: str = Field(default="", description="Generic capability/action that was executed")
    evidence: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Constraint matching (generic — operates only on ObservedState fields)
# ---------------------------------------------------------------------------

_TEXT_FIELD_KEYS = {
    "page_title",
    "navigation_url_path",
}


def _satisfies_constraint(state: ObservedState, constraint: dict[str, Any]) -> bool:
    """Return True when an observed state satisfies a node constraint.

    Supported keys (all generic):
    - ``authenticated``: bool equality on state.authenticated
    - ``page_title``: case-insensitive substring on state.page_title
    - ``navigation_url_path``: case-insensitive substring on state.navigation_url_path
    - ``text_pattern``: regex against "{navigation_url_path} {page_title}"
    - ``url_path_not_pattern``: regex must NOT match navigation_url_path
    - ``<state field>``: equality on any ObservedState field
    """
    for key, value in (constraint or {}).items():
        if key == "authenticated":
            if state.authenticated != bool(value):
                return False
        elif key == "page_title":
            if value and value.lower() not in (state.page_title or "").lower():
                return False
        elif key == "navigation_url_path":
            if value and value.lower() not in (state.navigation_url_path or "").lower():
                return False
        elif key == "text_pattern":
            text = f"{state.navigation_url_path or ''} {state.page_title or ''}"
            try:
                if not re.search(str(value), text, re.IGNORECASE):
                    return False
            except re.error:
                if str(value).lower() not in text.lower():
                    return False
        elif key == "url_path_not_pattern":
            try:
                if re.search(str(value), state.navigation_url_path or "", re.IGNORECASE):
                    return False
            except re.error:
                if str(value).lower() in (state.navigation_url_path or "").lower():
                    return False
        elif key in _TEXT_FIELD_KEYS:
            # equality fallback
            if getattr(state, key, None) != value:
                return False
        else:
            if key.startswith("dom."):
                field = key.split(".", 1)[1]
                if (state.dom_observations or {}).get(field) != value:
                    return False
            elif getattr(state, key, None) != value:
                return False
    return True


# ---------------------------------------------------------------------------
# GoalEvaluation
# ---------------------------------------------------------------------------


class GoalEvaluation(BaseModel):
    """Result of evaluating the chronological history against the graph."""

    status: GoalStatus = GoalStatus.CONTINUE
    matched_transitions: list[str] = Field(default_factory=list, description="Transition targets satisfied, in order")
    completed_nodes: list[str] = Field(default_factory=list, description="Nodes completed as prerequisites/milestones")
    next_expected: str | None = Field(default=None, description="Target of the transition currently awaited")
    reason: str = ""
    history_index: int = Field(default=0, description="Number of evidence records consumed")

    @property
    def goal_achieved(self) -> bool:
        return self.status == GoalStatus.GOAL_COMPLETED

    def as_completion_result(self) -> dict[str, Any]:
        """Backward-compatible mapping for callers that expect a criteria result."""
        return {
            "satisfied": self.goal_achieved,
            "matched_criteria": list(self.matched_transitions),
            "reason": self.reason,
        }

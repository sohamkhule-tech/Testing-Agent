"""
Reasoning Models — structured output from the Reasoning Engine.

All models are serializable JSON. Designed to enrich ExecutionPlan
without replacing or duplicating it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BusinessIntent(BaseModel):
    """What the user really wants to achieve (business-level)."""

    goal: str | None = Field(None, description="Business objective (e.g. 'Verify login is reliable')")
    risk_level: str = Field(default="medium", description="high | medium | low")
    domain: str | None = Field(None, description="Business domain (e.g. HR, Finance)")
    expected_deliverables: list[str] = Field(default_factory=list, description="What the user expects as output")


class WorkflowIntent(BaseModel):
    """User journey as a workflow, not individual pages."""

    name: str | None = Field(None, description="Workflow name (e.g. 'Create RRF')")
    steps: list[str] = Field(default_factory=list, description="Ordered workflow steps")
    entry_point: str | None = Field(None, description="Starting page/action")
    exit_point: str | None = Field(None, description="Where the workflow should stop")
    dependencies: list[str] = Field(default_factory=list, description="Pre-requisite workflows")


class NavigationIntent(BaseModel):
    """How the agent should navigate the application."""

    start_url: str | None = None
    pages_to_visit: list[str] = Field(default_factory=list)
    pages_to_skip: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=3)


class TestingIntent(BaseModel):
    """What and how to test."""

    strategies: list[str] = Field(default_factory=list, description="smoke | boundary | negative | positive | security | regression")
    focus_modules: list[str] = Field(default_factory=list)
    excluded_modules: list[str] = Field(default_factory=list)
    auth_required: bool = False
    destructive_allowed: bool = Field(default=False, description="Whether destructive actions are permitted")


class Constraint(BaseModel):
    """An execution constraint that propagates through all downstream stages."""

    type: str = Field(..., description="scope | auth | data | environment | stop | test_type")
    description: str = Field(..., description="Human-readable constraint")
    rule: str = Field(..., description="Machine-interpretable rule (JSON path or simple predicate)")
    severity: str = Field(default="must", description="must | should | prefer")
    applies_to: list[str] = Field(default_factory=list, description="Stages this constraint affects")


class DecisionNode(BaseModel):
    """A single decision made by the Decision Engine."""

    stage: str = Field(..., description="Workflow stage where decision was made")
    question: str = Field(..., description="What was being decided")
    decision: str = Field(..., description="continue | stop | skip | retry | ask_user | replan")
    reasoning: str = Field(default="", description="Why this decision was made")
    timestamp: str = Field(default="", description="ISO timestamp")
    outcome: str | None = Field(None, description="What happened after the decision")


class CompletionCriterion(BaseModel):
    """A single evaluable goal completion criterion.

    Retained for backward compatibility with callers that supply criteria
    explicitly. The ReasoningEngine now derives completion from a dynamic
    ``ExpectedStateGraph``; the generic engine no longer generates business
    keywords (success/confirm/thank) or URL/title regexes itself.
    """

    description: str = Field(..., description="Human readable description of what must be satisfied")
    signal: str = Field(..., description="auth_success | url_changed | page_title_matches | element_absent | page_reached | form_submitted | action_completed")
    target_pattern: str = Field(default="", description="URL, title pattern or selector regex")
    required: bool = Field(default=True, description="Whether this criterion must be satisfied")


class CompletionResult(BaseModel):
    """Outcome of evaluating completion criteria."""

    satisfied: bool = Field(..., description="Whether all required completion criteria are satisfied")
    matched_criteria: list[str] = Field(default_factory=list, description="Descriptions of criteria satisfied")
    reason: str = Field(default="", description="Explanation of evaluation result")


class ExecutionStrategy(BaseModel):
    """How the agent should execute — derived from reasoning."""

    approach: str = Field(default="sequential", description="sequential | parallel | conditional")
    priority_ordering: list[str] = Field(default_factory=list, description="Ordered list of what to execute first")
    stopping_conditions: list[str] = Field(default_factory=list, description="Conditions that halt execution")
    completion_criteria: list[dict[str, Any]] = Field(default_factory=list, description="Evaluable completion criteria (backward-compatible summary)")
    risk_mitigation: list[str] = Field(default_factory=list, description="How to handle risks")


class ConfidenceDetails(BaseModel):
    """Documented, evidence-backed reasoning confidence (not an arbitrary value)."""

    score: float = Field(default=0.0, description="0.0–1.0 overall confidence")
    formula: str = Field(default="", description="Documented formula used to compute the score")
    contributions: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Each signal/evidence that contributed to the score and its weight",
    )
    evidence: list[str] = Field(default_factory=list, description="Raw signals that informed the score")


class ReasoningResult(BaseModel):
    """
    Structured output from the Reasoning Engine.

    This enriches the ExecutionPlan — does NOT replace it.
    """

    detected_intent: str | None = Field(None, description="Brief summary of what the user wants")
    business_intent: BusinessIntent = Field(default_factory=BusinessIntent)
    workflow_intent: WorkflowIntent = Field(default_factory=WorkflowIntent)
    navigation_intent: NavigationIntent = Field(default_factory=NavigationIntent)
    testing_intent: TestingIntent = Field(default_factory=TestingIntent)
    constraints: list[Constraint] = Field(default_factory=list)
    execution_strategy: ExecutionStrategy = Field(default_factory=ExecutionStrategy)
    completion_criteria: list[CompletionCriterion] = Field(default_factory=list, description="Inferred goal completion criteria (backward-compatible summary)")
    expected_state_graph: dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic ExpectedStateGraph serialized from intent — the authoritative completion contract",
    )
    decisions: list[DecisionNode] = Field(default_factory=list)
    confidence: float = Field(default=0.0, description="0.0–1.0 reasoning confidence")
    confidence_details: ConfidenceDetails | None = Field(
        default=None,
        description="Documented confidence computation with evidence contributions",
    )

    def summary(self) -> dict[str, Any]:
        """Serialise to a plain dict for transport/persistence."""
        return self.model_dump(mode="json")


class ReasoningTrace(BaseModel):
    """
    Debug-only trace of reasoning decisions. Never exposed to UI in raw form —
    only concise decision summaries are surfaced.
    """

    run_id: str = Field(default="")
    raw_prompt: str | None = Field(None)
    detected_intent: str | None = Field(None)
    extracted_constraints: list[str] = Field(default_factory=list)
    decisions: list[DecisionNode] = Field(default_factory=list)
    plan_updates: int = Field(default=0)
    execution_strategy: str | None = Field(None)
    confidence_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Documented confidence computation with contributing evidence",
    )
    expected_state_graph: dict[str, Any] = Field(
        default_factory=dict,
        description="Serialized dynamic ExpectedStateGraph (debug visibility)",
    )

    def add_decision(self, decision: DecisionNode) -> None:
        self.decisions.append(decision)

    def trace_summary(self) -> dict[str, Any]:
        """Concise summary suitable for logs and UI."""
        return {
            "detected_intent": self.detected_intent,
            "constraint_count": len(self.extracted_constraints),
            "decision_count": len(self.decisions),
            "plan_updates": self.plan_updates,
            "strategy": self.execution_strategy,
            "confidence": (self.confidence_details or {}).get("score", 0.0),
        }

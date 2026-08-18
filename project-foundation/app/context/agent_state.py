"""
AgentState — Canonical Intent-Preservation State

``AgentState`` is the single typed carrier that preserves the user's original
intent end-to-end across every workflow stage:

    Frontend → API → Execution Planner → Crawler → Inventory → Test Design
    → Human Review → Code Generation → Execution → Reporting

It keeps the original prompt verbatim, the structured parsed intent, the
execution plan, and each stage's output so that no downstream stage ever
loses the context it needs.

SECURITY
--------
``credentials`` intentionally holds transient, in-memory credentials. It must
NEVER be logged, emitted in events, or written to disk. Use
``AgentState.redacted()`` / ``AgentState.to_serializable(redact_credentials=True)``
for anything that leaves the process.
"""

from __future__ import annotations

from datetime import UTC
from typing import Any

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """
    Structured, stage-agnostic context for the AI Testing Agent.

    Field aliases mirror the requirement's camelCase names so callers may
    construct/serialize with either ``originalUserPrompt`` or
    ``original_user_prompt`` (``populate_by_name=True``).
    """

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }

    original_user_prompt: str | None = Field(
        None,
        alias="originalUserPrompt",
        description="Verbatim original user prompt (credentials already redacted by the parser)",
    )
    parsed_intent: dict[str, Any] = Field(
        default_factory=dict,
        alias="parsedIntent",
        description="Structured intent (ParsedPromptIntent.to_dict() shape, backward compatible)",
    )
    execution_goal: str | None = Field(
        None,
        alias="executionGoal",
        description="High-level goal statement distilled from the user prompt",
    )
    workflow_scope: dict[str, Any] = Field(
        default_factory=dict,
        alias="workflowScope",
        description="Scope summary: included/excluded modules and pages",
    )
    included_modules: list[str] = Field(
        default_factory=list,
        alias="includedModules",
        description="Modules the user explicitly asked to test",
    )
    excluded_modules: list[str] = Field(
        default_factory=list,
        alias="excludedModules",
        description="Modules the user explicitly asked to skip",
    )
    credentials: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "SECURITY: transient in-memory credentials "
            "(username/password/login_url/auth_strategy). Never log, emit, or persist."
        ),
    )
    priorities: list[str] = Field(
        default_factory=list,
        description="Testing priorities (e.g. critical-path first, security first)",
    )
    business_objective: str | None = Field(
        None,
        alias="businessObjective",
        description="Business objective the test run is meant to protect/verify",
    )
    inventory: dict[str, Any] = Field(
        default_factory=dict,
        description="Inventory summary and path produced by the inventory stage",
    )
    test_plan: dict[str, Any] = Field(
        default_factory=dict,
        alias="testPlan",
        description="AI-generated test plan summary and path",
    )
    approved_plan: dict[str, Any] = Field(
        default_factory=dict,
        alias="approvedPlan",
        description=(
            "Human-review outcome: approved plan path, review decision, reviewer, "
            "and preserved original prompt / parsed intent / execution plan"
        ),
    )
    generated_ir: dict[str, Any] = Field(
        default_factory=dict,
        alias="generatedIR",
        description="Intermediate Representation summary and path",
    )
    generated_tests: dict[str, Any] = Field(
        default_factory=dict,
        alias="generatedTests",
        description="Generated Playwright project summary and path",
    )
    execution_results: dict[str, Any] = Field(
        default_factory=dict,
        alias="executionResults",
        description="Execution outcomes: status, metrics, reports",
    )
    artifacts: dict[str, Any] = Field(
        default_factory=dict,
        description="Aggregated artifact paths from all stages",
    )

    # Phase 2: real-time stage tracking (merge, never overwrite)
    current_stage: str | None = Field(
        None,
        alias="currentStage",
        description="Currently active workflow stage name",
    )
    current_task: str | None = Field(
        None,
        alias="currentTask",
        description="What the current stage is doing",
    )
    completed_tasks: list[str] = Field(
        default_factory=list,
        alias="completedTasks",
        description="Stage names that have completed successfully",
    )
    progress: float = Field(
        default=0.0,
        description="Overall workflow progress 0.0–100.0",
    )
    failures: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-stage failure details [{stage, error, timestamp}]",
    )
    warnings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Per-stage warnings [{stage, message, timestamp}]",
    )
    execution_time: dict[str, float] = Field(
        default_factory=dict,
        alias="executionTime",
        description="Per-stage timing in seconds {stage: seconds}",
    )
    goal_achieved: bool | None = Field(
        None,
        alias="goalAchieved",
        description="Whether the execution goal was met (None until finalised)",
    )

    # Phase 2.5: goal satisfaction engine (replaces simple boolean)
    goal_progress: float = Field(
        default=0.0,
        alias="goalProgress",
        description="Goal completion percentage 0.0–100.0",
    )
    goal_completion: dict[str, Any] = Field(
        default_factory=dict,
        alias="goalCompletion",
        description="Detailed goal-by-goal completion {goal: {status, reason, tasks_done, tasks_total}}",
    )
    goal_status: str = Field(
        default="not_started",
        alias="goalStatus",
        description="not_started | in_progress | partially_complete | completed | blocked | failed",
    )

    # Phase 2.5: task-level tracking
    task_status: dict[str, str] = Field(
        default_factory=dict,
        alias="taskStatus",
        description="Per-task status {subtask_id: pending|running|completed|skipped|failed|blocked}",
    )
    planner_revision: int = Field(
        default=0,
        alias="plannerRevision",
        description="Number of times the ExecutionPlan was revised (dynamic replanning)",
    )
    clarification_required: bool = Field(
        default=False,
        alias="clarificationRequired",
        description="Whether the planner paused for user clarification",
    )
    selected_capability: str | None = Field(
        None,
        alias="selectedCapability",
        description="The tool/capability selected by the planner for the current task",
    )
    execution_history: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="executionHistory",
        description="History of executed actions [{stage, task, capability, status, timestamp}]",
    )

    # ------------------------------------------------------------------
    # Phase 2: stage tracking + merge
    # ------------------------------------------------------------------

    def merge(self, **updates: Any) -> None:
        """Update fields in-place, merging list/dict fields (never overwrite)."""
        for key, value in updates.items():
            if value is None:
                continue
            existing = getattr(self, key, None)
            if isinstance(existing, dict) and isinstance(value, dict):
                existing.update(value)
            elif isinstance(existing, list) and isinstance(value, list):
                existing.extend(v for v in value if v not in existing)
            else:
                setattr(self, key, value)

    def record_stage_entry(self, stage: str, task: str | None = None) -> None:
        """Record that a workflow stage has started."""
        self.current_stage = stage
        self.current_task = task or f"{stage.replace('_', ' ').title()} in progress..."

    def record_stage_done(self, stage: str, duration_seconds: float = 0.0) -> None:
        """Record that a workflow stage completed successfully."""
        if stage not in self.completed_tasks:
            self.completed_tasks.append(stage)
        self.execution_time[stage] = duration_seconds
        self.progress = min(round((len(self.completed_tasks) / 8) * 100, 1), 100.0)

    def record_stage_failure(self, stage: str, error: str) -> None:
        """Record a stage-level failure."""
        from datetime import datetime
        self.failures.append({"stage": stage, "error": error, "timestamp": datetime.now(UTC).isoformat()})

    def record_stage_warning(self, stage: str, message: str) -> None:
        """Record a non-fatal warning."""
        from datetime import datetime
        self.warnings.append({"stage": stage, "message": message, "timestamp": datetime.now(UTC).isoformat()})

    # ------------------------------------------------------------------
    # Phase 2.5: goal satisfaction + task tracking
    # ------------------------------------------------------------------

    def update_goal_satisfaction(
        self,
        *,
        goal: str,
        tasks_done: int = 0,
        tasks_total: int = 0,
        completed: bool = False,
        reason: str | None = None,
    ) -> None:
        """Incrementally update the goal satisfaction engine."""
        self.goal_completion[goal or "execution"] = {
            "tasks_done": tasks_done,
            "tasks_total": tasks_total,
            "completed": completed,
            "reason": reason,
        }
        if tasks_total > 0:
            self.goal_progress = round((tasks_done / tasks_total) * 100, 1)
        if completed:
            self.goal_status = "completed"
            self.goal_achieved = True
        elif tasks_done > 0:
            self.goal_status = "in_progress"
        else:
            self.goal_status = "not_started"

    def record_task_status(self, task_id: str, status: str) -> None:
        """Update status of a single subtask."""
        self.task_status[task_id] = status

    def record_executed_action(self, stage: str, task: str, capability: str, status: str) -> None:
        """Append an entry to the execution history."""
        from datetime import datetime
        self.execution_history.append({
            "stage": stage,
            "task": task,
            "capability": capability,
            "status": status,
            "timestamp": datetime.now(UTC).isoformat(),
        })
        if self.execution_history:  # keep last 100 entries
            self.execution_history = self.execution_history[-100:]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def redacted(self) -> AgentState:
        """Return a deep copy with sensitive values stripped (log/emit-safe)."""
        clone = self.model_copy(deep=True)
        clone.credentials = {}
        return clone

    def to_serializable(self, redact_credentials: bool = True) -> dict[str, Any]:
        """
        Serialise to a plain dict (camelCase keys) for transport/storage.

        Args:
            redact_credentials: When True (default), the credentials field is
                dropped so the result is safe to log, emit, or persist.
        """
        data = self.model_dump(by_alias=True)
        if redact_credentials:
            data["credentials"] = {}
        return data

    @classmethod
    def from_serializable(cls, data: dict[str, Any] | None) -> AgentState:
        """Rehydrate from :meth:`to_serializable` output (accepts camelCase)."""
        return cls(**(data or {}))


# Convenience: the canonical set of AgentState field names (camelCase) for
# documentation and cross-referencing the Phase 1 deliverable.
AGENT_STATE_FIELDS: list[str] = [
    "originalUserPrompt",
    "parsedIntent",
    "executionGoal",
    "workflowScope",
    "includedModules",
    "excludedModules",
    "credentials",
    "priorities",
    "businessObjective",
    "inventory",
    "testPlan",
    "approvedPlan",
    "generatedIR",
    "generatedTests",
    "executionResults",
    "artifacts",
    "currentStage",
    "currentTask",
    "completedTasks",
    "progress",
    "failures",
    "warnings",
    "executionTime",
    "goalAchieved",
    "goalProgress",
    "goalCompletion",
    "goalStatus",
    "taskStatus",
    "plannerRevision",
    "clarificationRequired",
    "selectedCapability",
    "executionHistory",
]

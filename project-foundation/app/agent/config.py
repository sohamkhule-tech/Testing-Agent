"""
Agent Feature Flags & Configuration

All new agentic behaviour is gated behind feature flags.
When all flags are False (default), the existing pipeline runs unchanged.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import BaseModel, Field


class AgentFeatureFlags(BaseModel):
    """Master feature-flag model for the AI Testing Agent.

    Every flag defaults to ``False`` so that no existing behaviour is
    altered unless explicitly enabled.
    """

    # ── Phase 0 ────────────────────────────────────────────────
    agent_mode_enabled: bool = Field(
        default=False,
        description="Master switch — enables all agentic behaviour",
    )
    artifact_registry_enabled: bool = Field(
        default=False,
        description="Use ArtifactRegistry instead of raw file paths",
    )

    # ── Phase 1 ────────────────────────────────────────────────
    intent_engine_enabled: bool = Field(
        default=False,
        description="Use LLM IntentEngine (else regex-only PromptParser)",
    )
    clarification_loop_enabled: bool = Field(
        default=False,
        description="Enable clarification questions for low-confidence intent",
    )
    execution_planner_enabled: bool = Field(
        default=False,
        description="Use ExecutionPlanner (else linear stage sequence)",
    )
    task_hierarchy_enabled: bool = Field(
        default=False,
        description="Decompose goals into Task→Subtask→Action hierarchy",
    )
    capability_registry_enabled: bool = Field(
        default=False,
        description="Enable CapabilityRegistry for tool discovery",
    )
    tool_selection_enabled: bool = Field(
        default=False,
        description="Dynamic tool selection per task (else hardcoded mapping)",
    )
    context_manager_enabled: bool = Field(
        default=False,
        description="Use ContextManager (else raw state access)",
    )
    confidence_gates_enabled: bool = Field(
        default=False,
        description="Threshold checks after every stage",
    )
    goal_satisfaction_enabled: bool = Field(
        default=False,
        description="Evidence-based goal satisfaction evaluation",
    )

    # ── Phase 2 ────────────────────────────────────────────────
    knowledge_model_enabled: bool = Field(
        default=False,
        description="Build KnowledgeModel from inventory (Phase 2)",
    )
    memory_manager_enabled: bool = Field(
        default=False,
        description="Use MemoryManager instead of ephemeral state (Phase 2)",
    )
    reflection_enabled: bool = Field(
        default=False,
        description="Reflection gates after major stages (Phase 2)",
    )
    recovery_engine_enabled: bool = Field(
        default=False,
        description="Advanced recovery strategies (Phase 2)",
    )

    # ── Phase 3 ────────────────────────────────────────────────
    parallel_execution_enabled: bool = Field(
        default=False,
        description="Parallel stage groups (Phase 3)",
    )
    learning_enabled: bool = Field(
        default=False,
        description="Cross-run learning (Phase 3)",
    )
    knowledge_reuse_enabled: bool = Field(
        default=False,
        description="Reuse knowledge across runs (Phase 3)",
    )
    cost_optimization_enabled: bool = Field(
        default=False,
        description="LLM cost management (Phase 3)",
    )

    @property
    def agent_active(self) -> bool:
        """True when any agentic feature is enabled."""
        return self.agent_mode_enabled

    @property
    def phase_1_active(self) -> bool:
        """True when Phase 1 features are active."""
        return self.agent_mode_enabled and (
            self.intent_engine_enabled
            or self.execution_planner_enabled
            or self.context_manager_enabled
        )


@lru_cache()
def get_agent_config() -> AgentFeatureFlags:
    """Return the process-wide agent configuration singleton.

    In production this would read from environment variables or a
    config store.  For now, all flags default to ``False``.
    """
    return AgentFeatureFlags()

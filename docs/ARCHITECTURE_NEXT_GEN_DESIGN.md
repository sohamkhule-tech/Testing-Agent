# NEXT-GENERATION ARCHITECTURE DESIGN

## Autonomous AI Testing Agent

**Document Type:** Technical Architecture Design  
**Version:** 1.1  
**Date:** 2026-08-06  
**Status:** Design Phase — No Code Written  
**Changelog:**
- v1.0: Initial architecture — Intent, Planner, State, Context, Knowledge, Memory, Reflection, Recovery, Artifacts
- v1.1: + Clarification Loop, Task Hierarchy, Capability Registry, Tool Selection Layer, Confidence Gates, Goal Satisfaction Engine

---

# 1. HIGH-LEVEL ARCHITECTURE

## 1.1 Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────┐
│                          USER                                        │
│              natural-language testing request                        │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     INTENT UNDERSTANDING                             │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  PromptParser (regex)           IntentEngine (LLM)              │ │
│  │  • credentials                  • goals                        │ │
│  │  • URLs                         • modules / scope              │ │
│  │  • browser                      • exclusions                   │ │
│  │  • environment                  • priorities                   │ │
│  │                                 • testing strategy             │ │
│  │                                 • business objective           │ │
│  │                                 • success criteria             │ │
│  │                                 • user constraints             │ │
│  └──────────────┬──────────────────────┬──────────────────────────┘ │
│                 │                      │                             │
│                 ▼                      ▼                             │
│     DeterministicIntent       SemanticIntent                         │
│                 │                      │                             │
│                 └──────────┬───────────┘                             │
│                            ▼                                         │
│                    UnifiedIntent (JSON)                              │
│                            │                                         │
│               ┌────────────┴────────────┐                            │
│               │  confidence >= 0.6?     │                            │
│               ├────────────┬────────────┤                            │
│               │  YES       │  NO        │                            │
│               │  ▸ proceed │  ▸ trigger │                            │
│               │            │    CLARIFY │  ◄── NEW                   │
│               └────────────┴────────────┘                            │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      EXECUTION PLANNER                               │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  Goal Decomposer   │  Task Hierarchy   │  Dependency Resolver   │ │
│  │  ───────────────── │  ──────────────── │  ────────────────────  │ │
│  │  Intent → Goals    │  Goals → Tasks    │  Tasks → DAG           │ │
│  │                    │       ↘ Subtasks  │                        │ │
│  │                    │         ↘ Actions │      ◄── NEW           │ │
│  └────────────────────┴──────────────────┴────────────────────────┘ │
│                            │                                         │
│           ┌────────────────┼────────────────┐                        │
│           ▼                ▼                ▼                        │
│    ExecutionPlan      Capability        Tool                         │
│    (DAG + Tasks)      Registry          Requirements                │
│                                              ◄── NEW                 │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     TOOL SELECTION LAYER       ◄── NEW                │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │  For each Task in ExecutionPlan:                                │ │
│  │  1. Query Capability Registry for matching tools                │ │
│  │  2. Score tools by: capability match, availability, cost,       │ │
│  │     historical success rate                                     │ │
│  │  3. Select best tool per task                                   │ │
│  │  4. Resolve tool dependencies (e.g., browser needs LLM)         │ │
│  │  5. Emit ToolSelectionEvent                                     │ │
│  └────────────────────────────────────────────────────────────────┘ │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        AGENT STATE                                    │
│                     (centralized shared state)                        │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ original_prompt   │ unified_intent   │ execution_plan          │  │
│  │ current_goal      │ completed_goals  │ pending_goals           │  │
│  │ context           │ artifacts        │ knowledge_model         │  │
│  │ inventory         │ test_plan        │ generated_code          │  │
│  │ execution_results │ failures         │ retry_history           │  │
│  │ progress          │ business_objectives │ module_scope         │  │
│  │ credentials(Auth) │ user_constraints │ reflection_log          │  │
│  │ stage_history     │ checkpoint       │ memory_refs             │  │
│  │ clarification_qs  │ tool_selections  │ satisfaction_status ←NEW│  │
│  │ ambiguity_flags   │ capability_reqs  │ confidence_gates  ←NEW  │  │
│  └───────────────────────────────────────────────────────────────┘  │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW ORCHESTRATOR                              │
│                 (extended LangGraph StateGraph)                       │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │                                                              │    │
│  │  Trigger → Crawler → Inventory → TestDesign → HumanReview   │    │
│  │                                              │               │    │
│  │                          ┌───────────────────┘               │    │
│  │                          ▼                                    │    │
│  │              CodeGeneration → Execution → Reporting          │    │
│  │                                                              │    │
│  │  ▲ CONFIDENCE GATES: threshold check after each stage ◄─NEW │    │
│  │  ▲ REFLECTION GATES: semantic evaluation after major stages  │    │
│  │  ▲ GOAL SATISFACTION: final evaluation after execution ◄─NEW│    │
│  │                                                              │    │
│  └─────────────────────────────────────────────────────────────┘    │
│                                                                       │
│  New Agentic Wrapper:                                                 │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  1. Read AgentState                                          │    │
│  │  2. Check current goal alignment                             │    │
│  │  3. Check confidence gates (pass/fail/warn)                  │    │
│  │  4. Query Tool Selection for appropriate agent               │    │
│  │  5. Execute stage with full context                          │    │
│  │  6. Write results back to AgentState                         │    │
│  │  7. Trigger Confidence Gate evaluation                       │    │
│  │  8. Trigger Reflection (major stages)                        │    │
│  │  9. Decide: continue / replan / retry / abort                │    │
│  │ 10. Trigger Goal Satisfaction (after all goals completed)    │    │
│  └─────────────────────────────────────────────────────────────┘    │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                      SUPPORTING LAYERS                                │
│                                                                       │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌─────────────────┐  │
│  │  CONTEXT  │  │  MEMORY   │  │ ARTIFACT  │  │    RECOVERY     │  │
│  │  MANAGER  │  │  MANAGER  │  │ REGISTRY  │  │    ENGINE       │  │
│  │           │  │           │  │           │  │                 │  │
│  │ guarantee │  │ short-term│  │ centralize│  │ retry           │  │
│  │ no stage  │  │ long-term │  │ all files │  │ resume          │  │
│  │ loses     │  │ run-level │  │ screensht │  │ rollback        │  │
│  │ context   │  │ historical│  │ traces    │  │ stage replay    │  │
│  │           │  │ learning  │  │ code      │  │ failure isolate │  │
│  └───────────┘  └───────────┘  └───────────┘  └─────────────────┘  │
│                                                                       │
│  ┌─────────────────────┐  ┌──────────────────────────────┐  ◄──NEW  │
│  │  CAPABILITY         │  │  GOAL SATISFACTION ENGINE    │          │
│  │  REGISTRY           │  │                              │          │
│  │  • all agents/tools │  │  • evidence-based evaluation │          │
│  │  • capabilities map │  │  • per-goal pass/fail/partial│          │
│  │  • cost metadata    │  │  • coverage vs objective     │          │
│  │  • SLA contracts    │  │  • drives replan decisions   │          │
│  └─────────────────────┘  └──────────────────────────────┘          │
└──────────────────────────────────────────────────────────────────────┘
```

## 1.2 Agent Interaction Diagram

```
         ┌────────────────────────────────────────────────────────────────┐
         │                    AGENT INTERACTIONS                            │
         └────────────────────────────────────────────────────────────────┘

    ┌──────────┐     ┌──────────────┐     ┌──────────────────┐
    │  Intent   │────▷│  Execution   │────▷│     Agent        │
    │  Engine   │     │   Planner    │     │     State         │
    │  (LLM)    │     │   (DAG)      │     │   (Pydantic)      │
    └─────┬─────┘     └──────┬───────┘     └────────┬─────────┘
          │                  │                       │
          ▼                  ▼                       │
   ┌──────────────┐  ┌──────────────┐               │
   │ Clarification │  │  Capability  │               │  ◄── NEW
   │    Loop       │  │  Registry    │               │
   │ (ambiguity)   │  │ (tools map)  │               │
   └──────┬────────┘  └──────┬───────┘               │
          │                  │                       │
          ▼                  ▼                       ▼
   ┌──────────────────────────────────────────────────────┐
   │                TOOL SELECTION LAYER                   │  ◄── NEW
   │  • matches tasks → capabilities                      │
   │  • scores tools by fit, cost, history                │
   │  • selects best agent/service per task               │
   └─────────────────────┬────────────────────────────────┘
                         │
         ┌───────────────┼──────────────────┐
         │               │                   │
         ▼               ▼                   ▼
  ┌───────────┐  ┌──────────────┐   ┌───────────────┐
  │  Context  │  │  Workflow    │   │   Memory      │
  │  Manager  │◄─│ Orchestrator │──▷│   Manager     │
  └───────────┘  └──────┬───────┘   └───────────────┘
                        │
   ┌────────────────────┼──────────────────────────────────┐
   │                    │                                   │
   ▼                    ▼                                   ▼
┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────────┐
│Confidence│    │  Reflection  │     │   Artifact   │     │    Recovery      │
│  Gates   │◄───│   Engine     │◄────│   Registry   │────▷│    Engine        │
│(threshold│    │  (semantic)  │     │ (centralized)│     │  (resilience)    │
│ checks)  │    └──────┬───────┘     └──────────────┘     └──────────────────┘
│ ◄── NEW  │           │
└─────────┘           │ (replan signal)
           ┌──────────┴──────────┐
           │                     │
           ▼                     ▼
    ┌──────────────┐    ┌──────────────────────┐
    │  Execution   │    │  GOAL SATISFACTION   │  ◄── NEW
    │   Planner    │    │       ENGINE         │
    │  (replan)    │    │  (evidence-based     │
    └──────────────┘    │   goal evaluation)   │
                        └──────────────────────┘                                               │

Data flow (→): Context/state propagation
Control flow (▷): Orchestration decisions
Feedback flow (◄─): Evaluation triggers
```

## 1.3 Information Flow Summary

```
USER INPUT
    │
    ├──► Intent Understanding
    │       ├──► RegexParser → deterministic fields (URLs, credentials, browser, env)
    │       └──► IntentEngine(LLM) → semantic fields (goals, strategy, business_objective,
    │                                   modules, exclusions, priorities, scope, success_criteria)
    │       └──► OUTPUT: UnifiedIntent (structured JSON)
    │
    ├──► AMBIGUITY CHECK ──────────────────────────────────── NEW ──┐
    │       │                                                        │
    │       ├──► confidence >= 0.6? → YES → proceed to Planner       │
    │       └──► confidence < 0.6?  → NO  → CLARIFICATION LOOP       │
    │              │                                                  │
    │              ├──► Detect ambiguous dimensions                   │
    │              ├──► Generate targeted clarification question(s)   │
    │              ├──► Present to user (blocking prompt / async)     │
    │              ├──► Merge user response into UnifiedIntent        │
    │              ├──► Re-evaluate confidence                        │
    │              └──► Repeat until confidence >= threshold OR       │
    │                    max clarifications reached → proceed anyway   │
    │                                                                │
    ├──► Execution Planner                                           │
    │       └──► Goal Decomposer → goals hierarchy                   │
    │       └──► Task Hierarchy Builder                              │
    │           ├──► Goal → Task(s)                   ◄── NEW       │
    │           ├──► Task → Subtask(s)                              │
    │           └──► Subtask → Action(s)                             │
    │       └──► Dependency Resolver → DAG                            │
    │       └──► Constraint Validator → validated plan                │
    │       └──► Success Criteria Mapper → measurable outcomes        │
    │       └──► OUTPUT: ExecutionPlan (DAG with task hierarchy)      │
    │                                                                │
    ├──► CAPABILITY REGISTRY LOOKUP  ──────────────────── NEW ──┐   │
    │       │                                                     │   │
    │       ├──► For each Task in ExecutionPlan:                  │   │
    │       ├──► Query registry: what tools can perform this?     │   │
    │       └──► Filter by: availability, constraints, cost       │   │
    │                                                             │   │
    ├──► TOOL SELECTION  ───────────────────────────────── NEW ──┤   │
    │       │                                                     │   │
    │       ├──► Score candidate tools per task                   │   │
    │       ├──► Select best tool (highest score)                 │   │
    │       ├──► Resolve tool dependencies                        │   │
    │       └──► OUTPUT: Task → Tool mapping                      │   │
    │                                                             │   │
    ├──► AgentState Initialization                                │   │
    │       └──► Populates: original_prompt, unified_intent,      │   │
    │               execution_plan, current_goal, pending_goals,  │   │
    │               business_objectives, module_scope,            │   │
    │               user_constraints, credentials,                │   │
    │               tool_selections, capability_requirements,     │   │
    │               clarification_history (if any)                │   │
    │                                                             │   │
    ├──► Workflow Orchestrator (reads AgentState before each stage)│  │
    │       │                                                     │   │
    │       ├──► Stage: trigger                                   │   │
    │       │       └──► writes: workspace_path, run_metadata      │   │
    │       │                                                     │   │
    │       ├──► [CONFIDENCE GATE]  ◄── NEW                       │   │
    │       │       └──► trigger output meets quality threshold?  │   │
    │       │       └──► PASS → continue | WARN → continue+flag   │   │
    │       │                       | FAIL → retry/abort          │   │
    │       │                                                     │   │
    │       ├──► Stage: crawler                                   │   │
    │       │       └──► reads: unified_intent.scope, credentials │   │
    │       │       └──► writes: crawl_package → ArtifactRegistry │   │
    │       │                                                     │   │
    │       ├──► [CONFIDENCE GATE + REFLECTION GATE]              │   │
    │       │       └──► gate: pages discovered meet threshold?   │   │
    │       │       └──► reflection: scope coverage adequate?     │   │
    │       │                                                     │   │
    │       ├──► Stage: inventory                                 │   │
    │       │       └──► writes: inventory, knowledge_model       │   │
    │       │                                                     │   │
    │       ├──► Stage: test_design                               │   │
    │       │       └──► reads: inventory, knowledge_model, goals │   │
    │       │       └──► writes: test_plan                        │   │
    │       │                                                     │   │
    │       ├──► [CONFIDENCE GATE + REFLECTION GATE]              │   │
    │       │       └──► gate: scenario count meets minimum?      │   │
    │       │       └──► reflection: business objective covered?  │   │
    │       │                                                     │   │
    │       ├──► Stage: human_review                              │   │
    │       │       └──► writes: approved_test_plan               │   │
    │       │                                                     │   │
    │       ├──► Stage: code_generation                           │   │
    │       │       └──► writes: generated_code                   │   │
    │       │                                                     │   │
    │       ├──► [CONFIDENCE GATE + REFLECTION GATE]              │   │
    │       │       └──► gate: validation passed?                 │   │
    │       │       └──► reflection: all scenarios implemented?   │   │
    │       │                                                     │   │
    │       ├──► Stage: execution                                 │   │
    │       │       └──► writes: execution_results, failures      │   │
    │       │                                                     │   │
    │       ├──► Stage: reporting                                 │   │
    │       │       └──► writes: reports → ArtifactRegistry       │   │
    │       │                                                     │   │
    │       ├──► [CONFIDENCE GATE + REFLECTION GATE]              │   │
    │       │       └──► gate: report completeness check          │   │
    │       │       └──► reflection: success criteria met?        │   │
    │       │                                                     │   │
    │       └──► GOAL SATISFACTION ENGINE ──────────── NEW ──┐   │   │
    │               │                                         │   │   │
    │               ├──► For each Goal in ExecutionPlan:      │   │   │
    │               │   ├──► Load execution evidence          │   │   │
    │               │   ├──► Compare pass rate vs threshold   │   │   │
    │               │   ├──► Check critical paths covered     │   │   │
    │               │   ├──► Verify coverage meets spec       │   │   │
    │               │   └──► Decision: SATISFIED / PARTIAL /  │   │   │
    │               │                UNSATISFIED              │   │   │
    │               │                                         │   │   │
    │               ├──► SATISFIED → mark goal complete       │   │   │
    │               │               advance to next goal      │   │   │
    │               │                                         │   │   │
    │               ├──► PARTIAL   → report partial success   │   │   │
    │               │               suggest gap closure       │   │   │
    │               │               optionally replan         │   │   │
    │               │                                         │   │   │
    │               └──► UNSATISFIED → trigger replan         │   │   │
    │                       OR escalate to user               │   │   │
    │                                                        │   │   │
    └──► Memory Layer (throughout)                            │   │   │
            ├──► Short-term: current run context              │   │   │
            ├──► Long-term: knowledge_model, patterns         │   │   │
            ├──► Run memory: checkpoints, contracts           │   │   │
            ├──► Historical: trends, cross-run metrics        │   │   │
            └──► Learning: clarification outcomes,            │   │   │
                          satisfaction feedback,              │   │   │
                          tool selection outcomes ◄── NEW     │   │   │
```

---

# 2. AGENT STATE

## 2.1 Design Philosophy

Every stage MUST read from and write to a single `AgentState` instance. No stage reconstructs context from scratch. No stage reads only its own stage-specific data. Every stage has access to the full picture.

## 2.2 AgentState Schema

```python
# Location: app/agent/state.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, Optional
from uuid import UUID
from enum import Enum


class GoalStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class SatisfactionResult(str, Enum):                  # ─── NEW ───
    """Outcome of goal satisfaction evaluation."""
    SATISFIED = "satisfied"       # All evidence confirms goal met
    PARTIALLY = "partially"       # Most evidence, gaps identified
    UNSATISFIED = "unsatisfied"   # Insufficient evidence or failures
    INCONCLUSIVE = "inconclusive" # Not enough data to determine


class Stage(str):
    """Valid workflow stages (extended)."""
    INTENT_UNDERSTANDING = "intent_understanding"
    CLARIFICATION = "clarification"                   # ─── NEW ───
    PLANNING = "planning"
    TOOL_SELECTION = "tool_selection"                 # ─── NEW ───
    TRIGGER = "trigger"
    CRAWLER = "crawler"
    INVENTORY = "inventory"
    TEST_DESIGN = "test_design"
    HUMAN_REVIEW = "human_review"
    CODE_GENERATION = "code_generation"
    EXECUTION = "execution"
    REPORTING = "reporting"
    REFLECTION = "reflection"
    GOAL_SATISFACTION = "goal_satisfaction"           # ─── NEW ───


class StageResult(BaseModel):
    """Output of a single workflow stage."""
    stage: Stage
    status: str  # completed | failed | skipped | retrying
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: float = 0.0
    data: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    retry_attempt: int = 0
    artifacts_created: list[str] = Field(default_factory=list)


class Goal(BaseModel):
    """A business-level testing objective."""
    id: str
    description: str
    status: GoalStatus = GoalStatus.PENDING
    priority: str = "medium"           # critical | high | medium | low
    module_scope: list[str] = Field(default_factory=list)
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    tasks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    parent_goal_id: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


class UnifiedIntent(BaseModel):
    """Combined deterministic + semantic intent."""
    # Deterministic (regex-extracted)
    credentials_provided: bool = False
    target_urls: list[str] = Field(default_factory=list)
    browser: str = "chromium"
    environment: str = "staging"

    # Semantic (LLM-extracted)
    business_objective: str = ""
    goals: list[str] = Field(default_factory=list)
    modules_to_test: list[str] = Field(default_factory=list)
    modules_to_exclude: list[str] = Field(default_factory=list)
    pages_to_include: list[str] = Field(default_factory=list)
    pages_to_exclude: list[str] = Field(default_factory=list)
    testing_strategy: str = ""          # smoke | regression | full | exploratory
    priorities: dict[str, str] = Field(default_factory=dict)
    coverage_preferences: list[str] = Field(default_factory=list)
    output_preferences: list[str] = Field(default_factory=list)
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    scope_constraint: str = ""          # "only", "exclude", "full"
    custom_instructions: str = ""
    confidence: float = 0.0             # 0.0–1.0: semantic parsing confidence

    class Config:
        frozen = False


class ExecutionPlan(BaseModel):
    """Task DAG generated by the Execution Planner."""
    id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    version: int = 1
    goals: list[Goal] = Field(default_factory=list)
    stage_sequence: list[Stage] = Field(default_factory=list)
    dependencies: dict[str, list[str]] = Field(default_factory=dict)  # stage → [depends_on]
    parallel_groups: list[list[Stage]] = Field(default_factory=list)
    conditional_stages: dict[Stage, str] = Field(default_factory=dict)  # stage → condition
    constraints: dict[str, Any] = Field(default_factory=dict)
    estimated_runtime_minutes: float = 0.0
    checkpoint_strategy: str = "after_each_stage"
    success_criteria: dict[str, Any] = Field(default_factory=dict)
    failure_policy: str = "stop"        # stop | continue | retry
    max_retries: int = 3
    dynamic_replanning: bool = True


class KnowledgeModel(BaseModel):
    """Structured knowledge about the application under test."""
    pages: list[dict[str, Any]] = Field(default_factory=list)
    forms: list[dict[str, Any]] = Field(default_factory=list)
    flows: list[dict[str, Any]] = Field(default_factory=list)       # user journeys
    apis: list[dict[str, Any]] = Field(default_factory=list)
    components: list[dict[str, Any]] = Field(default_factory=list)   # UI components
    navigation_graph: dict[str, Any] = Field(default_factory=dict)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    domain_concepts: list[str] = Field(default_factory=list)


class ContextFrame(BaseModel):
    """Immutable snapshot of context at a point in time."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    stage: Stage
    intent_snapshot: Optional[UnifiedIntent] = None
    goal_snapshot: Optional[Goal] = None
    decision: str = ""                  # what the stage decided to do
    reasoning: str = ""                 # why
    data_summary: dict[str, Any] = Field(default_factory=dict)


class ReflectionRecord(BaseModel):
    """Output of a reflection gate."""
    stage: Stage
    passed: bool
    evaluation: str
    issues_found: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    replan_triggered: bool = False
    new_plan_version: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MemoryRef(BaseModel):
    """Reference to a memory entry (non-blocking, pointer-only)."""
    memory_id: str
    memory_type: str                    # short_term | long_term | run | historical | learning
    description: str
    relevance_score: float = 1.0


# ──────────────────────────────────────────────────────────────
# v1.1 NEW MODEL CLASSES
# ──────────────────────────────────────────────────────────────

class ClarificationQuestion(BaseModel):                          # ─── NEW: Part 3B
    """A targeted question asked to resolve ambiguous intent."""
    id: str
    dimension: str                      # scope | priority | strategy | coverage | module
    question: str                       # Human-readable question
    context: str                        # Why this is ambiguous
    options: list[str] = Field(
        default_factory=list,
        description="Suggested answers for multi-choice resolution"
    )
    default_answer: Optional[str] = None  # If user doesn't respond
    asked_at: datetime = Field(default_factory=datetime.utcnow)


class ClarificationExchange(BaseModel):                          # ─── NEW: Part 3B
    """A complete clarification Q&A round."""
    run_id: UUID
    round_number: int
    question: ClarificationQuestion
    user_response: Optional[str] = None
    resolved_intent_fields: list[str] = Field(default_factory=list)
    confidence_before: float
    confidence_after: Optional[float] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ToolSelection(BaseModel):                                  # ─── NEW: Part 4D
    """Mapping of a task to the tool/agent selected for it."""
    task_id: str
    stage: Stage
    selected_tool_id: str               # Reference to CapabilityRegistry entry
    selected_tool_name: str             # e.g., "CrawlerAgent", "TestDesignAgent", "LLMClient"
    score: float                        # Composite selection score (0–1)
    fallback_tool_ids: list[str] = Field(default_factory=list)
    selection_reason: str               # Why this tool was chosen
    cost_estimate: Optional[float] = None  # Estimated LLM cost or compute cost
    constraints_matched: list[str] = Field(default_factory=list)


class CapabilityRef(BaseModel):                                 # ─── NEW: Part 4C
    """Lightweight capability reference stored in AgentState."""
    capability_id: str
    name: str
    type: str                           # agent | service | llm_client | browser | generator
    required_for_stages: list[Stage] = Field(default_factory=list)
    is_critical: bool = False           # Pipeline cannot proceed without this
    status: str = "available"           # available | degraded | unavailable


class ConfidenceGateConfig(BaseModel):                          # ─── NEW: Part 8B
    """Configuration for a single confidence gate."""
    stage: Stage
    metric: str                         # e.g., "page_count", "scenario_count", "pass_rate"
    threshold: float                    # e.g., min 5 pages, min 90% pass rate
    comparator: str = ">="              # >= | <= | == | >
    gate_type: str = "hard"             # hard (fail blocks) | soft (fail warns only)
    auto_retry: bool = False
    max_retries: int = 1
    failure_action: str = "retry"       # retry | warn | skip | abort


class ConfidenceGateResult(BaseModel):                          # ─── NEW: Part 8B
    """Result of a single confidence gate evaluation."""
    gate_id: str
    stage: Stage
    metric: str
    expected: float
    actual: float
    passed: bool
    severity: str = "info"              # info | warn | error
    message: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SatisfactionEvidence(BaseModel):                          # ─── NEW: Part 8C
    """Evidence collected to evaluate goal satisfaction."""
    goal_id: str
    evidence_type: str                  # pass_rate | coverage | assertion | user_feedback
    value: Any
    threshold: Optional[float] = None
    meets_threshold: Optional[bool] = None
    source: str                         # e.g., "execution_results", "reflection", "human_review"
    collected_at: datetime = Field(default_factory=datetime.utcnow)


class GoalSatisfactionResult(BaseModel):                        # ─── NEW: Part 8C
    """Final evaluation of whether a goal was satisfied."""
    goal_id: str
    result: SatisfactionResult
    evidence: list[SatisfactionEvidence] = Field(default_factory=list)
    evidence_summary: str = ""
    confidence: float = 0.0             # How confident are we in this verdict?
    gap_analysis: list[str] = Field(default_factory=list)  # What's missing?
    recommendations: list[str] = Field(default_factory=list)  # What to do about gaps?
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)


class AgentState(BaseModel):
    """
    Centralized state for the AI Testing Agent.

    Every stage reads from and writes to this single state object.
    No stage ever rebuilds context from partial data.
    """
    # ── Identity ──────────────────────────────────────────────
    run_id: UUID
    run_status: str = "initializing"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    workspace_path: Optional[str] = None

    # ── User Input ────────────────────────────────────────────
    original_prompt: str = ""
    request_data: dict[str, Any] = Field(default_factory=dict)
    requested_by: Optional[str] = None

    # ── Intent ────────────────────────────────────────────────
    unified_intent: Optional[UnifiedIntent] = None
    parsed_intent_legacy: dict[str, Any] = Field(default_factory=dict)  # backward compat
    auth_context: Optional[dict[str, Any]] = None  # NEVER emitted in events

    # ── Execution Plan ────────────────────────────────────────
    execution_plan: Optional[ExecutionPlan] = None
    plan_version: int = 1

    # ── Goals ─────────────────────────────────────────────────
    current_goal_id: Optional[str] = None
    completed_goals: list[Goal] = Field(default_factory=list)
    pending_goals: list[Goal] = Field(default_factory=list)
    failed_goals: list[Goal] = Field(default_factory=list)

    # ── Stage Tracking ────────────────────────────────────────
    completed_stages: list[str] = Field(default_factory=list)
    stage_results: dict[str, StageResult] = Field(default_factory=dict)
    stage_history: list[ContextFrame] = Field(default_factory=list)

    # ── Artifacts ─────────────────────────────────────────────
    # (references to ArtifactRegistry, not raw file paths)
    crawl_package_ref: Optional[str] = None
    inventory_ref: Optional[str] = None
    knowledge_model_ref: Optional[str] = None
    test_plan_ref: Optional[str] = None
    approved_test_plan_ref: Optional[str] = None
    generated_code_ref: Optional[str] = None
    execution_results_ref: Optional[str] = None
    execution_reports_ref: Optional[str] = None

    # ── Knowledge ─────────────────────────────────────────────
    knowledge_model: Optional[KnowledgeModel] = None

    # ── Execution Results ─────────────────────────────────────
    execution_summary: dict[str, Any] = Field(default_factory=dict)
    test_results: list[dict[str, Any]] = Field(default_factory=list)
    pass_rate: float = 0.0
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_flaky: int = 0

    # ── Failures & Recovery ───────────────────────────────────
    failures: list[dict[str, Any]] = Field(default_factory=list)
    retry_history: list[dict[str, Any]] = Field(default_factory=list)
    recovery_actions: list[dict[str, Any]] = Field(default_factory=list)

    # ── Reflection ────────────────────────────────────────────
    reflection_log: list[ReflectionRecord] = Field(default_factory=list)
    replan_count: int = 0

    # ── Memory ────────────────────────────────────────────────
    memory_refs: list[MemoryRef] = Field(default_factory=list)

    # ── Progress ──────────────────────────────────────────────
    progress_percent: float = 0.0
    estimated_remaining_minutes: float = 0.0

    # ── Errors ────────────────────────────────────────────────
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # ── Clarification (v1.1) ──────────────────────────────────  ◄── NEW
    ambiguity_flags: dict[str, float] = Field(
        default_factory=dict,
        description="Dimension → ambiguity score (0–1). E.g., {'scope': 0.8, 'priority': 0.3}"
    )
    clarification_history: list[ClarificationExchange] = Field(default_factory=list)
    clarification_rounds: int = 0
    max_clarification_rounds: int = 3

    # ── Tool Selection (v1.1) ──────────────────────────────────  ◄── NEW
    tool_selections: dict[str, ToolSelection] = Field(
        default_factory=dict,
        description="task_id → ToolSelection mapping"
    )
    capability_requirements: list[CapabilityRef] = Field(
        default_factory=list,
        description="Capabilities needed for this execution plan"
    )

    # ── Confidence Gates (v1.1) ────────────────────────────────  ◄── NEW
    confidence_gate_configs: list[ConfidenceGateConfig] = Field(default_factory=list)
    confidence_gate_results: list[ConfidenceGateResult] = Field(default_factory=list)
    gate_failure_count: int = 0
    max_gate_failures: int = 3

    # ── Goal Satisfaction (v1.1) ───────────────────────────────  ◄── NEW
    satisfaction_results: dict[str, GoalSatisfactionResult] = Field(
        default_factory=dict,
        description="goal_id → satisfaction evaluation"
    )
    overall_satisfaction: Optional[SatisfactionResult] = None
    satisfaction_evaluated_at: Optional[datetime] = None

    # ── Metadata (DI-injected agents, config) ─────────────────
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"frozen": False, "validate_assignment": True, "arbitrary_types_allowed": True}

    # ──────────────────────────────────────────────────────────
    # Helper methods
    # ──────────────────────────────────────────────────────────

    def get_stage_context(self, stage: Stage) -> dict[str, Any]:
        """Build the full context dictionary for a stage to consume."""
        return {
            "run_id": str(self.run_id),
            "original_prompt": self.original_prompt,
            "unified_intent": self.unified_intent.model_dump() if self.unified_intent else None,
            "execution_plan": self.execution_plan.model_dump() if self.execution_plan else None,
            "current_goal": next((g for g in self.pending_goals if g.id == self.current_goal_id), None),
            "auth_context": self.auth_context,
            "workspace_path": self.workspace_path,
            "knowledge_model": self.knowledge_model.model_dump() if self.knowledge_model else None,
            "completed_stages": self.completed_stages,
            "stage_results": {k: v.model_dump() for k, v in self.stage_results.items()},
            "reflection_log": [r.model_dump() for r in self.reflection_log],
            # v1.1 additions
            "tool_selections": {k: v.model_dump() for k, v in self.tool_selections.items()},
            "confidence_gate_configs": [g.model_dump() for g in self.confidence_gate_configs],
            "satisfaction_results": {k: v.model_dump() for k, v in self.satisfaction_results.items()},
            "ambiguity_flags": self.ambiguity_flags,
        }

    def record_stage(self, result: StageResult) -> None:
        """Record a completed stage and update tracking."""
        self.stage_results[result.stage.value] = result
        if result.status == "completed":
            if result.stage.value not in self.completed_stages:
                self.completed_stages.append(result.stage.value)
        self.stage_history.append(ContextFrame(
            stage=result.stage,
            decision=result.status,
            data_summary={"duration_ms": result.duration_ms, "error": result.error},
        ))
        self.updated_at = datetime.utcnow()

    def advance_goal(self) -> Optional[Goal]:
        """Move to the next pending goal."""
        for goal in self.pending_goals:
            if goal.status == GoalStatus.PENDING:
                goal.status = GoalStatus.IN_PROGRESS
                self.current_goal_id = goal.id
                return goal
        return None

    def complete_current_goal(self) -> None:
        """Mark current goal as completed and advance."""
        for goal in self.pending_goals:
            if goal.id == self.current_goal_id:
                goal.status = GoalStatus.COMPLETED
                goal.completed_at = datetime.utcnow()
                self.completed_goals.append(goal)
                self.pending_goals.remove(goal)
                break
        self.current_goal_id = None
        self.advance_goal()

    def fail_current_goal(self, reason: str) -> None:
        """Mark current goal as failed."""
        for goal in self.pending_goals:
            if goal.id == self.current_goal_id:
                goal.status = GoalStatus.FAILED
                self.failed_goals.append(goal)
                self.pending_goals.remove(goal)
                self.failures.append({
                    "goal_id": goal.id,
                    "reason": reason,
                    "timestamp": datetime.utcnow().isoformat(),
                })
                break
        self.current_goal_id = None

    def update_progress(self) -> None:
        """Recalculate progress based on completed vs total stages."""
        total_stages = len(self.execution_plan.stage_sequence) if self.execution_plan else 7
        completed = len(self.completed_stages)
        self.progress_percent = round((completed / max(total_stages, 1)) * 100, 1)
```

## 2.3 State Propagation Contract

Every workflow stage node MUST:

1. **Accept** `AgentState` as its sole input parameter
2. **Read** all relevant fields from `AgentState` — never reconstruct intent/context
3. **Execute** its logic
4. **Write** results back to the appropriate `AgentState` fields
5. **Call** `state.record_stage(StageResult(...))` before returning
6. **Return** the mutated `AgentState`

This contract is enforced by a new `IAgenticStage` interface:

```python
class IAgenticStage(ABC):
    @abstractmethod
    async def execute(self, state: AgentState) -> AgentState:
        """
        Execute this stage with full agent state.

        Guarantees:
        - state is read (not copied) before execution
        - results are written to state
        - StageResult is recorded
        - state is returned
        """
        pass
```

## 2.4 Backward Compatibility

The existing `PlatformWorkflowState` is retained but maps to `AgentState` via an adapter:

```python
class LegacyStateAdapter:
    """Maps old PlatformWorkflowState ↔ new AgentState."""

    @staticmethod
    def to_agent_state(legacy: PlatformWorkflowState) -> AgentState:
        ...

    @staticmethod
    def from_agent_state(agent_state: AgentState) -> PlatformWorkflowState:
        ...
```

All existing nodes continue to work unmodified during Phase 1 migration.

---

# 3. INTENT UNDERSTANDING

## 3.1 Current Architecture (Problem)

```
Raw Prompt → PromptParser (regex only) → ParsedPromptIntent
```

Limitations:
- No semantic understanding of user goals
- No business objective extraction
- No module relationship understanding
- No success criteria inference
- Extracts only keyword-level patterns
- Cannot distinguish "test login thoroughly" from "just check login page exists"

## 3.2 Target Architecture (Hybrid)

```
Raw Prompt
    │
    ├──► RegexParser (DeterministicPipeline) ──► DeterministicIntent
    │    • credentials (username, password, login_url)
    │    • target URLs (base_url, specific pages)
    │    • browser preference (chromium, firefox, webkit)
    │    • environment (staging, production, dev)
    │    • auth_strategy (form, api, basic, oauth)
    │    • explicit URL patterns (/*.admin, /dashboard/*)
    │    RETAINED from current PromptParser — proven, fast, reliable
    │
    └──► IntentEngine (LLM) ──► SemanticIntent
         • business_objective: "Validate order checkout flow for PCI compliance"
         • goals: ["Verify payment processing", "Test session timeout", ...]
         • modules_to_test: ["Checkout", "Payment Gateway", "Order Confirmation"]
         • modules_to_exclude: ["Admin Panel", "Wishlist"]
         • testing_strategy: "regression"
         • priorities: {"Checkout": "critical", "Search": "medium"}
         • scope_constraint: "only" | "exclude" | "full"
         • success_criteria: {"min_pass_rate": 95, "critical_paths_tested": 10}
         • custom_instructions: "..."
         • confidence: 0.92
         NEW — adds semantic understanding without removing regex reliability
```

## 3.3 IntentEngine Implementation Design

```
Location: app/agent/intent/intent_engine.py
```

### LLM Prompt Structure

```markdown
SYSTEM:
You are an intent understanding engine for an AI testing platform.
Extract structured testing intent from user prompts.

OUTPUT SCHEMA (JSON):
{
  "business_objective": "string",
  "goals": ["string"],
  "modules_to_test": ["string"],
  "modules_to_exclude": ["string"],
  "pages_to_include": ["string"],
  "pages_to_exclude": ["string"],
  "testing_strategy": "smoke|regression|full|exploratory",
  "priorities": {"module_name": "critical|high|medium|low"},
  "coverage_preferences": ["functional|negative|boundary|security|api|accessibility|performance"],
  "output_preferences": ["typescript|playwright|pom|...],
  "success_criteria": {"key": "value"},
  "scope_constraint": "only|exclude|full",
  "custom_instructions": "string",
  "confidence": 0.0-1.0
}

RULES:
- If scope is "only", ALL other modules are excluded.
- If user says "verify", "validate", "ensure" → business_objective is compliance/testing.
- If user says "test just", "only test" → scope_constraint = "only".
- Infer success_criteria from business_objective context.
- Low confidence (<0.5) → flag for user confirmation.

USER PROMPT:
{redacted_user_prompt}
```

### Fallback Strategy

If LLM call fails (timeout, error, no API key):
1. Use regex-only `ParsedPromptIntent` (existing, proven)
2. Map regex fields to `UnifiedIntent` schema
3. Set `confidence: 0.0`
4. Log warning: "Semantic intent extraction skipped — using deterministic parser"
5. Continue pipeline with reduced semantic richness

### Merge Strategy

```
Merge(DeterministicIntent, SemanticIntent) → UnifiedIntent

Rules:
- credentials: always from regex (never from LLM — security)
- URLs: regex takes precedence (more precise)
- browser: regex takes precedence
- environment: regex takes precedence
- all semantic fields: from LLM (or default empty if LLM unavailable)
- conflicts: flag in warnings, prefer regex for factual fields
```

## 3.4 Intent Validation

Before passing `UnifiedIntent` to the Execution Planner:

1. Validate `modules_to_test` ∩ `modules_to_exclude` = ∅
2. Validate at least one module in `modules_to_test`
3. Validate `scope_constraint` is valid enum value
4. Validate `confidence > 0.0 || WARN`
5. Validate URLs are reachable format
6. Emit `INTENT_VALIDATED` event with confidence score

---

# 3B. CLARIFICATION LOOP

## 3B.1 Design

```
Location: app/agent/intent/clarification_loop.py
```

### Problem

When IntentEngine confidence is below threshold, proceeding with ambiguous intent leads to:
- Wrong modules tested (or missed)
- Incorrect testing strategy
- User expectations not met
- Wasted compute on misaligned tests

### Solution

A clarification loop that pauses the pipeline and asks the user targeted questions before committing to an execution plan.

### Flow

```
UnifiedIntent generated
        │
        ▼
┌───────────────────┐
│ Ambiguity Detector│
│                   │
│ For each dimension│
│ (scope, strategy, │
│  priority,        │
│  coverage,        │
│  success_criteria)│
│ check confidence  │
└────────┬──────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
 ALL >= 0.6   ANY < 0.6
    │         │
    │         ▼
    │   ┌─────────────────────────┐
    │   │ Question Generator (LLM)│
    │   │                         │
    │   │ Generates 1 targeted    │
    │   │ question per ambiguous  │
    │   │ dimension.              │
    │   │                         │
    │   │ Rules:                   │
    │   │ • Max 1 question/round │
    │   │ • Multi-choice preferred│
    │   │ • Avoid jargon          │
    │   │ • Show impact of choice │
    │   └───────────┬─────────────┘
    │               │
    │               ▼
    │   ┌─────────────────────────┐
    │   │ Present to User          │
    │   │                         │
    │   │ Strategy A: synchronous │
    │   │ (blocking, for CLI/API  │
    │   │  with immediate resp.)  │
    │   │                         │
    │   │ Strategy B: asynchronous│
    │   │ (persist question,      │
    │   │  notify user, wait for  │
    │   │  resume with answer)    │
    │   └───────────┬─────────────┘
    │               │
    │               ▼
    │   ┌─────────────────────────┐
    │   │ Merge Response          │
    │   │                         │
    │   │ • Update UnifiedIntent  │
    │   │   with answer           │
    │   │ • Reset confidence for  │
    │   │   resolved dimension    │
    │   │ • Re-evaluate overall   │
    │   │   confidence            │
    │   └───────────┬─────────────┘
    │               │
    │               ▼
    │        ┌──────────────┐
    │        │ Confidence   │
    │        │ >= 0.6 now?  │
    │        └──┬───────────┘
    │      ┌────┴────┐
    │      │NO       │YES
    │      ▼         │
    │   ┌─────────┐  │
    │   │Rounds < │  │
    │   │max (3)? │  │
    │   └─┬────┬──┘  │
    │   YES  NO      │
    │   │    │       │
    │   │    ▼       │
    │   │  PROCEED   │
    │   │  with      │
    │   │  warning   │
    │   │            │
    │   └────────────┼───► Execution Planner
    │                │
    └────────────────┘
```

### Ambiguity Dimensions

| Dimension | What it means | Example ambiguity | Confidence indicators |
|-----------|--------------|------------------|-----------------------|
| `scope` | Which modules/pages to test | "test the app" — which parts? | Low modules_to_test count, high confidence drop |
| `strategy` | Smoke vs regression vs full | "run some tests" — how many? | No testing_strategy inferred, ambiguous keywords |
| `priority` | Which features matter most | "check the important stuff" — which? | All medium priority, no critical flagged |
| `coverage` | What test types to generate | "test it" — functional? security? | Empty coverage_preferences |
| `success_criteria` | What constitutes success | "make sure it works" — how measured? | Empty success_criteria dict |
| `module_relationship` | How modules depend on each other | "test login and checkout" — separately? together? | Multiple modules, no dependency context |

### Question Generator

```python
class ClarificationQuestionGenerator:
    """
    Generates targeted clarification questions for ambiguous dimensions.

    Uses LLM (lightweight model, low token count) to generate one
    high-impact question per ambiguous dimension.
    """

    async def generate_questions(
        self,
        unified_intent: UnifiedIntent,
        ambiguity_flags: dict[str, float],   # dimension → score 0–1
        max_questions: int = 1,
    ) -> list[ClarificationQuestion]:
        """
        Generate clarification questions.

        Strategy:
        1. Sort dimensions by ambiguity score (descending)
        2. Pick highest-impact dimension
        3. Generate 1 multi-choice question targeting that dimension
        4. Include default answer if user times out
        """

    async def merge_response(
        self,
        unified_intent: UnifiedIntent,
        question: ClarificationQuestion,
        user_response: str,
    ) -> UnifiedIntent:
        """
        Update UnifiedIntent with user's clarification.

        Uses LLM to intelligently merge the response back into
        the structured intent fields. Not a simple field set —
        a response like "I want thorough security testing on
        the payment flow" should update testing_strategy,
        coverage_preferences, and priorities simultaneously.
        """
```

### Clarification Loop Interface

```python
class ClarificationLoop:
    """
    Orchestrates the clarification process.

    Integrates with:
    - Intent Engine (to detect ambiguity)
    - Question Generator (to create questions)
    - AgentState (to persist clarification history)
    - API layer (to present questions to user synchronously or async)
    """

    async def evaluate_ambiguity(
        self, unified_intent: UnifiedIntent
    ) -> dict[str, float]:
        """Compute ambiguity scores per dimension."""

    async def run_clarification(
        self,
        state: AgentState,
        strategy: str = "synchronous",  # synchronous | asynchronous
    ) -> AgentState:
        """
        Run the clarification loop.

        Returns:
            Updated AgentState with:
            - clarification_history populated
            - unified_intent updated
            - ambiguity_flags recomputed
        """

    async def should_clarify(self, unified_intent: UnifiedIntent) -> bool:
        """Returns True if any dimension is below confidence threshold."""

    async def get_pending_question(
        self, run_id: UUID
    ) -> Optional[ClarificationQuestion]:
        """Retrieve pending question for async clarification."""
```

### User Experience

**Synchronous (CLI/API with immediate interaction):**

```
User: Test my e-commerce app
Agent: I'll set up testing. I need one clarification first:

       The app scope is unclear. Should I:
       A) Test only the customer-facing storefront (products, cart, checkout)
       B) Test only the admin panel (inventory, orders, analytics)
       C) Test both the storefront AND admin panel
       D) Full application testing including API layer

       [Default: C if no response in 30s]

User: C
Agent: Testing both storefront and admin. Generating execution plan...
```

**Asynchronous (web UI with SSE):**

```
1. User submits prompt → run created with status "awaiting_clarification"
2. SSE event: CLARIFICATION_REQUIRED with question JSON
3. Frontend renders question card with options
4. User selects option → POST /runs/{id}/clarify with answer
5. Pipeline resumes from clarification node
```

### Clarification Events

```
EventType.CLARIFICATION_REQUIRED     → {question_id, question_text, options, timeout}
EventType.CLARIFICATION_RECEIVED     → {question_id, response, resolved_dimensions}
EventType.CLARIFICATION_COMPLETED    → {rounds_completed, new_confidence}
EventType.CLARIFICATION_TIMEOUT      → {question_id, default_applied}
EventType.CLARIFICATION_SKIPPED      → {reason: "confidence_ok" | "max_rounds_exceeded"}
```

---

# 4. EXECUTION PLANNER

## 4.1 Design

```
Location: app/agent/planner/execution_planner.py
```

### Input

- `UnifiedIntent` (from Intent Understanding)
- `AgentState` (for any existing run context, e.g., resume)

### Output

- `ExecutionPlan` (task DAG with dependencies, constraints, success criteria)

### Core Components

#### 4.1.1 Goal Decomposer

```
UnifiedIntent.goals → Goal[] (hierarchy)

Example:
  Input:  goals = ["Test checkout flow", "Verify payment processing"]
  Output:
    Goal 1: Test checkout flow
    ├── Task 1.1: Crawl checkout pages
    ├── Task 1.2: Generate checkout test scenarios
    ├── Task 1.3: Generate checkout test code
    └── Task 1.4: Execute checkout tests

    Goal 2: Verify payment processing
    ├── Task 2.1: Crawl payment pages
    ├── Task 2.2: Generate payment test scenarios
    ├── Task 2.3: Generate payment test code
    └── Task 2.4: Execute payment tests
        └── depends_on: Task 1.4 (checkout must succeed first)
```

#### 4.1.2 Task Scheduler

```
Tasks → Stage sequence with dependencies

Algorithm:
1. Map each goal's tasks to workflow stages
2. Merge overlapping stages (Goal1.crawl + Goal2.crawl → single crawl covering both)
3. Resolve dependencies (execution depends on code_generation depends on test_design...)
4. Identify parallelizable groups (crawl + inventory can't be parallel, but code_gen could)
5. Assign conditional logic (skip execution if code_gen fails)
```

#### 4.1.3 Constraint Validator

```
Validates plan against:
- System capabilities (browser available? LLM available?)
- User constraints (max duration? max LLM cost?)
- Environment constraints (headless? network access?)
- Security constraints (credentials scope)
```

#### 4.1.4 Success Criteria Mapper

```
Maps UnifiedIntent.success_criteria → measurable checkpoint values

Example:
  Input:  {"min_pass_rate": 95, "critical_paths_tested": 10}
  Output: ExecutionPlan.success_criteria = {
    "execution": {"min_pass_rate": 95.0},
    "test_design": {"min_scenarios": 10, "must_cover_critical": True},
    "crawler": {"min_pages": 5},
  }
```

## 4.2 Execution Plan Structure

```python
ExecutionPlan:
  id: "plan-abc123"
  version: 1
  goals:
    - id: "goal-1"
      description: "Test checkout flow"
      status: pending
      priority: critical
      module_scope: ["Checkout", "Cart"]
      success_criteria:
        checkout_flows_tested: 5
        payment_gateways_covered: 2
      tasks: ["task-1.1", "task-1.2", "task-1.3", "task-1.4"]
      dependencies: []
      parent_goal_id: null

  stage_sequence: [trigger, crawler, inventory, test_design, human_review, code_generation, execution, reporting]

  dependencies:
    code_generation: [test_design, human_review]
    execution: [code_generation]
    reporting: [execution]

  parallel_groups: []  # future: [[crawler_payment, crawler_admin]]

  conditional_stages:
    execution: "code_generation.status == 'completed' AND code_generation.validation_passed == true"

  constraints:
    max_llm_calls: 15
    max_runtime_minutes: 30
    browser: "chromium"
    headless: true
    environment: "staging"

  success_criteria:
    execution: {min_pass_rate: 90}
    test_design: {min_scenarios_per_module: 3}
    crawler: {min_pages_discovered: 5}

  max_retries: 3
  dynamic_replanning: true
```

## 4.3 Dynamic Replanning

When Reflection triggers a replan:

```
1. Stop current stage execution
2. Capture current AgentState as checkpoint
3. Increment ExecutionPlan.version
4. Re-evaluate goals:
   - Completed goals → keep completed
   - Failed goals → may retry or skip based on new plan
   - Pending goals → may reorder or add new
5. Regenerate stage_sequence for remaining goals
6. Resume workflow from appropriate checkpoint
```

---

# 4B. TASK HIERARCHY

## 4B.1 Design

```
Location: app/agent/planner/task_hierarchy.py
```

### Problem

The v1.0 architecture maps Intent → Goals → Stages, but stages are coarse-grained pipelines (crawler, test_design, code_generation). For a true agent, tasks should be more granular, independently schedulable, and dynamically composable.

### Target Hierarchy

```
GOAL                          (business objective)
  └── TASK                    (unit of work)
        ├── SUBTASK           (composable sub-operation)
        │     └── ACTION      (atomic operation)
        │
        ├── depends_on: [task_X, task_Y]
        ├── tool_assignment: CrawlerAgent
        └── success_criteria: {min_pages: 5, max_depth: 3}
```

### Hierarchy Levels

| Level | Definition | Example | Cardinality |
|-------|-----------|---------|-------------|
| **Goal** | Business objective from intent | "Validate checkout flow" | 1 goal per business concern |
| **Task** | Complete unit of testing work | "Crawl checkout pages", "Generate checkout tests" | 3–7 tasks per goal |
| **Subtask** | Composable sub-operation | "Extract forms from /cart page", "Generate POM for CartPage" | 1–N per task |
| **Action** | Atomic executable step | "Call Playwright navigate(/cart)", "LLM generate PageObject" | 1–N per subtask |

### Example Hierarchy

```
Goal: "Validate Checkout Flow" (priority: critical)
│
├── Task 1: "Discover checkout application structure"
│   ├── Subtask 1.1: "Navigate checkout pages"
│   │   ├── Action: Browser.navigate("/cart")
│   │   ├── Action: Browser.navigate("/checkout")
│   │   └── Action: Browser.navigate("/checkout/shipping")
│   ├── Subtask 1.2: "Extract page structure"
│   │   ├── Action: DOM.extract("/cart")
│   │   ├── Action: DOM.extract("/checkout")
│   │   └── Action: DOM.extract("/checkout/shipping")
│   └── Subtask 1.3: "Build knowledge model for checkout"
│       └── Action: KnowledgeBuilder.build(subset=["checkout"])
│   └── depends_on: []
│   └── tool_assignment: CrawlerAgent
│   └── success_criteria: {min_pages: 3, authenticated: true}
│
├── Task 2: "Generate checkout test scenarios"
│   ├── Subtask 2.1: "Analyze checkout knowledge model"
│   ├── Subtask 2.2: "Generate test scenarios"
│   └── Subtask 2.3: "Validate scenarios against coverage preferences"
│   └── depends_on: [Task 1]
│   └── tool_assignment: TestDesignAgent
│   └── success_criteria: {min_scenarios: 10, critical_covered: true}
│
├── Task 3: "Generate checkout test code"
│   ├── Subtask 3.1: "Generate IR from scenarios"
│   ├── Subtask 3.2: "Validate IR"
│   ├── Subtask 3.3: "Generate Playwright project"
│   └── Subtask 3.4: "Format and validate code"
│   └── depends_on: [Task 2]
│   └── tool_assignment: CodeGenerationAgent
│   └── success_criteria: {validation_passed: true, scenarios_implemented: 10}
│
├── Task 4: "Execute checkout tests"
│   ├── Subtask 4.1: "Setup test environment"
│   ├── Subtask 4.2: "Run Playwright tests"
│   ├── Subtask 4.3: "Collect results and artifacts"
│   └── Subtask 4.4: "Analyze failures"
│   └── depends_on: [Task 3]
│   └── tool_assignment: ExecutionAgent
│   └── success_criteria: {min_pass_rate: 0.90}
│
└── Task 5: "Report checkout test results"
    ├── Subtask 5.1: "Generate HTML dashboard"
    ├── Subtask 5.2: "Generate JUnit XML"
    └── Subtask 5.3: "Generate business-objective summary"
    └── depends_on: [Task 4]
    └── tool_assignment: ReportingService
```

### Task Scheduler (Enhanced)

```python
class TaskScheduler:
    """
    Converts goals into task hierarchies with:
    - Granular task decomposition (Goal → Task → Subtask → Action)
    - Dependency resolution within and across goals
    - Tool requirement inference
    - Parallelism identification
    """

    async def decompose_goals(
        self,
        goals: list[Goal],
        knowledge_model: Optional[KnowledgeModel],
    ) -> list[Task]:
        """
        Decompose each goal into a task hierarchy.

        For each goal:
        1. Determine required stages (crawl, design, generate, execute)
        2. Create Task per stage
        3. Decompose Task into Subtasks
        4. Infer Actions per Subtask based on target application structure
        """

    async def resolve_dependencies(self, tasks: list[Task]) -> list[Task]:
        """
        Resolve dependencies:

        Within a goal:
        - Task 2 depends on Task 1 (design needs crawl data)
        - Task 3 depends on Task 2 (code gen needs design)
        - Task 4 depends on Task 3 (execution needs code)

        Across goals:
        - Goal B's crawl may reuse Goal A's crawled data
        - Goal B's execution may depend on Goal A's pass rate
        """

    async def identify_parallel_groups(
        self, tasks: list[Task]
    ) -> list[list[Task]]:
        """
        Identify tasks that can run in parallel:

        - Goals A and B can be crawled in parallel (different modules)
        - Test design for Goal A and B can be parallelized
        - Code generation per module can be parallelized
        """

    async def infer_tool_requirements(
        self, tasks: list[Task]
    ) -> dict[str, list[str]]:
        """
        For each task, determine what tools/capabilities are needed.

        Returns: task_id → [capability_ids]
        """
```

### Task Model

```python
class Task(BaseModel):
    id: str
    goal_id: str
    name: str
    description: str
    stage: Stage
    priority: str                          # critical | high | medium | low
    depends_on: list[str] = []             # task IDs
    subtasks: list[Subtask] = []
    tool_requirements: list[str] = []      # capability IDs needed
    success_criteria: dict[str, Any] = {}
    estimated_duration_minutes: float = 0.0
    status: GoalStatus = GoalStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3


class Subtask(BaseModel):
    id: str
    task_id: str
    name: str
    description: str
    actions: list[Action] = []
    depends_on: list[str] = []             # subtask IDs within same task
    status: GoalStatus = GoalStatus.PENDING


class Action(BaseModel):
    id: str
    subtask_id: str
    type: str                              # browser_navigate | dom_extract | llm_generate |
                                           # file_write | npm_install | playwright_run | ...
    parameters: dict[str, Any] = {}
    tool_id: str                           # CapabilityRegistry ID
    atomic: bool = True                    # Cannot be partially executed
    status: GoalStatus = GoalStatus.PENDING
```

---

# 4C. CAPABILITY REGISTRY

## 4C.1 Design

```
Location: app/agent/registry/capability_registry.py
```

### Purpose

A centralized catalog of every tool, agent, service, and utility the system can use. The Execution Planner and Tool Selection Layer query this registry to determine what's available.

### CapabilityEntry Schema

```python
class CapabilityEntry(BaseModel):
    """A registered capability in the system."""
    capability_id: str                     # UUID
    name: str                              # "CrawlerAgent", "LLMClient", "BrowserManager"
    type: CapabilityType                   # agent | service | tool | browser | generator | validator

    # ── Interface ──────────────────────────────────────────────
    inputs: dict[str, str] = Field(        # parameter → type
        default_factory=dict,
        example={"url": "str", "credentials": "AuthContext", "scope": "list[str]"}
    )
    outputs: dict[str, str] = Field(       # return field → type
        default_factory=dict,
        example={"crawl_package": "CrawlPackage", "screenshots": "list[bytes]"}
    )

    # ── Constraints ────────────────────────────────────────────
    requires: list[str] = []               # "browser_running", "llm_available", "network"
    conflicts_with: list[str] = []         # capabilities that cannot run simultaneously
    max_concurrent: int = 1                # Max parallel instances

    # ── Cost ───────────────────────────────────────────────────
    cost_model: str = "free"               # free | per_call | per_token | per_minute
    estimated_cost_per_call: float = 0.0
    average_duration_ms: float = 0.0

    # ── Quality ─────────────────────────────────────────────────
    success_rate: float = 1.0              # Historical success rate (0–1)
    quality_score: float = 1.0             # Composite quality score (0–1)
    flakiness_score: float = 0.0           # 0 = reliable, 1 = very flaky

    # ── Status ──────────────────────────────────────────────────
    status: str = "available"              # available | degraded | unavailable | deprecated
    health_check_endpoint: Optional[str] = None  # if applicable

    # ── SLA ─────────────────────────────────────────────────────
    sla: dict[str, Any] = Field(default_factory=dict)
    # e.g. {"max_latency_ms": 30000, "uptime_pct": 99.9}

    # ── Metadata ────────────────────────────────────────────────
    version: str = "1.0.0"
    tags: list[str] = []                   # ["playwright", "browser", "discovery"]
    documentation_url: Optional[str] = None


class CapabilityType(str, Enum):
    AGENT = "agent"                        # AI-powered agent (TestDesignAgent, etc.)
    SERVICE = "service"                    # Deterministic service (InventoryAggregator)
    TOOL = "tool"                          # Utility tool (CodeFormatter, FileWriter)
    BROWSER = "browser"                    # Browser automation (Playwright)
    GENERATOR = "generator"                # Code generator (TemplateEngine, IRGenerator)
    VALIDATOR = "validator"                # Validator (IRValidator, CodeValidator)
    LLM_CLIENT = "llm_client"             # LLM provider (OpenAI, Anthropic, Ollama)
    EXECUTOR = "executor"                  # Test executor (PlaywrightRunner)
    STORAGE = "storage"                    # Storage backend (LocalFS, S3, PG)
```

### Registry Interface

```python
class CapabilityRegistry:
    """Centralized catalog of all available capabilities."""

    async def register(self, capability: CapabilityEntry) -> str:
        """Register a new capability."""

    async def unregister(self, capability_id: str) -> None:
        """Remove a capability."""

    async def get(self, capability_id: str) -> CapabilityEntry:
        """Get capability by ID."""

    async def query(
        self,
        capability_type: Optional[CapabilityType] = None,
        tags: Optional[list[str]] = None,
        required_outputs: Optional[list[str]] = None,
        status: str = "available",
    ) -> list[CapabilityEntry]:
        """
        Find capabilities matching criteria.

        Example: Find all agents that can produce a test_plan
            query(required_outputs=["TestPlan"], capability_type=CapabilityType.AGENT)
        """

    async def get_available(self) -> list[CapabilityEntry]:
        """Get all currently available (non-degraded) capabilities."""

    async def check_health(self, capability_id: str) -> bool:
        """Check if a capability is healthy (ping health endpoint)."""

    async def update_stats(
        self,
        capability_id: str,
        success_rate: Optional[float] = None,
        flakiness_score: Optional[float] = None,
        average_duration_ms: Optional[float] = None,
    ) -> None:
        """Update quality stats from LearningMemory."""

    async def get_by_io(
        self,
        inputs: dict[str, str],
        outputs: dict[str, str],
    ) -> list[CapabilityEntry]:
        """Find capabilities that match given I/O contract."""
```

### Initial Capability Catalog (Phase 1)

```
Capability ID          Type        Status       Cost Model      Avg Latency
──────────────────────  ──────────  ───────────  ─────────────   ───────────
trigger-agent           agent       available    free            ~50ms
crawler-agent           agent       available    per_minute      ~30s/page
browser-manager         browser     available    per_minute      ~2s startup
llm-client-openai       llm_client  available    per_token       ~5s/call
llm-client-ollama       llm_client  available    free            ~15s/call
inventory-aggregator    service     available    free            ~100ms
test-design-agent       agent       available    per_token       ~30s/call
human-review-service    service     available    free            ~10ms
code-generation-agent   agent       available    per_token       ~5min/project
ir-generation-agent     agent       available    per_token       ~30s/call
ir-validator            validator   available    free            ~50ms
template-engine         generator   available    free            ~2s/project
code-formatter          tool        available    free            ~500ms
code-validator          validator   available    free            ~2s
execution-agent         executor    available    per_minute      ~varies
playwright-runner       executor    available    per_minute      ~30s/test
failure-analyzer        tool        available    free            ~100ms
report-generator        generator   available    free            ~3s
artifact-collector      tool        available    free            ~200ms
screenshot-capture      tool        available    free            ~2s
prompt-builder          tool        available    free            ~5ms
prompt-loader           tool        available    free            ~2ms
credential-store        storage     available    free            ~10ms
knowledge-builder       agent       available    per_token       ~5s      (Phase 2)
reflection-engine       agent       available    per_token       ~10s     (Phase 2)
recovery-engine         service     available    free            ~50ms    (Phase 2)
```

---

# 4D. TOOL SELECTION LAYER

## 4D.1 Design

```
Location: app/agent/selection/tool_selection.py
```

### Purpose

Given a task from the Execution Plan, determine which capability (agent/service/tool) should execute it. This decouples the task definition from the implementation.

### Selection Algorithm

```python
class ToolSelector:
    """
    Selects the best tool for each task based on:
    - Capability match (does this tool produce the required output?)
    - Availability (is the tool healthy and accessible?)
    - Cost (prefer cheaper tools when quality is similar)
    - Historical success rate (from LearningMemory)
    - User constraints (browser preference, LLM provider)
    - Stage compatibility (some tools only work in specific stages)
    """

    async def select_tool(
        self,
        task: Task,
        registry: CapabilityRegistry,
        state: AgentState,
    ) -> ToolSelection:
        """
        Select the best tool for a task.

        Algorithm:
        1. Query registry for tools that can produce task's required outputs
        2. Filter by availability (health check)
        3. Filter by constraints (user preferences, system state)
        4. Score each candidate:
           score = w1*capability_match + w2*success_rate + w3*(1/flakiness)
                   - w4*cost_factor + w5*user_preference_bonus
        5. Select highest-scoring candidate
        6. Log fallback options in case selected tool fails
        """

    async def select_all(
        self,
        plan: ExecutionPlan,
        registry: CapabilityRegistry,
        state: AgentState,
    ) -> dict[str, ToolSelection]:
        """Select tools for all tasks in the execution plan."""

    def compute_tool_score(
        self,
        task: Task,
        candidate: CapabilityEntry,
        state: AgentState,
    ) -> float:
        """
        Composite scoring formula:

        score = (
            capability_match_score * 0.35 +
            success_rate * 0.25 +
            (1.0 - flakiness_score) * 0.15 -
            normalized_cost * 0.15 +
            user_preference_bonus * 0.10
        )
        """

    async def resolve_dependencies(
        self,
        selections: dict[str, ToolSelection],
        registry: CapabilityRegistry,
    ) -> dict[str, ToolSelection]:
        """
        After selecting tools, ensure their dependencies are met.

        Example: If CrawlerAgent is selected but BrowserManager is
        unavailable, either:
        - Select a different crawler tool
        - Provision BrowserManager
        - Flag as blocked
        """
```

### Scoring Weights Configuration

```python
class ToolScoringConfig(BaseModel):
    """Configurable weights for tool selection scoring."""
    capability_match_weight: float = 0.35
    success_rate_weight: float = 0.25
    reliability_weight: float = 0.15      # 1 - flakiness_score
    cost_weight: float = 0.15
    user_preference_weight: float = 0.10

    # User preferences (from UnifiedIntent)
    prefer_local_llm: bool = True          # Ollama over OpenAI if both available
    prefer_fast_tools: bool = False        # Speed over quality
    budget_limit_per_run: float = 0.0      # 0 = unlimited
```

### Tool Selection Events

```
EventType.TOOL_SELECTION_STARTED     → {task_count, plan_version}
EventType.TOOL_SELECTED              → {task_id, tool_name, score, alternatives: [...]}
EventType.TOOL_SELCTION_COMPLETED    → {selections_count, warnings: [...]}
EventType.TOOL_UNAVAILABLE           → {tool_name, reason, task_ids_affected}
EventType.TOOL_FALLBACK_TRIGGERED    → {original_tool, fallback_tool, task_id, reason}
```

### Integration with Recovery Engine

When a selected tool fails:
1. Recovery Engine receives the failure
2. If `RETRY` strategy is chosen, same tool is retried
3. If `RETRY_WITH_CONTEXT` strategy fails, Tool Selection Layer selects the fallback tool from `ToolSelection.fallback_tool_ids`
4. If no fallback exists, `FAILURE_ISOLATION` or `DEGRADED_MODE` applies

---

# 5. CONTEXT MANAGER

## 5.1 Design

```
Location: app/agent/context/context_manager.py
```

### Responsibility

The Context Manager is the **gatekeeper** that guarantees every stage receives complete context. No stage ever:
- Reads only partial state
- Reconstructs intent from scratch
- Loses business objective between stages
- Operates without the original user prompt

### Interface

```python
class ContextManager:
    """
    Guarantees context propagation across all stages.

    Every stage calls context_manager.inject(state, stage) before execution.
    Context Manager returns an enriched state with all relevant context
    for that stage.
    """

    async def inject(self, state: AgentState, stage: Stage) -> ContextInjection:
        """Enrich state with stage-appropriate context."""

    async def snapshot(self, state: AgentState, stage: Stage) -> ContextFrame:
        """Create immutable snapshot after stage completion."""

    async def validate(self, state: AgentState, stage: Stage) -> ContextValidation:
        """Validate that stage has all required context fields."""


@dataclass
class ContextInjection:
    stage: Stage
    enriched_state: AgentState
    context_summary: str         # human-readable summary for UI/logs
    missing_context: list[str]   # fields that were missing and defaulted
    warnings: list[str]

@dataclass
class ContextValidation:
    valid: bool
    missing_required: list[str]
    missing_optional: list[str]
```

### Context Contract Per Stage

```
Stage                          Required Context Fields
────────────────────────────── ───────────────────────────────────────────
trigger                        original_prompt, request_data, auth_context
crawler                        unified_intent.target_urls, unified_intent.scope,
                                auth_context, execution_plan.constraints
inventory                      crawl_package_ref, unified_intent.module_scope
test_design                    inventory_ref, knowledge_model, unified_intent.goals,
                                unified_intent.business_objective,
                                unified_intent.coverage_preferences,
                                unified_intent.custom_instructions
human_review                   test_plan_ref, unified_intent, execution_plan
code_generation                approved_test_plan_ref, unified_intent.output_preferences,
                                knowledge_model, execution_plan.constraints
execution                      generated_code_ref, unified_intent.environment,
                                auth_context, execution_plan.constraints
reporting                      execution_results_ref, unified_intent.business_objective,
                                unified_intent.success_criteria,
                                execution_plan.success_criteria,
                                context_history (all ContextFrames)
reflection                     stage_results (all), execution_plan,
                                unified_intent.success_criteria
```

### Context Propagation Guarantee

The Context Manager wraps every stage node call:

```python
async def agentic_stage_wrapper(node_fn, stage: Stage, state: AgentState):
    context_mgr = get_context_manager()

    # 1. Validate required context before execution
    validation = await context_mgr.validate(state, stage)
    if not validation.valid:
        raise ContextError(f"Missing required context for {stage}: {validation.missing_required}")

    # 2. Inject enriched context
    injection = await context_mgr.inject(state, stage)
    enriched_state = injection.enriched_state

    # 3. Execute stage
    result_state = await node_fn(enriched_state)

    # 4. Snapshot context after execution
    frame = await context_mgr.snapshot(result_state, stage)
    result_state.stage_history.append(frame)

    return result_state
```

---

# 6. KNOWLEDGE MODEL

## 6.1 Design

Replace the flat `Inventory` JSON with a structured `KnowledgeModel`.

### Current Inventory (Problem)

```
Inventory.json:
  pages: [flat list of PageRecord]
  forms: [flat list of FormRecord]
  inputs: [flat list of InputRecord]
  ...
```

Problems:
- No relationships between pages/forms/components
- No user flows
- No domain concepts
- Pages are just data records, not interconnected entities
- LLM has to reconstruct meaning from flat data every time

### Target Knowledge Model

```python
class KnowledgeModel(BaseModel):
    """
    Structured semantic knowledge about the application under test.

    This is NOT a flat dump of crawler output. It is a processed,
    relationship-aware, LLM-friendly knowledge graph.
    """

    # ── Pages (hierarchical, not flat) ─────────────────────────
    pages: list[PageNode]

    # ── Forms (linked to pages, with validation rules) ─────────
    forms: list[FormNode]

    # ── User Flows (sequences of page interactions) ────────────
    flows: list[UserFlow]

    # ── API endpoints (with request/response schemas) ──────────
    apis: list[ApiNode]

    # ── UI Components (reusable widgets) ───────────────────────
    components: list[ComponentNode]

    # ── Navigation (directed graph, not flat edges) ────────────
    navigation_graph: NavigationGraph

    # ── Relationships ──────────────────────────────────────────
    relationships: list[Relationship]

    # ── Domain Concepts ────────────────────────────────────────
    domain_concepts: list[str]


class PageNode(BaseModel):
    id: str
    url: str
    title: str
    parent_page_id: Optional[str]        # hierarchy
    child_page_ids: list[str]
    forms_on_page: list[str]             # FormNode refs
    components_on_page: list[str]        # ComponentNode refs
    apis_called_by_page: list[str]       # ApiNode refs
    entry_points_to: list[str]           # flow entry points
    page_type: str                       # login|dashboard|list|form|detail|landing
    authentication_required: bool
    route_pattern: Optional[str]         # e.g., "/users/:id"
    metadata: dict[str, Any]


class FormNode(BaseModel):
    id: str
    page_id: str                         # parent page
    action_url: Optional[str]
    method: str                          # GET|POST|PUT
    fields: list[FormField]
    validation_rules: list[str]          # inferred: required, email, min-length, etc.
    submit_button_id: str
    related_api_id: Optional[str]        # API this form submits to

class FormField(BaseModel):
    name: str
    type: str                            # text|password|email|select|checkbox|radio|file
    required: bool
    placeholder: Optional[str]
    validation: list[str]                # inferred rules

class UserFlow(BaseModel):
    id: str
    name: str
    description: str
    steps: list[FlowStep]
    entry_page_id: str
    exit_page_id: Optional[str]
    is_authenticated: bool
    category: str                        # happy_path|edge_case|error_path|auth_flow

class FlowStep(BaseModel):
    order: int
    page_id: str
    action: str                          # navigate|click|fill|submit|wait|assert
    target: Optional[str]                # element selector or URL
    expected_outcome: str

class ApiNode(BaseModel):
    id: str
    method: str                          # GET|POST|PUT|DELETE|PATCH
    url_pattern: str
    request_body_schema: Optional[dict]
    response_body_sample: Optional[dict]
    status_codes_observed: list[int]
    called_by_pages: list[str]
    related_forms: list[str]

class ComponentNode(BaseModel):
    id: str
    name: str
    type: str                            # table|modal|navbar|sidebar|card|datagrid|chart
    page_ids: list[str]                  # pages this component appears on
    selector: str
    is_reusable: bool                    # appears on multiple pages
    child_components: list[str]

class NavigationGraph(BaseModel):
    nodes: dict[str, NavNode]            # page_id → NavNode
    edges: list[NavEdge]

class NavNode(BaseModel):
    page_id: str
    depth: int
    is_entry_point: bool
    reachable_from: list[str]

class NavEdge(BaseModel):
    from_page_id: str
    to_page_id: str
    via: str                             # link|button|form_submit|redirect|js_navigate
    label: Optional[str]                 # the link/button text

class Relationship(BaseModel):
    source_id: str
    target_id: str
    relationship_type: str               # contains|submits_to|navigates_to|renders_on|calls_api
    metadata: dict[str, Any]
```

## 6.2 Knowledge Model Builder

```
Location: app/agent/knowledge/knowledge_builder.py
```

Process:

1. **Ingest**: Load `inventory.json` (flat list of pages, forms, inputs, buttons, etc.)
2. **Structurize**: Group elements by page → `PageNode`, `FormNode`, `ComponentNode`
3. **Link**: Identify cross-references:
   - Form on page → `PageNode.forms_on_page`
   - Button submits form → `FormNode.submit_button_id`
   - API call from page → `ApiNode.called_by_pages`
4. **Infer Flow**: Analyze navigation edges to build `UserFlow` sequences
5. **Deduplicate**: Identify `ComponentNode.is_reusable` across pages
6. **Classify**: Tag page types (login, dashboard, form, list, detail)
7. **Validate**: Ensure all references resolve (no dangling IDs)
8. **Persist**: Store as `knowledge-model.json` in ArtifactRegistry
9. **Update AgentState**: `state.knowledge_model = model`

---

# 7. MEMORY

## 7.1 Memory Architecture

```
┌───────────────────────────────────────────────────────────────┐
│                       MEMORY MANAGER                          │
│                app/agent/memory/memory_manager.py              │
├───────────────────────────────────────────────────────────────┤
│                                                                │
│  ┌─────────────────┐   ┌─────────────────┐                    │
│  │  SHORT-TERM     │   │  LONG-TERM      │                    │
│  │  MEMORY         │   │  MEMORY         │                    │
│  │                 │   │                 │                    │
│  │ • current run   │   │ • knowledge     │                    │
│  │   context       │   │   model         │                    │
│  │ • stage I/O     │   │ • app patterns  │                    │
│  │ • goal state    │   │ • discovered    │                    │
│  │ • reflection    │   │   behaviors     │                    │
│  │   decisions     │   │ • domain        │                    │
│  │ • in AgentState │   │   vocabulary    │                    │
│  │ • lifetime: 1   │   │ • lifetime:     │                    │
│  │   run           │   │   cross-run     │                    │
│  └─────────────────┘   └─────────────────┘                    │
│                                                                │
│  ┌─────────────────┐   ┌─────────────────┐                    │
│  │  RUN MEMORY     │   │  HISTORICAL     │                    │
│  │                 │   │  MEMORY         │                    │
│  │ • all state     │   │ • past run      │                    │
│  │   snapshots     │   │   summaries     │                    │
│  │ • checkpoint    │   │ • common        │                    │
│  │   data          │   │   failures      │                    │
│  │ • artifact      │   │ • performance   │                    │
│  │   manifests     │   │   trends        │                    │
│  │ • stored on     │   │ • stored in     │                    │
│  │   disk (JSON)   │   │   PostgreSQL    │                    │
│  └─────────────────┘   └─────────────────┘                    │
│                                                                │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  LEARNING MEMORY                                        │  │
│  │                                                         │  │
│  │ • feedback from reflection                              │  │
│  │ • prompt improvements (which prompts work best)         │  │
│  │ • LLM response patterns (which models perform well)     │  │
│  │ • error recovery patterns (which fixes work)            │  │
│  │ • code generation quality trends                        │  │
│  │ • stored in PostgreSQL with embeddings                  │  │
│  │ • queried via semantic search                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

## 7.2 What Each Memory Stores

### Short-Term Memory
- **Location**: In-memory within `AgentState` + serialized to run workspace
- **Contents**: All `AgentState` fields, `ContextFrame` history, `ReflectionRecord` log
- **Lifetime**: Duration of a single run
- **Purpose**: Fast, zero-latency access to current run context. Every stage reads from it.

### Long-Term Memory
- **Location**: `knowledge-model.json` (file-based) + PostgreSQL `knowledge_models` table
- **Contents**: The `KnowledgeModel` — pages, forms, flows, APIs, components, navigation
- **Lifetime**: Cross-run. Updated incrementally as the same application is tested repeatedly.
- **Purpose**: Avoid re-discovering application structure on each run. Reuse knowledge.

### Run Memory
- **Location**: `storage/runs/{run_id}/` — checkpoint files, contract files, artifact manifests
- **Contents**: Complete per-run data: all contracts, artifacts, logs, screenshots
- **Lifetime**: Until run is archived/expired
- **Purpose**: Resume, debug, audit, replay

### Historical Memory
- **Location**: PostgreSQL tables: `run_summaries`, `execution_trends`
- **Contents**: Aggregated metrics from past runs, pass rate trends, common failures
- **Lifetime**: Long-term (configurable retention)
- **Purpose**: Show testing health over time, identify flaky areas, prioritize maintenance

### Learning Memory
- **Location**: PostgreSQL + pgvector embeddings
- **Contents**:
  - Prompt → output quality mappings
  - Error patterns → successful recovery strategies
  - Module → optimal test approach mappings
  - LLM response quality ratings
- **Lifetime**: Permanent (cumulative learning)
- **Purpose**: Improve agent performance over time through experience

## 7.3 Memory Manager Interface

```python
class MemoryManager:
    """Unified memory access layer."""

    async def store_short_term(self, run_id: UUID, state: AgentState) -> None:
        """Persist current run state to workspace."""

    async def load_short_term(self, run_id: UUID) -> Optional[AgentState]:
        """Restore run state for resume."""

    async def store_long_term(self, project_id: UUID, knowledge: KnowledgeModel) -> None:
        """Merge new knowledge into project knowledge base."""

    async def load_long_term(self, project_id: UUID) -> KnowledgeModel:
        """Load knowledge for reuse."""

    async def store_historical(self, run_id: UUID, summary: dict) -> None:
        """Archive run summary for trend analysis."""

    async def query_historical(self, project_id: UUID, filters: dict) -> list[dict]:
        """Query past runs for patterns."""

    async def store_learning(self, entry: LearningEntry) -> None:
        """Store a learning from reflection feedback."""

    async def query_learning(self, context: str, top_k: int = 5) -> list[LearningEntry]:
        """Semantic search for relevant past learnings."""

    async def store_run(self, run_id: UUID, checkpoint: dict) -> None:
        """Write checkpoint for resume capability."""

    async def load_run(self, run_id: UUID) -> Optional[dict]:
        """Load checkpoint for resume."""
```

---

# 8. REFLECTION

## 8.1 Design

```
Location: app/agent/reflection/reflection_engine.py
```

### Reflection Gates

Reflection gates are placed after each major workflow stage. They evaluate whether the stage's output aligns with the user's original intent and execution plan.

```
  STAGE                       REFLECTION GATE EVALUATION
  ─────────────────────────   ───────────────────────────────────────────────
  Crawler                     Did we discover all pages needed for the scope?
                               Are there missing modules? Should we re-crawl?
  Test Design                 Does the test plan cover all business objectives?
                               Are critical paths covered? Any gap analysis?
  Code Generation             Does the generated code implement all approved
                               scenarios? Are there unimplemented scenarios?
  Execution                   Did execution meet success criteria?
                               Were failures expected or critical?
  Reporting                   Does the report accurately reflect business
                               objectives? Are conclusions valid?
```

### Reflection Engine Interface

```python
class ReflectionEngine:
    """
    Evaluates stage output against goals and decides next action.
    """

    async def reflect(
        self,
        state: AgentState,
        stage: Stage,
        output: dict[str, Any],
    ) -> ReflectionDecision:
        """
        Evaluate stage output and return a decision.

        Returns: Continue | Replan | Retry | Abort | Warn
        """

    async def evaluate_crawler(
        self, state: AgentState, crawl_output: dict
    ) -> ReflectionRecord:
        """
        Check: Do discovered pages cover all required modules?
        Check: Are scoped modules found?
        Check: Depth/coverage adequate?
        """

    async def evaluate_test_design(
        self, state: AgentState, test_plan: dict
    ) -> ReflectionRecord:
        """
        Check: Scenarios per module meet minimum?
        Check: Critical paths covered?
        Check: Priorities aligned with business objectives?
        Check: Coverage types match preferences?
        """

    async def evaluate_code_generation(
        self, state: AgentState, gen_output: dict
    ) -> ReflectionRecord:
        """
        Check: All scenarios implemented?
        Check: Validation passed?
        Check: Output preferences honored?
        """

    async def evaluate_execution(
        self, state: AgentState, exec_output: dict
    ) -> ReflectionRecord:
        """
        Check: Pass rate meets success criteria?
        Check: Critical failures?
        Check: Expected vs actual coverage?
        """

    async def evaluate_reporting(
        self, state: AgentState, report_output: dict
    ) -> ReflectionRecord:
        """
        Check: Report addresses business objectives?
        Check: Conclusions supported by evidence?
        Check: Actionable recommendations?
        """


class ReflectionDecision(Enum):
    CONTINUE = "continue"      # Proceed to next stage
    REPLAN = "replan"          # Update execution plan, may re-run this stage
    RETRY = "retry"            # Re-run the same stage with same inputs
    ABORT = "abort"            # Stop the run, notify user
    WARN = "warn"              # Continue but log a warning
```

### Reflection Decision Logic

```python
async def reflect(self, state, stage, output) -> ReflectionDecision:
    # 1. Evaluate stage-specific criteria
    if stage == Stage.CRAWLER:
        record = await self.evaluate_crawler(state, output)
    elif stage == Stage.TEST_DESIGN:
        record = await self.evaluate_test_design(state, output)
    # ...

    # 2. Store reflection record
    state.reflection_log.append(record)

    # 3. Determine decision
    if not record.passed:
        if record.replan_triggered:
            # Increment plan version, regenerate task DAG
            state.execution_plan.version += 1
            state.replan_count += 1
            return ReflectionDecision.REPLAN
        elif len(state.retry_history) < state.execution_plan.max_retries:
            return ReflectionDecision.RETRY
        elif record.issues_found and all(is_critical(i) for i in record.issues_found):
            return ReflectionDecision.ABORT
        else:
            return ReflectionDecision.WARN

    return ReflectionDecision.CONTINUE
```

### Reflection Scenarios (Examples)

| Stage | Observation | Decision |
|-------|------------|----------|
| Crawler | 0 pages discovered in "Payments" module | REPLAN — broaden crawl scope or WARN user |
| Crawler | Only 2 of 5 expected pages found | WARN — continue with reduced scope |
| Test Design | 0 scenarios for "boundary" coverage despite user requesting it | RETRY — regenerate test plan with coverage emphasis |
| Test Design | 3 critical scenarios missing for checkout | RETRY — regenerate with missing scenario feedback |
| Code Gen | 2 scenarios failed validation | RETRY — regenerate IR for failed scenarios |
| Code Gen | All passed, but TypeScript output when user wanted Python | RETRY — regenerate with corrected output preference |
| Execution | Pass rate 45%, success criteria is 90% | ABORT — report failures, suggest fixes |
| Execution | Pass rate 85%, success criteria is 90% | WARN — continue, highlight in report |
| Reporting | Report doesn't mention business objective | REGENERATE — regenerate report with business context |

---

# 8B. CONFIDENCE GATES

## 8B.1 Design

```
Location: app/agent/gates/confidence_gates.py
```

### Problem

Reflection evaluates semantic alignment (did the stage achieve the business objective?). But Reflection is expensive (LLM call) and is reserved for major stages. Many stages need fast, deterministic quality checks that don't require an LLM.

Confidence Gates fill this gap — lightweight threshold checks that run after every stage.

### Difference: Confidence Gates vs Reflection

| Aspect | Confidence Gates | Reflection |
|--------|-----------------|------------|
| **When** | After EVERY stage | After MAJOR stages only |
| **Cost** | Free (deterministic) | LLM call (costly) |
| **Purpose** | Quality threshold enforcement | Semantic alignment evaluation |
| **Example** | "Did crawler find >= 5 pages?" | "Do discovered pages cover the business-critical modules?" |
| **Decision** | PASS / FAIL / WARN | CONTINUE / REPLAN / RETRY / ABORT |
| **Retry** | Automatic (configurable) | Requires planner involvement |

### Gate Configuration

Each gate is configured with a threshold:

```python
DEFAULT_CONFIDENCE_GATES = [
    # Trigger
    ConfidenceGateConfig(
        stage=Stage.TRIGGER,
        metric="workspace_created",
        threshold=1.0,
        comparator=">=",
        gate_type="hard",
        failure_action="abort",
        auto_retry=False,
    ),
    # Crawler
    ConfidenceGateConfig(
        stage=Stage.CRAWLER,
        metric="pages_visited",
        threshold=3,               # Min 3 pages must be discovered
        comparator=">=",
        gate_type="soft",          # Soft: warn but continue
        failure_action="warn",
    ),
    ConfidenceGateConfig(
        stage=Stage.CRAWLER,
        metric="error_rate",
        threshold=0.3,             # Max 30% of pages can fail
        comparator="<=",
        gate_type="hard",
        failure_action="retry",
        auto_retry=True,
        max_retries=2,
    ),
    # Test Design
    ConfidenceGateConfig(
        stage=Stage.TEST_DESIGN,
        metric="scenario_count",
        threshold=5,               # Min 5 scenarios required
        comparator=">=",
        gate_type="soft",
        failure_action="warn",
    ),
    ConfidenceGateConfig(
        stage=Stage.TEST_DESIGN,
        metric="critical_covered",
        threshold=1.0,             # All critical paths must be covered
        comparator=">=",
        gate_type="hard",
        failure_action="retry",
        auto_retry=True,
        max_retries=1,
    ),
    # Code Generation
    ConfidenceGateConfig(
        stage=Stage.CODE_GENERATION,
        metric="validation_passed",
        threshold=1.0,             # Must pass validation
        comparator=">=",
        gate_type="hard",
        failure_action="retry",
        auto_retry=True,
        max_retries=2,
    ),
    ConfidenceGateConfig(
        stage=Stage.CODE_GENERATION,
        metric="scenarios_implemented",
        threshold=0.90,            # At least 90% of scenarios converted to code
        comparator=">=",
        gate_type="soft",
        failure_action="warn",
    ),
    # Execution
    ConfidenceGateConfig(
        stage=Stage.EXECUTION,
        metric="pass_rate",
        threshold=0.80,            # At least 80% pass rate
        comparator=">=",
        gate_type="soft",
        failure_action="warn",
    ),
    ConfidenceGateConfig(
        stage=Stage.EXECUTION,
        metric="critical_tests_passed",
        threshold=1.0,             # All critical tests must pass
        comparator=">=",
        gate_type="hard",
        failure_action="abort",
        auto_retry=False,
    ),
    # Reporting
    ConfidenceGateConfig(
        stage=Stage.REPORTING,
        metric="report_completeness",
        threshold=1.0,             # Report must be complete
        comparator=">=",
        gate_type="hard",
        failure_action="retry",
        auto_retry=True,
        max_retries=1,
    ),
]
```

### Confidence Gate Engine

```python
class ConfidenceGateEngine:
    """
    Evaluates threshold-based quality checks after each stage.

    Lightweight, deterministic, no LLM calls.
    """

    async def evaluate(
        self,
        state: AgentState,
        stage: Stage,
        stage_output: dict[str, Any],
    ) -> list[ConfidenceGateResult]:
        """
        Evaluate all configured gates for this stage.

        For each configured gate:
        1. Extract the metric value from stage_output
        2. Compare against threshold
        3. Record PASS / FAIL result
        4. If FAIL and gate_type == "hard" and auto_retry → trigger retry
        5. If FAIL and gate_type == "hard" and !auto_retry → ABORT
        6. If FAIL and gate_type == "soft" → WARN and continue

        Returns list of results for event emission and state recording.
        """

    async def get_stage_gates(self, stage: Stage) -> list[ConfidenceGateConfig]:
        """Get all configured gates for a given stage."""

    async def extract_metric(
        self, stage_output: dict[str, Any], metric_name: str
    ) -> Any:
        """Extract a specific metric from stage output."""

    async def check_threshold(
        self, actual: float, threshold: float, comparator: str
    ) -> bool:
        """Compare: actual >= threshold, actual <= threshold, etc."""

    async def handle_gate_failure(
        self,
        state: AgentState,
        stage: Stage,
        gate: ConfidenceGateConfig,
        result: ConfidenceGateResult,
    ) -> GateAction:
        """
        Decide what to do when a gate fails.

        Returns: RETRY | WARN_AND_CONTINUE | SKIP_STAGE | ABORT
        """
```

### Gate Evaluation in the Workflow Loop

```python
async def agentic_stage_wrapper(node_fn, stage: Stage, state: AgentState):
    # ... execute stage ...
    result_state = await node_fn(enriched_state)

    # ── Confidence Gate Evaluation ────────────────────────────
    gate_engine = get_confidence_gate_engine()
    gate_results = await gate_engine.evaluate(result_state, stage, stage_output)

    result_state.confidence_gate_results.extend(gate_results)

    for result in gate_results:
        if not result.passed and result.severity == "error":
            result_state.gate_failure_count += 1

            if result_state.gate_failure_count >= result_state.max_gate_failures:
                raise GateFailureError(
                    f"Too many confidence gate failures ({result_state.gate_failure_count}). Aborting."
                )

    # ── If all gates passed → proceed to next stage     ──────
    # ── If soft gates failed → WARN and continue        ──────
    # ── If hard gates failed → RETRY or ABORT           ──────

    return result_state
```

### User-Configurable Gates

Gates can be customized per run via `ExecutionPlan.constraints`:

```python
# Example: User wants a stricter pass rate threshold for execution
execution_plan.constraints["confidence_gates"] = [
    {
        "stage": "execution",
        "metric": "pass_rate",
        "threshold": 0.95,     # Custom: 95% instead of default 80%
        "gate_type": "hard",
        "failure_action": "retry",
    }
]
```

---

# 8C. GOAL SATISFACTION ENGINE

## 8C.1 Design

```
Location: app/agent/satisfaction/goal_satisfaction.py
```

### Problem

In the v1.0 architecture, a stage completing successfully is treated as success. But "stage completed" ≠ "user goal satisfied." A test plan might have 50 scenarios but miss the one critical checkout flow. The execution might pass 95% but the 5% that failed were the most important tests.

### Purpose

The Goal Satisfaction Engine evaluates whether each business goal was truly met based on **evidence**, not just whether the pipeline ran.

### Evaluation Process

```
FOR EACH GOAL in execution_plan.goals:

    1. COLLECT EVIDENCE
       ├── Execution results (pass rates, per-goal)
       ├── Coverage data (which scenarios actually ran)
       ├── Confidence gate results (any failures?)
       ├── Reflection evaluations (semantic alignment)
       ├── Human review decisions (was plan approved?)
       └── Cross-goal dependencies (did upstream goals pass?)

    2. EVALUATE SATISFACTION
       ├── Compare pass_rate against goal.success_criteria
       ├── Verify critical_paths were tested
       ├── Check coverage preferences were honored
       ├── Analyze gap: what was planned vs what was executed
       └── Weight evidence by source reliability

    3. DETERMINE VERDICT
       ├── SATISFIED: All evidence confirms goal met
       ├── PARTIALLY: Core met, gaps identified but non-critical
       ├── UNSATISFIED: Goal not met, evidence contradicts
       └── INCONCLUSIVE: Not enough data (e.g., no tests ran)

    4. RECOMMEND
       ├── SATISFIED → mark complete, proceed to next goal
       ├── PARTIALLY → report gaps, optionally replan
       └── UNSATISFIED → trigger replan OR escalate to user
```

### Satisfaction Evidence Sources

| Source | Weight | What it provides |
|--------|--------|-----------------|
| `execution_results` | 0.40 | Pass rates, failure data per scenario/goal |
| `reflection_log` | 0.25 | Semantic evaluation of stage output quality |
| `confidence_gate_results` | 0.15 | Threshold-based quality checks |
| `test_plan` | 0.10 | Covered vs uncovered scenarios |
| `human_review` | 0.10 | User's explicit approval/rejection |
| `cross_goal_dependencies` | modifier | Upstream goal success influences downstream |

### Satisfaction Engine Interface

```python
class GoalSatisfactionEngine:
    """
    Evidence-based goal satisfaction evaluation.

    Does NOT just check if stages completed.
    Evaluates whether goals were TRULY satisfied based on evidence.
    """

    async def evaluate_all_goals(
        self, state: AgentState
    ) -> dict[str, GoalSatisfactionResult]:
        """Evaluate satisfaction for every goal in the execution plan."""

    async def evaluate_goal(
        self,
        goal: Goal,
        state: AgentState,
    ) -> GoalSatisfactionResult:
        """
        Evaluate a single goal.

        Steps:
        1. Collect all evidence related to this goal
        2. Filter evidence to only this goal's module scope
        3. Compare against goal.success_criteria
        4. Compute weighted satisfaction score
        5. Determine verdict (SATISFIED | PARTIAL | UNSATISFIED | INCONCLUSIVE)
        6. Generate gap analysis and recommendations
        """

    async def collect_evidence(
        self, goal: Goal, state: AgentState
    ) -> list[SatisfactionEvidence]:
        """
        Gather all relevant evidence for this goal.

        Sources:
        - state.execution_summary (filtered by goal.module_scope)
        - state.test_results (filtered)
        - state.reflection_log (relevant stage evaluations)
        - state.confidence_gate_results (relevant stages)
        - state.stage_results (relevant stage outputs)
        """

    async def compute_satisfaction_score(
        self,
        goal: Goal,
        evidence: list[SatisfactionEvidence],
    ) -> tuple[SatisfactionResult, float]:
        """
        Compute weighted satisfaction score.

        score = Σ (evidence.value * evidence.source_weight)
              / Σ evidence.source_weight

        Map score to verdict:
        - score >= 0.90 → SATISFIED
        - score >= 0.60 → PARTIALLY
        - score < 0.60  → UNSATISFIED
        - insufficient evidence → INCONCLUSIVE
        """

    async def generate_gap_analysis(
        self,
        goal: Goal,
        evidence: list[SatisfactionEvidence],
        result: SatisfactionResult,
    ) -> list[str]:
        """
        Generate human-readable gap analysis.

        Example output:
        - "3 of 5 critical checkout scenarios executed (60%)"
        - "Payment gateway tests failed: insufficient mock data"
        - "Boundary testing missing for quantity field (0 scenarios)"
        """

    async def generate_recommendations(
        self,
        goal: Goal,
        gaps: list[str],
        result: SatisfactionResult,
    ) -> list[str]:
        """
        Generate actionable recommendations.

        Example output:
        - "Re-run with mock payment provider to cover gateway tests"
        - "Add boundary test scenarios for quantity field"
        - "Increase test data to cover edge cases in shipping module"
        """
```

### Satisfaction Scoring Formula

```
satisfaction_score = 
    (pass_rate                     * 0.30) +
    (critical_path_coverage        * 0.25) +   # were critical paths tested?
    (scenario_implementation_rate  * 0.15) +   # planned vs implemented
    (semantic_alignment_score      * 0.15) +   # from reflection evaluation
    (confidence_gate_pass_rate     * 0.10) +   # all gates for this goal's stages
    (human_review_approval_bonus   * 0.05)     # human said "approved" = 1.0

Modifiers:
    * upstream_goal_failure_penalty: -0.20 per failed upstream goal
    * evidence_insufficiency_penalty: -0.10 if < 3 evidence sources available
```

### Satisfaction Decision Matrix

```
┌─────────────────┬──────────────────────┬────────────────────────┐
│ SATISFACTION    │  SCORE               │  ACTION                │
├─────────────────┼──────────────────────┼────────────────────────┤
│ SATISFIED       │  >= 0.90             │ Mark complete, next    │
│ PARTIALLY       │  0.60 – 0.90         │ Report gaps, optional  │
│                 │                      │ replan for missing     │
│ UNSATISFIED     │  < 0.60              │ Replan or escalate     │
│ INCONCLUSIVE    │  < 3 evidence srcs   │ Flag for manual review │
└─────────────────┴──────────────────────┴────────────────────────┘
```

### Integration with Workflow

```python
async def goal_satisfaction_node(state: AgentState) -> AgentState:
    """
    Workflow node that runs after all execution and reporting is complete.

    Evaluates every goal, produces satisfaction verdicts, and decides:
    - Mark run as complete (all goals satisfied)
    - Mark run as partial (some goals partially met)
    - Trigger replan for unsatisfied goals
    """
    engine = get_goal_satisfaction_engine()

    results = await engine.evaluate_all_goals(state)

    for goal_id, result in results.items():
        state.satisfaction_results[goal_id] = result

    # Compute overall satisfaction
    all_results = list(results.values())
    if all(r.result == SatisfactionResult.SATISFIED for r in all_results):
        state.overall_satisfaction = SatisfactionResult.SATISFIED
    elif any(r.result == SatisfactionResult.UNSATISFIED for r in all_results):
        state.overall_satisfaction = SatisfactionResult.UNSATISFIED
    else:
        state.overall_satisfaction = SatisfactionResult.PARTIALLY

    state.satisfaction_evaluated_at = datetime.utcnow()

    # If any goal is unsatisfied and dynamic_replanning is enabled:
    unsatisfied = [r for r in all_results if r.result == SatisfactionResult.UNSATISFIED]
    if unsatisfied and state.execution_plan.dynamic_replanning:
        # Trigger replan for unsatisfied goals
        ...

    return state
```

---

# 9. ERROR RECOVERY

## 9.1 Design

```
Location: app/agent/recovery/recovery_engine.py
```

### Recovery Strategies

```
┌───────────────────────────────────────────────────────────────────────┐
│                       RECOVERY ENGINE                                 │
│                  app/agent/recovery/recovery_engine.py                │
├───────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  STRATEGY              DESCRIPTION              APPLIES TO            │
│  ────────────────────  ──────────────────────  ─────────────────────── │
│  RETRY                 Re-execute same stage   Transient failures     │
│                        with same inputs        (network, timeout)     │
│                                                                        │
│  RETRY_WITH_CONTEXT    Re-execute with         LLM errors,            │
│                        enriched error context  validation failures    │
│                                                                        │
│  RESUME                Continue from last      Any checkpointed       │
│                        completed stage         stage failure          │
│                                                                        │
│  ROLLBACK              Revert to previous      Data corruption,       │
│                        checkpoint version      bad crawl data         │
│                                                                        │
│  PARTIAL_COMPLETION    Accept partial results  Non-critical           │
│                        and continue            failures               │
│                                                                        │
│  STAGE_REPLAY          Replay entire stage     Credential errors,     │
│                        with modified params    scope changes          │
│                                                                        │
│  FAILURE_ISOLATION     Skip failed component   Single module/         │
│                        continue with rest      page failure           │
│                                                                        │
│  DEGRADED_MODE         Run with reduced        LLM unavailable,       │
│                        capabilities            browser crash          │
│                                                                        │
└───────────────────────────────────────────────────────────────────────┘
```

### Recovery Engine Interface

```python
class RecoveryEngine:
    """
    Manages failure recovery strategies.

    Integrates with:
    - AgentState (to read failure context and retry history)
    - Checkpoint system (to resume from last valid state)
    - Reflection Engine (to determine if retry is appropriate)
    - Execution Planner (to replan if needed)
    """

    async def handle_failure(
        self,
        state: AgentState,
        failed_stage: Stage,
        error: Exception,
        attempt: int,
    ) -> RecoveryAction:
        """
        Determine the best recovery strategy.

        Decision matrix:
        - attempt < max_retries AND error is transient → RETRY
        - attempt < max_retries AND error is LLM-related → RETRY_WITH_CONTEXT
        - attempt >= max_retries AND failed stage is critical → ABORT
        - attempt >= max_retries AND failed stage is optional → FAILURE_ISOLATION
        - workspace corrupted → ROLLBACK
        """

    async def retry_stage(
        self,
        state: AgentState,
        stage: Stage,
        error_context: Optional[dict] = None,
    ) -> AgentState:
        """Retry a specific stage with optional enriched context."""

    async def resume_from_checkpoint(
        self,
        state: AgentState,
        failed_stage: Stage,
    ) -> AgentState:
        """Resume workflow from the last successful checkpoint."""

    async def rollback_stage(
        self,
        state: AgentState,
        target_stage: Stage,
    ) -> AgentState:
        """Rollback AgentState to just before target_stage executed."""

    async def isolate_failure(
        self,
        state: AgentState,
        failed_component: str,
    ) -> AgentState:
        """Isolate a failed component and continue with remaining scope."""

    async def enter_degraded_mode(
        self,
        state: AgentState,
        unavailable_capability: str,
    ) -> AgentState:
        """Continue workflow with reduced capabilities."""


class RecoveryAction(BaseModel):
    strategy: RecoveryStrategy
    target_stage: Optional[Stage] = None
    modified_params: Optional[dict] = None
    skip_stages: list[Stage] = Field(default_factory=list)
    message: str
    requires_user_approval: bool = False
```

### Recovery Flow

```
STAGE FAILS
    │
    ├──► RecoveryEngine.handle_failure(state, stage, error, attempt)
    │       │
    │       ├──► attempt < max_retries?
    │       │    ├── YES → RETRY strategy
    │       │    │    ├── transient? → same params retry
    │       │    │    └── LLM error? → RETRY_WITH_CONTEXT (enriched error info)
    │       │    │
    │       │    └── NO → evaluate stage criticality
    │       │         ├── critical? → ABORT
    │       │         ├── optional? → FAILURE_ISOLATION or PARTIAL_COMPLETION
    │       │         └── infrastructure? → DEGRADED_MODE
    │       │
    │       └──► Execute recovery action
    │            ├── RETRY → re-run node_fn with original inputs
    │            ├── RETRY_WITH_CONTEXT → re-run with error_feedback in prompt
    │            ├── RESUME → load checkpoint, continue from next stage
    │            ├── ROLLBACK → restore state from backup, restart from
    │            │              rolled-back stage
    │            ├── PARTIAL_COMPLETION → mark stage complete with warnings,
    │            │                       continue to next
    │            └── FAILURE_ISOLATION → mark failed scope as excluded,
    │                                    continue with remaining
    │
    └──► Log recovery_action to AgentState.recovery_actions
```

---

# 10. ARTIFACT MANAGEMENT

## 10.1 Design

```
Location: app/agent/artifacts/artifact_registry.py
```

### Problem

Currently, file paths are passed between stages as raw strings:
```python
state.test_plan_path = f"{workspace_path}/contracts/test-plan.json"
state.approved_test_plan_path = f"{workspace_path}/contracts/approved-test-plan.json"
```

Problems:
- No centralized tracking
- No metadata (version, format, size, producer)
- No lifecycle management
- Hard to query ("show me all artifacts from code gen stage")
- No cleanup/archival
- Paths break on workspace migration

### Solution: Artifact Registry

```python
class ArtifactRegistry:
    """
    Centralized tracking of all artifacts produced during a run.

    Provides:
    - Unique artifact IDs
    - Metadata (type, stage, version, format, size, producer, timestamp)
    - Dependency tracking (which artifact was derived from which)
    - Lifecycle management (create → update → archive → delete)
    - Queryable by stage, type, dependency
    """

    async def register(
        self,
        run_id: UUID,
        artifact_type: ArtifactType,
        storage_path: str,
        metadata: dict[str, Any],
        depends_on: list[str] = None,  # artifact_ids this depends on
    ) -> str:
        """Register an artifact and return its ID."""

    async def get(self, artifact_id: str) -> ArtifactRecord:
        """Get artifact metadata (not content)."""

    async def get_content(self, artifact_id: str) -> bytes:
        """Read artifact content from storage."""

    async def get_by_stage(self, run_id: UUID, stage: Stage) -> list[ArtifactRecord]:
        """Get all artifacts produced by a stage."""

    async def get_by_type(self, run_id: UUID, artifact_type: ArtifactType) -> list[ArtifactRecord]:
        """Get all artifacts of a specific type."""

    async def get_latest(self, run_id: UUID, artifact_type: ArtifactType) -> Optional[ArtifactRecord]:
        """Get the latest version of an artifact type."""

    async def get_lineage(self, artifact_id: str) -> list[ArtifactRecord]:
        """Trace the full lineage (what produced this, what it produced)."""

    async def archive_run(self, run_id: UUID) -> None:
        """Archive all artifacts for a completed run."""

    async def cleanup_run(self, run_id: UUID) -> None:
        """Remove all artifacts for a run (with retention policy)."""


class ArtifactType(str, Enum):
    CRAWL_PACKAGE = "crawl_package"
    INVENTORY = "inventory"
    KNOWLEDGE_MODEL = "knowledge_model"
    SCREENSHOT = "screenshot"
    TEST_PLAN = "test_plan"
    APPROVED_TEST_PLAN = "approved_test_plan"
    REVIEW_METADATA = "review_metadata"
    CODE_GENERATION_IR = "code_generation_ir"
    DEPENDENCY_GRAPH = "dependency_graph"
    GENERATED_CODE = "generated_code"
    PAGE_OBJECT = "page_object"
    TEST_SPEC = "test_spec"
    FIXTURE = "fixture"
    PLAYWRIGHT_CONFIG = "playwright_config"
    EXECUTION_SUMMARY = "execution_summary"
    TEST_RESULT = "test_result"
    FAILURE_REPORT = "failure_report"
    METRICS_REPORT = "metrics_report"
    JUNIT_XML = "junit_xml"
    HTML_REPORT = "html_report"
    EXECUTION_LOG = "execution_log"
    TRACE_FILE = "trace_file"
    VIDEO = "video"
    DASHBOARD = "dashboard"
    CHECKPOINT = "checkpoint"
    CREDENTIALS = "credentials"
    PROMPT_LOG = "prompt_log"


class ArtifactRecord(BaseModel):
    id: str                              # UUID
    run_id: UUID
    artifact_type: ArtifactType
    storage_path: str                    # filesystem path or S3 key
    format: str                          # json | html | mp4 | png | ts | yaml
    size_bytes: int
    created_at: datetime
    stage: Stage                         # which stage produced it
    version: int                         # version number within run
    depends_on: list[str] = []           # artifact IDs this was derived from
    produced_by: list[str] = []          # artifact IDs derived from this
    metadata: dict[str, Any] = {}        # type-specific metadata
    checksum: Optional[str] = None       # SHA256 for integrity
    is_archived: bool = False
    retention_policy: str = "run"        # run | project | permanent
```

### Artifact Lineage Example

```
Crawl Package (artifact-001)
    │
    ├──► Screenshot (artifact-002) depends_on: [artifact-001]
    ├──► Screenshot (artifact-003) depends_on: [artifact-001]
    │
    └──► Inventory (artifact-004) depends_on: [artifact-001]
            │
            └──► Test Plan (artifact-005) depends_on: [artifact-004]
                    │
                    └──► Approved Test Plan (artifact-006) depends_on: [artifact-005]
                            │
                            └──► Code Generation IR (artifact-007) depends_on: [artifact-006]
                                    │
                                    ├──► Page Object (artifact-008) depends_on: [artifact-007]
                                    ├──► Test Spec (artifact-009) depends_on: [artifact-007]
                                    └──► Test Spec (artifact-010) depends_on: [artifact-007]
                                            │
                                            └──► Execution Report (artifact-011) depends_on: [artifact-008..010]
```

### Integration with AgentState

In `AgentState`, raw file paths are replaced by artifact references:

```python
# OLD:
state.test_plan_path = f"{workspace}/contracts/test-plan.json"

# NEW:
artifact_id = await registry.register(run_id, ArtifactType.TEST_PLAN, path, metadata)
state.test_plan_ref = artifact_id
```

All downstream stages use `registry.get(artifact_id)` to resolve content.

---

# 11. IMPLEMENTATION STRATEGY

## 11.1 Migration Philosophy

**INCREMENTAL — NEVER BREAK EXISTING FUNCTIONALITY**

The migration follows the **Strangler Fig Pattern**:
1. New components are built alongside existing ones
2. Existing stages are progressively wrapped with agentic behavior
3. Old paths remain functional until new paths are proven
4. Feature flags control which code path is active
5. Every phase is independently testable and reversible

## 11.2 Migration Roadmap

```
PHASE 0: Foundation (Week 1-2)
├── AgentState model definition
├── ArtifactRegistry implementation
├── ContextManager skeleton
└── Feature flag system

PHASE 1: Critical — Core Agent (Week 3-5)
├── Intent Engine (hybrid parser)
├── Execution Planner
├── ContextManager (full)
├── Agentic stage wrappers
├── Backward compatibility layer
└── Integration tests

PHASE 2: Intelligence (Week 6-8)
├── Knowledge Model + Builder
├── Memory Manager (all layers)
├── Reflection Engine
├── Recovery Engine
└── Learning Memory

PHASE 3: Optimization (Week 9-10)
├── Parallel execution groups
├── Intelligent retry with learning
├── Cross-run knowledge reuse
├── Performance optimization
└── Production hardening
```

## 11.3 Post-Migration Target Architecture

After all phases, the architecture transforms from:

```
OLD:
  Prompt → Parser(regex) → Sequential Pipeline (7 stages) → Report
  [stages operate independently, no shared context, no goals]

NEW (v1.1):
  Prompt → Intent Understanding(hybrid)
       → Ambiguity Check → Clarification Loop (if needed)
       → Execution Planner (Goal → Task → Subtask → Action)
       → Capability Registry Lookup
       → Tool Selection Layer (best tool per task)
       → AgentState (centralized, goal-aware)
       → Workflow Orch(wrapped stages)
       → Confidence Gates (threshold checks after every stage)
       → Context Manager + Memory + Reflection + Recovery
       → Goal Satisfaction Engine (evidence-based evaluation)
       → Business-objective-aware Reporting
  [all stages share AgentState, understand goals, select tools dynamically,
   clarify ambiguity, verify satisfaction with evidence, learn from failures]
```

---

# 12. PHASE-BY-PHASE FILE PLAN

## Phase 0: Foundation

```
CREATE:
  app/agent/__init__.py                          # Agent module init
  app/agent/state.py                              # AgentState, UnifiedIntent, Goal, etc.
  app/agent/artifacts/__init__.py
  app/agent/artifacts/artifact_registry.py        # ArtifactRegistry
  app/agent/artifacts/registry_backend.py         # Storage backend (local/S3)
  app/agent/config.py                             # Feature flags, agent configuration
  tests/unit/test_agent_state.py                  # AgentState serialization tests
  tests/unit/test_artifact_registry.py            # ArtifactRegistry tests

MODIFY:
  app/core/interfaces.py                          # Add IAgenticStage interface
  app/graph/state.py                              # Add LegacyStateAdapter
  app/config/settings.py                          # Add agent feature flags section

NO BREAKING CHANGES. Existing pipeline runs unchanged.
```

## Phase 1: Core Agent

```
CREATE:
  app/agent/intent/__init__.py
  app/agent/intent/intent_engine.py                # IntentEngine (LLM-based)
  app/agent/intent/unified_intent_builder.py       # Merge deterministic + semantic
  app/agent/intent/intent_validator.py             # UnifiedIntent validation
  app/agent/intent/ambiguity_detector.py           # Ambiguity dimension scoring   ◄── NEW v1.1
  app/agent/intent/clarification_loop.py           # Clarification orchestrator     ◄── NEW v1.1
  app/agent/intent/clarification_question_gen.py   # Question generator (LLM)       ◄── NEW v1.1
  app/agent/intent/prompts/intent_engine_system.md
  app/agent/intent/prompts/clarification_prompt.md # Clarification question prompt  ◄── NEW v1.1

  app/agent/planner/__init__.py
  app/agent/planner/execution_planner.py           # Goal Decomposer, Task Scheduler
  app/agent/planner/goal_decomposer.py             # Intent → Goals hierarchy
  app/agent/planner/task_scheduler.py              # Goals → Stage DAG
  app/agent/planner/task_hierarchy.py              # Goal→Task→Subtask→Action       ◄── NEW v1.1
  app/agent/planner/constraint_validator.py        # Plan validation
  app/agent/planner/dependency_resolver.py         # Stage dependency resolution

  app/agent/registry/__init__.py                                               ◄── NEW v1.1
  app/agent/registry/capability_registry.py        # Capability catalog          ◄── NEW v1.1
  app/agent/registry/capability_health.py          # Health check endpoint       ◄── NEW v1.1

  app/agent/selection/__init__.py                                             ◄── NEW v1.1
  app/agent/selection/tool_selection.py            # Tool scoring & selection    ◄── NEW v1.1
  app/agent/selection/tool_scoring.py              # Scoring algorithm           ◄── NEW v1.1

  app/agent/context/__init__.py
  app/agent/context/context_manager.py             # Full ContextManager
  app/agent/context/context_injector.py            # Per-stage context injection
  app/agent/context/context_validator.py           # Required fields validation
  app/agent/context/context_snapshot.py            # ContextFrame creation

  app/agent/gates/__init__.py                                                  ◄── NEW v1.1
  app/agent/gates/confidence_gates.py              # ConfidenceGateEngine        ◄── NEW v1.1
  app/agent/gates/gate_configs.py                  # Default gate configurations ◄── NEW v1.1

  app/agent/satisfaction/__init__.py                                           ◄── NEW v1.1
  app/agent/satisfaction/goal_satisfaction.py      # GoalSatisfactionEngine      ◄── NEW v1.1
  app/agent/satisfaction/evidence_collector.py     # Evidence gathering          ◄── NEW v1.1

  app/agent/orchestrator.py                        # AgenticStageWrapper
  app/agent/adapter.py                             # LegacyStateAdapter

  app/schemas/intent.py                            # Pydantic schemas for UnifiedIntent
  app/schemas/plan.py                              # Pydantic schemas for ExecutionPlan
  app/schemas/clarification.py                     # Clarification question schemas    ◄── NEW v1.1
  app/schemas/capability.py                        # CapabilityEntry schemas           ◄── NEW v1.1
  app/schemas/gates.py                             # ConfidenceGate schemas            ◄── NEW v1.1
  app/schemas/satisfaction.py                      # Satisfaction schemas              ◄── NEW v1.1

  tests/unit/test_intent_engine.py
  tests/unit/test_execution_planner.py
  tests/unit/test_context_manager.py
  tests/unit/test_clarification_loop.py                                         ◄── NEW v1.1
  tests/unit/test_task_hierarchy.py                                             ◄── NEW v1.1
  tests/unit/test_capability_registry.py                                       ◄── NEW v1.1
  tests/unit/test_tool_selection.py                                            ◄── NEW v1.1
  tests/unit/test_confidence_gates.py                                          ◄── NEW v1.1
  tests/unit/test_goal_satisfaction.py                                         ◄── NEW v1.1
  tests/integration/test_agentic_workflow.py
  tests/integration/test_clarification_workflow.py                              ◄── NEW v1.1

MODIFY:
  app/workflows/trigger_workflow.py                # Add agentic stage wrapper calls
  app/services/prompt_builder.py                   # Use ParsePhase from config, add IntentEngine fallback
  app/api/routes/trigger.py                        # Add intent analysis + clarification endpoints
  app/api/routes/workflow.py                       # Add satisfaction results endpoint
  app/dependencies.py                              # Register new agent components

BACKWARD COMPATIBILITY:
  Feature flag: AGENT_MODE_ENABLED = false (default)
  When false: existing pipeline runs exactly as today
  When true: new agentic pipeline with all v1.1 components
```

## Phase 2: Intelligence

```
CREATE:
  app/agent/knowledge/__init__.py
  app/agent/knowledge/knowledge_builder.py         # Inventory → KnowledgeModel
  app/agent/knowledge/knowledge_validator.py       # Model validation
  app/agent/knowledge/flow_inferrer.py             # UserFlow inference from navigation

  app/agent/memory/__init__.py
  app/agent/memory/memory_manager.py               # Unified memory access
  app/agent/memory/short_term_memory.py            # In-memory + disk
  app/agent/memory/long_term_memory.py             # Cross-run knowledge
  app/agent/memory/historical_memory.py            # PG-based trends
  app/agent/memory/learning_memory.py              # PG + pgvector embeddings

  app/agent/reflection/__init__.py
  app/agent/reflection/reflection_engine.py        # Core reflection
  app/agent/reflection/evaluators/crawler_evaluator.py
  app/agent/reflection/evaluators/test_design_evaluator.py
  app/agent/reflection/evaluators/code_generation_evaluator.py
  app/agent/reflection/evaluators/execution_evaluator.py
  app/agent/reflection/evaluators/reporting_evaluator.py

  app/agent/recovery/__init__.py
  app/agent/recovery/recovery_engine.py            # Core recovery
  app/agent/recovery/strategies/retry_strategy.py
  app/agent/recovery/strategies/rollback_strategy.py
  app/agent/recovery/strategies/isolation_strategy.py
  app/agent/recovery/strategies/degraded_strategy.py

  app/models/orm/agent.py                          # Agent-specific ORM models
  app/schemas/memory.py                            # Memory schemas
  app/schemas/reflection.py                        # Reflection schemas

  tests/unit/test_knowledge_builder.py
  tests/unit/test_memory_manager.py
  tests/unit/test_reflection_engine.py
  tests/unit/test_recovery_engine.py
  tests/integration/test_reflection_workflow.py

MODIFY:
  app/workflows/trigger_workflow.py                # Add reflection gates after stages
  app/agents/crawler_agent.py                      # Wire to Reflection + KnowledgeModel
  app/agents/test_design_agent.py                  # Wire to Reflection + Context
  app/agents/code_generation_agent.py              # Wire to Reflection
  app/agents/execution_agent.py                    # Wire to Reflection
  app/services/inventory_aggregator_service.py     # Wire to KnowledgeBuilder
  app/models/orm/system.py                         # Add learning/memory tables
  alembic/versions/                                # New migration for agent tables
```

## Phase 3: Optimization

```
CREATE:
  app/agent/optimization/parallel_executor.py      # Parallel stage execution
  app/agent/optimization/intelligent_retry.py      # Learning-based retry
  app/agent/optimization/knowledge_reuse.py        # Cross-run knowledge reuse
  app/agent/optimization/cost_optimizer.py         # LLM cost management

MODIFY:
  app/agent/planner/execution_planner.py           # Parallel group support
  app/agent/recovery/recovery_engine.py            # Learning integration
  app/workflows/trigger_workflow.py                # Parallel execution support
```

---

# 13. RISK ANALYSIS

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| LLM IntentEngine produces wrong goals | Medium | High | Regex fallback, confidence threshold, user confirmation for low confidence |
| Clarification loop annoys users with too many questions | Medium | High | Max 3 rounds, multi-choice defaults, per-dimension confidence threshold, async mode |
| Tool selection picks suboptimal agent | Low | Medium | Fallback tools, scoring transparency, manual override option, LearningMemory feedback |
| Capability registry becomes stale | Low | Medium | Health checks on every query, TTL-based cache invalidation, self-healing on tool failure |
| Confidence gates too strict → pipeline never completes | Medium | High | Soft gate option, user-configurable thresholds, auto-retry before abort |
| Goal satisfaction produces false positives | Medium | High | Evidence-weighting, multiple sources required, inconclusive verdict when evidence sparse |
| Task hierarchy too granular → overhead dominates work | Low | Low | Configurable granularity (coarse=Stage, fine=Action), auto-collapse small tasks |
| AgentState grows too large in memory | Low | Medium | Lazy loading of artifact content, pydantic exclude on large fields |
| Reflection causes infinite replan loops | Low | High | Max replan count (3), timeout, human review gate |
| ContextManager adds latency | Medium | Low | Async context loading, parallel context assembly |
| Knowledge model builder corrupts relationships | Medium | Medium | Validation layer, integrity checks on every relationship |
| Migration breaks existing API | Low | Critical | Feature flags, comprehensive regression suite, backward compat for 2 versions |
| Learning memory embedding costs | Low | Low | Optional (behind feature flag), batch processing |
| Parallel execution race conditions | Medium | Medium | AgentState locks, stage dependency enforcement, atomic writes |
| PostgreSQL dependency for Phase 2 | Low | Medium | All memory layers have file-based fallback, PG is optional |
| Frontend needs major refactor | Medium | High | New SSE event types are additive, Zustand store extended not replaced |

---

# 14. DATABASE CHANGES

## Phase 0: No DB changes

## Phase 1: New columns

```sql
-- Existing tables get new columns (backward compat — defaults allow old code)
ALTER TABLE runs ADD COLUMN IF NOT EXISTS unified_intent JSONB;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS execution_plan JSONB;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS agent_mode BOOLEAN DEFAULT FALSE;
ALTER TABLE runs ADD COLUMN IF NOT EXISTS plan_version INTEGER DEFAULT 1;
```

## Phase 2: New tables

```sql
CREATE TABLE agent_goals (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES runs(run_id) ON DELETE CASCADE,
    goal_data JSONB NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE TABLE reflection_records (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES runs(run_id) ON DELETE CASCADE,
    stage VARCHAR(50) NOT NULL,
    passed BOOLEAN NOT NULL,
    evaluation TEXT,
    issues JSONB,
    recommendations JSONB,
    replan_triggered BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE knowledge_models (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    model_data JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE run_summaries (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES runs(run_id) ON DELETE CASCADE,
    project_id UUID REFERENCES projects(id),
    summary_data JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE learning_entries (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES runs(run_id),
    category VARCHAR(50) NOT NULL,
    context TEXT,
    observation TEXT,
    action_taken TEXT,
    outcome TEXT,
    embedding VECTOR(1536),  -- pgvector extension
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE recovery_actions (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES runs(run_id),
    failed_stage VARCHAR(50) NOT NULL,
    error_message TEXT,
    strategy VARCHAR(50) NOT NULL,
    result VARCHAR(20),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE artifact_registry (
    id UUID PRIMARY KEY,
    run_id UUID REFERENCES runs(run_id) ON DELETE CASCADE,
    artifact_type VARCHAR(50) NOT NULL,
    storage_path TEXT NOT NULL,
    format VARCHAR(20),
    size_bytes BIGINT,
    stage VARCHAR(50),
    version INTEGER DEFAULT 1,
    depends_on UUID[],
    checksum VARCHAR(64),
    is_archived BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

---

# 15. API CHANGES

## Phase 1: New endpoints (additive)

```
POST   /api/v1/runs/{id}/intent         — Get/refresh semantic intent analysis
GET    /api/v1/runs/{id}/ambiguity       — Get ambiguity dimensions and scores               ◄── NEW v1.1
POST   /api/v1/runs/{id}/clarify         — Submit clarification response                     ◄── NEW v1.1
GET    /api/v1/runs/{id}/clarification   — Get pending clarification question                ◄── NEW v1.1
GET    /api/v1/runs/{id}/plan            — Get execution plan + goal status + task hierarchy
POST   /api/v1/runs/{id}/replan         — Trigger dynamic replanning
GET    /api/v1/runs/{id}/context         — Get full context snapshot for any stage
GET    /api/v1/runs/{id}/capabilities    — Get available capabilities for this run           ◄── NEW v1.1
GET    /api/v1/runs/{id}/tool-selections — Get task→tool mapping                             ◄── NEW v1.1
GET    /api/v1/runs/{id}/gates           — Get confidence gate results for all stages        ◄── NEW v1.1
GET    /api/v1/runs/{id}/satisfaction    — Get goal satisfaction results                     ◄── NEW v1.1
POST   /api/v1/runs/{id}/reflect         — Trigger manual reflection on current stage
```

## Phase 2: New endpoints

```
GET    /api/v1/runs/{id}/knowledge       — Get knowledge model for current run
GET    /api/v1/projects/{id}/knowledge   — Get project knowledge model (cross-run)
GET    /api/v1/runs/{id}/memory          — Get memory references for run
GET    /api/v1/runs/{id}/reflections     — Get reflection log
POST   /api/v1/runs/{id}/recovery/{strategy} — Trigger specific recovery strategy
GET    /api/v1/runs/{id}/artifacts       — List artifacts with metadata
GET    /api/v1/runs/{id}/artifacts/{id}  — Get artifact content
```

---

# 16. FEATURE FLAGS

```python
# app/agent/config.py

class AgentFeatureFlags(BaseModel):
    # Phase 0
    agent_mode_enabled: bool = False             # Master switch
    artifact_registry_enabled: bool = False      # Use ArtifactRegistry instead of raw paths

    # Phase 1
    intent_engine_enabled: bool = False          # Use LLM IntentEngine (else regex-only)
    clarification_loop_enabled: bool = False     # Enable clarification for low-confidence intent ◄── NEW v1.1
    execution_planner_enabled: bool = False      # Use ExecutionPlanner (else linear sequence)
    task_hierarchy_enabled: bool = False         # Goal→Task→Subtask→Action decomposition    ◄── NEW v1.1
    capability_registry_enabled: bool = False    # Capability catalog + health checks         ◄── NEW v1.1
    tool_selection_enabled: bool = False         # Dynamic tool selection per task            ◄── NEW v1.1
    context_manager_enabled: bool = False        # Use ContextManager (else raw state)
    confidence_gates_enabled: bool = False       # Threshold checks after every stage         ◄── NEW v1.1
    goal_satisfaction_enabled: bool = False      # Evidence-based goal evaluation             ◄── NEW v1.1

    # Phase 2
    knowledge_model_enabled: bool = False        # Build KnowledgeModel from inventory
    memory_manager_enabled: bool = False         # Use MemoryManager (else ephemeral)
    reflection_enabled: bool = False             # Reflection gates after stages
    recovery_engine_enabled: bool = False        # Advanced recovery strategies

    # Phase 3
    parallel_execution_enabled: bool = False     # Parallel stage groups
    learning_enabled: bool = False               # Cross-run learning
    knowledge_reuse_enabled: bool = False        # Reuse knowledge across runs
    cost_optimization_enabled: bool = False      # LLM cost management
```

---

# 17. TESTING STRATEGY

## Unit Tests (per phase)

```
tests/unit/
  test_agent_state.py              — Serialization, mutation, helper methods
  test_intent_engine.py            — Prompt construction, parsing, fallback
  test_execution_planner.py        — Goal decomposition, DAG generation
  test_context_manager.py          — Inject, validate, snapshot
  test_knowledge_builder.py        — Inventory → KnowledgeModel conversion
  test_memory_manager.py           — All memory layers
  test_reflection_engine.py        — All evaluators
  test_recovery_engine.py          — All strategies
  test_artifact_registry.py        — Register, query, lineage
```

## Integration Tests

```
tests/integration/
  test_agentic_workflow.py         — Full agent pipeline with all Phase 1 features
  test_reflection_workflow.py      — Reflection-triggered replanning
  test_recovery_workflow.py        — Failure → recovery → resume
  test_backward_compat.py          — Feature flags off = old behavior unchanged
  test_dual_mode.py                — Mixed flag states
```

## Regression Tests

All existing tests (`tests/test_*.py`) must pass with `AGENT_MODE_ENABLED=false`.

---

# 18. ROLLBACK STRATEGY

Each phase introduces a feature flag. Rollback is: **set flag to false**.

```
Phase 0:  agent_mode_enabled = false          → no agentic behavior, all new code bypassed
Phase 1:  intent_engine_enabled = false       → fall back to regex-only PromptParser
          clarification_loop_enabled = false  → skip clarification, proceed with raw intent    ◄── NEW
          execution_planner_enabled = false   → fall back to linear stage sequence
          task_hierarchy_enabled = false      → use coarse Goal→Stage mapping                  ◄── NEW
          capability_registry_enabled = false → use hardcoded DI resolution                    ◄── NEW
          tool_selection_enabled = false      → use hardcoded stage→agent mapping              ◄── NEW
          confidence_gates_enabled = false    → skip threshold checks after stages             ◄── NEW
          goal_satisfaction_enabled = false   → mark goal complete when stage succeeds         ◄── NEW
Phase 2:  reflection_enabled = false          → skip reflection gates
          recovery_engine_enabled = false     → use simple retry (current behavior)
Phase 3:  parallel_execution_enabled = false  → sequential execution
```

Database migrations are additive (new columns, new tables) — no destructive changes. Rollback does not require DB rollback.

---

# 19. ESTIMATED IMPLEMENTATION ORDER

```
Priority  Component                    Complexity   Dependencies              Risk
─────     ──────────                  ──────────   ─────────────             ────
P0        AgentState model            Low          None                      Low
P0        Feature flag system         Low          None                      Low
P0        ArtifactRegistry            Medium       AgentState                Low
P1        LegacyStateAdapter          Low          AgentState                Low
P1        CapabilityRegistry          Medium       AgentState                Low           ◄── NEW v1.1
P1        IntentEngine + unified      Medium       AgentState                Medium
P1        AmbiguityDetector           Low          IntentEngine, AgentState  Low            ◄── NEW v1.1
P1        ClarificationLoop           Medium       AmbiguityDetector         Medium         ◄── NEW v1.1
P1        ExecutionPlanner            High         UnifiedIntent             Medium
P1        TaskHierarchy               Medium       ExecutionPlanner          Medium         ◄── NEW v1.1
P1        ToolSelection               Medium       CapabilityRegistry,Tasks  Medium         ◄── NEW v1.1
P1        ConfidenceGates             Medium       AgentState                Low            ◄── NEW v1.1
P1        ContextManager              Medium       AgentState                Low
P1        Agentic stage wrappers      Medium       ContextManager,Gates      Low
P1        GoalSatisfaction            Medium       AgentState,Gates,Reflect  Medium         ◄── NEW v1.1
P1        Workflow node wrapping      High         All above                 High
P2        Knowledge builder           Medium       ArtifactRegistry          Low
P2        Memory manager              High         KnowledgeModel            Medium
P2        Reflection engine           High         AgentState                High
P2        Recovery engine             High         ReflectionEngine          High
P2        Learning memory             Medium       MemoryManager             Medium
P3        Parallel executor           High         ExecutionPlanner          High
P3        Intelligent retry           Medium       LearningMemory            Medium
P3        Knowledge reuse             Medium       KnowledgeModel            Medium
P0        Tests (all phases)          Continuous   Respective phase          Low
```

---

# 20. SUMMARY

| What | Current | Target |
|------|---------|--------|
| Intent Parsing | Regex only | Hybrid (regex + LLM) |
| Ambiguity Handling | None (assumes correct) | Clarification loop with targeted questions | ◄── NEW v1.1
| Planning | None (linear stages) | DAG-based Execution Planner |
| Task Granularity | Goal → Stage (coarse) | Goal → Task → Subtask → Action (fine) | ◄── NEW v1.1
| State | Flat per-stage fields | Centralized AgentState |
| Tool Selection | Hardcoded per stage | Dynamic scoring + capability matching | ◄── NEW v1.1
| Capability Awareness | Implicit (DI container) | Centralized CapabilityRegistry with health checks | ◄── NEW v1.1
| Context | Lost between stages | Guaranteed by ContextManager |
| Knowledge | Flat JSON inventory | Structured KnowledgeModel |
| Memory | None | 5-layer memory architecture |
| Reflection | None | Gates after every major stage |
| Quality Gates | None (stage completed = good) | Confidence gates after every stage | ◄── NEW v1.1
| Goal Evaluation | Stage success = goal met | Evidence-based Goal Satisfaction Engine | ◄── NEW v1.1
| Recovery | Simple checkpoint/retry | 5-strategy Recovery Engine |
| Artifacts | Raw file paths | Centralized ArtifactRegistry |
| Reporting | Execution results only | Business-objective-aware |
| Learning | None | Cross-run pattern learning |

**Migration approach:** Incremental, feature-flagged, never breaking existing functionality. Each phase builds on the previous, and every phase can be toggled on/off independently.

**This document constitutes the complete architectural design. No code should be written until this design is reviewed and approved.**

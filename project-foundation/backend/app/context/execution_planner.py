"""
Execution Planner — user prompt → structured execution plan

Translates the user's intent into a reviewable execution plan:

    Goal → Tasks → Subtasks → Dependencies → Execution Order → Tool Selection

The planner is deterministic (no LLM) so it is fast, cheap, and always
available. When the ``intent_engine_enabled`` flag is on, richer fields
(goal, priorities, business objective, success criteria) extracted by the
Hybrid Intent Parser are layered on top. Stage ordering always matches the
existing linear workflow, so enabling the planner never re-orders stages.

Phase 2.5 extensions:
- SubTask model for atomic execution items
- Tool selection (capability routing per task)
- Clarification loop (NeedsClarification on ambiguity)
- Dynamic replanning (append discovered tasks, revision history)
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.logging import LoggerMixin

# ---------------------------------------------------------------------------
# Stage / capability registry
# ---------------------------------------------------------------------------

STAGE_ORDER: list[str] = [
    "trigger",
    "crawler",
    "inventory_aggregator",
    "test_design",
    "human_review",
    "code_generation",
    "execution",
]

_STAGE_LABELS: dict[str, str] = {
    "trigger": "Project Setup",
    "crawler": "Crawl Application",
    "inventory_aggregator": "Generate Inventory",
    "test_design": "Design Test Plan",
    "human_review": "Human Review",
    "code_generation": "Generate Tests",
    "execution": "Execute Tests",
}

_STAGE_DESCRIPTIONS: dict[str, str] = {
    "trigger": "Initialise workspace, validate target URL, prepare run metadata.",
    "crawler": "Crawl the application within the resolved scope and capture pages, forms, and navigation.",
    "inventory_aggregator": "Aggregate crawled data into a canonical application inventory.",
    "test_design": "Generate a structured, priority-ranked test plan from the inventory and user intent.",
    "human_review": "Present the test plan for human approval before any code is generated.",
    "code_generation": "Generate the Playwright project from the approved test plan using the IR pipeline.",
    "execution": "Run the generated tests and produce reports.",
}

# Phase 2.5: capability → workflow stage mapping
_CAPABILITY_STAGE: dict[str, str] = {
    "open_page": "crawler",
    "navigate": "crawler",
    "discover": "crawler",
    "capture_screenshot": "crawler",
    "extract_forms": "crawler",
    "aggregate_inventory": "inventory_aggregator",
    "analyse_structure": "test_design",
    "design_scenarios": "test_design",
    "generate_playwright": "code_generation",
    "generate_page_objects": "code_generation",
    "generate_tests": "code_generation",
    "validate_code": "code_generation",
    "execute_tests": "execution",
    "collect_results": "execution",
    "generate_report": "execution",
    "human_review": "human_review",
    "initialise_workspace": "trigger",
}

# Phase 2.5: ambiguous module names that trigger clarification
_AMBIGUOUS_CLUSTERS: dict[str, list[str]] = {
    "HR": ["HR Dashboard", "HR Payroll", "HR Recruitment", "HR Onboarding", "HR Benefits"],
    "Admin": ["Admin Panel", "Admin Settings", "Admin Users", "Admin Audit"],
    "Reports": ["Sales Reports", "Audit Reports", "User Reports", "System Reports"],
    "Settings": ["Account Settings", "App Settings", "Security Settings"],
    "Dashboard": ["Main Dashboard", "Analytics Dashboard", "Admin Dashboard"],
    "Users": ["User Management", "User Profile", "User Permissions"],
}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class SubTask(BaseModel):
    """An atomic execution item within a task (Phase 2.5)."""

    id: str = Field(..., description="Unique subtask id (e.g. st-login-1)")
    description: str = Field(..., description="What this subtask does")
    capability: str = Field(default="", description="Tool/capability that executes this subtask (e.g. open_page, generate_tests)")
    stage: str = Field(default="", description="Workflow stage this maps to")
    depends_on: list[str] = Field(default_factory=list, description="Subtask ids that must complete first")
    status: str = Field(default="pending", description="pending | running | completed | skipped | failed | blocked")
    discovered: bool = Field(default=False, description="Whether this was added by dynamic replanning")


class ExecutionTask(BaseModel):
    """A single stage in the execution plan (extended in Phase 2.5)."""

    name: str = Field(..., description="Task name (stage label)")
    stage: str = Field(..., description="Stage identifier (matches workflow node)")
    order: int = Field(..., description="Execution order (1-based)")
    description: str = Field(default="", description="What the task does")
    depends_on: list[str] = Field(default_factory=list, description="Stages that must complete first")
    status: str = Field(default="pending", description="pending | running | completed | skipped | failed")
    capability: str = Field(default="", description="Primary tool/capability for this task (Phase 2.5)")
    subtasks: list[SubTask] = Field(default_factory=list, description="Atomic execution items (Phase 2.5)")


class ClarificationNeeded(BaseModel):
    """Structured clarification request when intent is ambiguous (Phase 2.5)."""

    message: str = Field(..., description="Human-readable explanation of the ambiguity")
    ambiguous_term: str = Field("", description="The term that caused the ambiguity")
    options: list[str] = Field(default_factory=list, description="Possible resolutions the user can choose from")
    confidence: float = Field(default=0.0, description="Parser confidence that triggered this (0.0–1.0)")
    recommended: str | None = Field(None, description="Suggested option (first in list)")


class ExecutionPlan(BaseModel):
    """
    Reviewable execution plan derived from the user prompt.

    Phase 2.5 extensions:
    - ``clarification_needed``: set when the planner detects ambiguity
    - ``revisions``: list of previous plan snapshots (dynamic replanning history)
    - Tasks now carry ``subtasks`` and ``capability``
    """

    goal: str | None = Field(None, description="High-level goal statement")
    tasks: list[ExecutionTask] = Field(default_factory=list, description="Ordered tasks with subtasks")
    execution_order: list[str] = Field(default_factory=list, description="Stage ids in execution order")
    workflow_scope: dict[str, Any] = Field(
        default_factory=dict,
        description="Included/excluded modules and pages, coverage and output preferences",
    )
    constraints: list[str] = Field(default_factory=list, description="Scope/authority constraints")
    success_criteria: list[str] = Field(default_factory=list, description="Conditions for a successful run")
    source_prompt: str | None = Field(None, description="Original user prompt (preserved)")
    clarification_needed: ClarificationNeeded | None = Field(
        None, description="Non-None means execution must pause for user clarification (Phase 2.5)"
    )
    revisions: list[dict[str, Any]] = Field(
        default_factory=list, description="History of previous ExecutionPlan snapshots (Phase 2.5)"
    )

    # Phase 4: reasoning enrichment (backward-compatible — all optional)
    business_intent: dict[str, Any] = Field(
        default_factory=dict, description="Business-level intent from ReasoningEngine"
    )
    workflow_intent: dict[str, Any] = Field(
        default_factory=dict, description="Multi-step workflow understanding"
    )
    reasoning_summary: str | None = Field(
        None, description="One-line summary of what the ReasoningEngine concluded"
    )
    decision_history: list[dict[str, Any]] = Field(
        default_factory=list, description="Decisions made by the DecisionEngine"
    )
    stopping_conditions: list[str] = Field(
        default_factory=list, description="Conditions that halt execution"
    )
    completion_criteria: list[dict[str, Any]] = Field(
        default_factory=list, description="Evaluable completion criteria inferred from user intent"
    )
    expected_state_graph: dict[str, Any] = Field(
        default_factory=dict,
        description="Dynamic ExpectedStateGraph — the authoritative completion contract derived from intent",
    )
    priority_model: dict[str, Any] = Field(
        default_factory=dict, description="Priority model from execution strategy"
    )
    risk_assessment: dict[str, Any] = Field(
        default_factory=dict, description="Risk level and mitigations"
    )
    execution_strategy: dict[str, Any] = Field(
        default_factory=dict, description="How the agent should execute (sequential/parallel/conditional)"
    )
    reasoning_trace: dict[str, Any] = Field(
        default_factory=dict, description="Debug-only reasoning trace summary"
    )

    def to_serializable(self) -> dict[str, Any]:
        """Serialise to a plain dict for transport/persistence."""
        return self.model_dump(mode="json")

    def enrich_from_reasoning(self, reasoning_result: Any) -> None:
        """
        Phase 4: apply ReasoningResult to this plan.

        Args:
            reasoning_result: ``app.reasoning.models.ReasoningResult``
        """
        rr = reasoning_result
        self.reasoning_summary = getattr(rr, "detected_intent", None)
        self.business_intent = getattr(rr, "business_intent", None).model_dump(mode="json") if getattr(rr, "business_intent", None) else {}
        self.workflow_intent = getattr(rr, "workflow_intent", None).model_dump(mode="json") if getattr(rr, "workflow_intent", None) else {}
        self.execution_strategy = getattr(rr, "execution_strategy", None).model_dump(mode="json") if getattr(rr, "execution_strategy", None) else {}
        self.stopping_conditions = list(getattr(rr, "execution_strategy", None).stopping_conditions if getattr(rr, "execution_strategy", None) else [])

        raw_cc = getattr(rr, "completion_criteria", []) or []
        self.completion_criteria = [
            c.model_dump(mode="json") if hasattr(c, "model_dump") else c
            for c in raw_cc
        ]

        raw_graph = getattr(rr, "expected_state_graph", None) or {}
        if isinstance(raw_graph, dict):
            self.expected_state_graph = raw_graph
        elif hasattr(raw_graph, "model_dump"):
            self.expected_state_graph = raw_graph.model_dump(mode="json")
        else:
            self.expected_state_graph = {}

        self.risk_assessment = {"level": getattr(getattr(rr, "business_intent", None), "risk_level", "medium")}
        self.priority_model = {"ordering": list(getattr(rr, "execution_strategy", None).priority_ordering if getattr(rr, "execution_strategy", None) else [])}

        # Merge constraints from reasoning into plan constraints
        for c in getattr(rr, "constraints", []) or []:
            existing = self.workflow_scope.get("__reasoning_constraints__", [])
            existing.append({"type": getattr(c, "type", ""), "description": getattr(c, "description", ""), "severity": getattr(c, "severity", "")})
            self.workflow_scope["__reasoning_constraints__"] = existing

    def snapshot_revision(self) -> None:
        """Record current plan state before modification (dynamic replanning)."""
        self.revisions.append(self.model_dump(mode="json"))
        if len(self.revisions) > 10:
            self.revisions = self.revisions[-10:]

    def append_task(self, task: ExecutionTask) -> None:
        """Append a discovered task (dynamic replanning)."""
        task.order = max((t.order for t in self.tasks), default=0) + 1
        task.subtasks = [st.model_copy(update={"discovered": True}) for st in task.subtasks]
        self.tasks.append(task)
        self.execution_order.append(task.stage)

    def update_task_status(self, stage: str, status: str) -> None:
        """Update status of a task by stage name."""
        for task in self.tasks:
            if task.stage == stage:
                task.status = status
                return

    def tasks_by_status(self, status: str) -> list[ExecutionTask]:
        return [t for t in self.tasks if t.status == status]

    def all_subtasks(self) -> list[SubTask]:
        return [st for task in self.tasks for st in task.subtasks]


# ---------------------------------------------------------------------------
# Planner
# ---------------------------------------------------------------------------

class ExecutionPlanner(LoggerMixin):
    """
    Builds :class:`ExecutionPlan` from intent.

    Phase 2.5 capabilities:
    - Task decomposition into subtasks with dependencies
    - Tool selection (capability routing per task)
    - Clarification detection (ambiguous module names, low confidence)
    - Dynamic replanning (append discovered tasks)
    """

    def __init__(self, clarity_threshold: float = 0.4) -> None:
        super().__init__()
        self._clarity_threshold = clarity_threshold

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(
        self,
        *,
        user_prompt: str | None = None,
        parsed_intent: dict[str, Any] | None = None,
        request_data: dict[str, Any] | None = None,
        agent_state: Any | None = None,
        confidence: float = 0.7,
    ) -> ExecutionPlan:
        """
        Build an execution plan from the user prompt / parsed intent.
        May return a plan with ``clarification_needed`` set if ambiguity is detected.
        """
        parsed = parsed_intent or (getattr(agent_state, "parsed_intent", None) if agent_state else None) or {}
        scope = self._build_scope(parsed, request_data)
        goal = self._build_goal(parsed, agent_state, request_data)
        tasks = self._build_tasks(scope)

        # Phase 2.5: check for ambiguity before finalising
        clarification = self._check_clarification(
            user_prompt=user_prompt or "",
            parsed=parsed,
            confidence=confidence,
            requested_modules=scope.get("included_modules") or [],
        )

        plan = ExecutionPlan(
            goal=goal,
            tasks=tasks,
            execution_order=[t.stage for t in tasks],
            workflow_scope=scope,
            constraints=self._build_constraints(scope, request_data),
            success_criteria=self._build_success_criteria(parsed, agent_state, tasks),
            source_prompt=user_prompt or (getattr(agent_state, "original_user_prompt", None) if agent_state else None),
            clarification_needed=clarification,
        )
        return plan

    def select_capability(self, task_name: str, task_type: str = "crawler") -> str:
        """Determine which tool/capability should execute a given task."""
        mapping = {
            "open_page": "open_page",
            "navigate": "navigate",
            "discover": "discover",
            "capture_screenshot": "capture_screenshot",
            "extract_forms": "extract_forms",
            "aggregate_inventory": "aggregate_inventory",
            "analyse_structure": "analyse_structure",
            "design_scenarios": "design_scenarios",
            "generate_playwright": "generate_playwright",
            "generate_page_objects": "generate_page_objects",
            "generate_tests": "generate_tests",
            "validate_code": "validate_code",
            "execute_tests": "execute_tests",
            "collect_results": "collect_results",
            "generate_report": "generate_report",
            "human_review": "human_review",
            "initialise_workspace": "initialise_workspace",
        }
        return mapping.get(task_name, task_type)

    def capability_stage(self, capability: str) -> str:
        """Map a capability name to the workflow stage that handles it."""
        return _CAPABILITY_STAGE.get(capability, "crawler")

    def replan_after_discovery(
        self,
        plan: ExecutionPlan,
        discovered_modules: list[str],
        crawler_stage: str = "crawler",
    ) -> ExecutionPlan:
        """
        Dynamic replanning: append newly discovered modules as tasks.

        Only adds modules that are NOT already in the plan's scope or tasks.
        Records a revision snapshot before modification.
        """
        existing_modules = set(
            (plan.workflow_scope.get("included_modules") or [])
            + (plan.workflow_scope.get("excluded_modules") or [])
        )
        existing_stages = {t.stage for t in plan.tasks}

        new_discovered = [m for m in discovered_modules if m not in existing_modules and m not in existing_stages]
        if not new_discovered:
            return plan

        plan.snapshot_revision()

        for _idx, module in enumerate(new_discovered, start=1):
            cap = self.select_capability(module, "discover")
            subtasks = [
                SubTask(
                    id=f"st-{module.lower().replace(' ', '-')}-{i}",
                    description=f"Discover and crawl {module}",
                    capability=cap,
                    stage=crawler_stage,
                    discovered=True,
                )
                for i in range(1, 3)
            ]
            task = ExecutionTask(
                name=f"Discover {module}",
                stage=crawler_stage,
                order=max((t.order for t in plan.tasks), default=0) + 1,
                description=f"Crawl the newly discovered {module} area.",
                depends_on=[plan.execution_order[-1]] if plan.execution_order else [],
                capability=cap,
                subtasks=subtasks,
            )
            plan.append_task(task)
            self.logger.info("replan_after_discovery_appended", module=module)

        return plan

    # ------------------------------------------------------------------
    # Clarification
    # ------------------------------------------------------------------

    def _check_clarification(
        self,
        user_prompt: str,
        parsed: dict[str, Any],
        confidence: float,
        requested_modules: list[str],
    ) -> ClarificationNeeded | None:
        """Detect ambiguity and return ClarificationNeeded, or None if clear."""
        if confidence < self._clarity_threshold:
            return ClarificationNeeded(
                message=f"Intent confidence is too low ({confidence:.0%}) to proceed automatically. Please provide more detail.",
                ambiguous_term="entire prompt",
                confidence=confidence,
                recommended=None,
            )

        if not requested_modules:
            return None

        lower_prompt = user_prompt.lower() if user_prompt else ""
        for mod in requested_modules:
            cluster = _AMBIGUOUS_CLUSTERS.get(mod.capitalize()) or _AMBIGUOUS_CLUSTERS.get(mod)
            if cluster and not any(k.lower() in lower_prompt for k in cluster):
                return ClarificationNeeded(
                    message=f"'{mod}' could refer to multiple areas in the application. Please clarify which one.",
                    ambiguous_term=mod,
                    options=list(cluster),
                    confidence=confidence,
                    recommended=cluster[0],
                )

        return None

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_scope(
        self,
        parsed: dict[str, Any],
        request_data: dict[str, Any] | None,
    ) -> dict[str, Any]:
        included_modules = list(parsed.get("focus_areas") or [])
        excluded_modules = list(parsed.get("excluded_modules") or [])
        included_pages = list(parsed.get("included_pages") or [])
        excluded_pages = list(parsed.get("excluded_pages") or [])

        ta = (request_data or {}).get("target_application") or {}
        base_url = ta.get("base_url") or ta.get("url") or ""
        environment = ta.get("environment") or parsed.get("environment") or "staging"

        return {
            "target_url": base_url,
            "environment": environment,
            "included_modules": included_modules,
            "excluded_modules": excluded_modules,
            "included_pages": included_pages,
            "excluded_pages": excluded_pages,
            "coverage_preferences": list(parsed.get("coverage_preferences") or []),
            "output_preferences": list(parsed.get("output_preferences") or []),
            "has_credentials": bool(parsed.get("has_credentials")) or bool(parsed.get("credentials")),
        }

    def _build_goal(
        self,
        parsed: dict[str, Any],
        agent_state: Any | None,
        request_data: dict[str, Any] | None,
    ) -> str:
        if agent_state and getattr(agent_state, "execution_goal", None):
            return agent_state.execution_goal
        if parsed.get("goal"):
            return str(parsed["goal"])

        focus = parsed.get("focus_areas") or []
        if focus:
            return f"Generate and execute automated tests for: {', '.join(focus)}"
        ta = (request_data or {}).get("target_application") or {}
        url = ta.get("base_url") or ta.get("url") or "the application"
        return f"Test {url} based on the user's instructions"

    def _build_tasks(self, scope: dict[str, Any]) -> list[ExecutionTask]:
        stages: list[str] = []
        if scope.get("has_credentials"):
            stages.append("login")
        stages.extend(STAGE_ORDER)

        coverages = scope.get("coverage_preferences") or []
        included = scope.get("included_modules") or []
        tasks: list[ExecutionTask] = []
        previous: str | None = None
        for idx, stage in enumerate(stages, start=1):
            capability = _CAPABILITY_STAGE.get(stage, stage)
            if stage == "login":
                tasks.append(ExecutionTask(
                    name="Authenticate",
                    stage="login",
                    order=idx,
                    description="Log in with the provided credentials before crawling.",
                    capability="navigate",
                    subtasks=[
                        SubTask(id="st-login-1", description="Navigate to login page", capability="open_page", stage="crawler"),
                        SubTask(id="st-login-2", description="Fill credentials and submit", capability="extract_forms", stage="crawler", depends_on=["st-login-1"]),
                    ],
                ))
            elif stage == "crawler":
                # Phase 2.5: decompose crawl into subtasks derived from included modules
                crawler_subtasks = self._decompose_crawl(included, coverages, scope.get("has_credentials", False) if scope.get("has_credentials") is not None else False)
                tasks.append(ExecutionTask(
                    name=_STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                    stage=stage,
                    order=idx,
                    description=_STAGE_DESCRIPTIONS.get(stage, ""),
                    depends_on=[previous] if previous else [],
                    capability="discover",
                    subtasks=crawler_subtasks,
                ))
            elif stage == "test_design":
                design_subtasks = self._decompose_test_design(included, coverages)
                tasks.append(ExecutionTask(
                    name=_STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                    stage=stage,
                    order=idx,
                    description=_STAGE_DESCRIPTIONS.get(stage, ""),
                    depends_on=[previous] if previous else [],
                    capability="design_scenarios",
                    subtasks=design_subtasks,
                ))
            elif stage == "code_generation":
                codegen_subtasks = self._decompose_codegen(coverages)
                tasks.append(ExecutionTask(
                    name=_STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                    stage=stage,
                    order=idx,
                    description=_STAGE_DESCRIPTIONS.get(stage, ""),
                    depends_on=[previous] if previous else [],
                    capability="generate_playwright",
                    subtasks=codegen_subtasks,
                ))
            elif stage == "execution":
                exec_subtasks = self._decompose_execution(coverages, included)
                tasks.append(ExecutionTask(
                    name=_STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                    stage=stage,
                    order=idx,
                    description=_STAGE_DESCRIPTIONS.get(stage, ""),
                    depends_on=[previous] if previous else [],
                    capability="execute_tests",
                    subtasks=exec_subtasks,
                ))
            else:
                tasks.append(ExecutionTask(
                    name=_STAGE_LABELS.get(stage, stage.replace("_", " ").title()),
                    stage=stage,
                    order=idx,
                    description=_STAGE_DESCRIPTIONS.get(stage, ""),
                    depends_on=[previous] if previous else [],
                    capability=capability,
                    subtasks=[],
                ))
            previous = stage
        return tasks

    # ------------------------------------------------------------------
    # Subtask decomposition
    # ------------------------------------------------------------------

    def _decompose_crawl(
        self,
        included_modules: list[str],
        coverages: list[str],
        has_auth: bool,
    ) -> list[SubTask]:
        """Decompose the crawler stage into atomic subtasks."""
        base: list[SubTask] = []
        if has_auth:
            base.append(SubTask(id="st-crawl-0", description="Authenticate before crawl", capability="navigate", stage="crawler"))
        if included_modules:
            offset = len(base)
            for i, mod in enumerate(included_modules, start=1):
                base.append(SubTask(
                    id=f"st-crawl-{offset + i}",
                    description=f"Crawl {mod} module pages",
                    capability="discover",
                    stage="crawler",
                    depends_on=[base[0].id] if base else [],
                ))
        if not included_modules or not base:
            base.append(SubTask(id="st-crawl-1", description="Crawl application starting from target URL", capability="discover", stage="crawler"))
        return base

    def _decompose_test_design(
        self,
        included_modules: list[str],
        coverages: list[str],
    ) -> list[SubTask]:
        """Decompose test design based on coverage preferences."""
        subtasks: list[SubTask] = [
            SubTask(id="st-design-1", description="Analyse app inventory and structure", capability="analyse_structure", stage="test_design"),
        ]
        last = "st-design-1"
        specific_coverages = [c for c in coverages if c.lower() not in ("all", "full", "comprehensive")]
        if specific_coverages:
            for i, cov in enumerate(specific_coverages, start=2):
                subtasks.append(SubTask(
                    id=f"st-design-{i}",
                    description=f"Design {cov} test scenarios",
                    capability="design_scenarios",
                    stage="test_design",
                    depends_on=[last],
                ))
                last = f"st-design-{i}"
        if included_modules:
            next_id = len(subtasks) + 1
            for mod in included_modules:
                subtasks.append(SubTask(
                    id=f"st-design-{next_id}",
                    description=f"Design scenarios for {mod} module",
                    capability="design_scenarios",
                    stage="test_design",
                    depends_on=[last],
                ))
                next_id += 1
                last = f"st-design-{next_id - 1}"
        if not specific_coverages and not included_modules:
            subtasks.append(SubTask(
                id="st-design-2",
                description="Design comprehensive test scenarios",
                capability="design_scenarios",
                stage="test_design",
                depends_on=[last],
            ))
        return subtasks

    def _decompose_codegen(self, coverages: list[str]) -> list[SubTask]:
        """Decompose code generation based on coverage preferences."""
        subtasks: list[SubTask] = [
            SubTask(id="st-codegen-1", description="Generate IR from approved test plan", capability="generate_tests", stage="code_generation"),
            SubTask(id="st-codegen-2", description="Generate Playwright page objects", capability="generate_page_objects", stage="code_generation", depends_on=["st-codegen-1"]),
            SubTask(id="st-codegen-3", description="Generate Playwright test files", capability="generate_tests", stage="code_generation", depends_on=["st-codegen-2"]),
        ]
        if coverages:
            subtasks.append(SubTask(
                id="st-codegen-4",
                description=f"Generate tests covering: {', '.join(coverages)}",
                capability="generate_tests",
                stage="code_generation",
                depends_on=["st-codegen-3"],
            ))
        return subtasks

    def _decompose_execution(
        self,
        coverages: list[str],
        included_modules: list[str],
    ) -> list[SubTask]:
        """Decompose execution with scope awareness."""
        subtasks: list[SubTask] = [
            SubTask(id="st-exec-1", description="Install Playwright dependencies", capability="initialise_workspace", stage="execution"),
            SubTask(id="st-exec-2", description="Run approved test scenarios", capability="execute_tests", stage="execution", depends_on=["st-exec-1"]),
            SubTask(id="st-exec-3", description="Collect test results and generate reports", capability="generate_report", stage="execution", depends_on=["st-exec-2"]),
        ]
        return subtasks

    def _build_constraints(
        self,
        scope: dict[str, Any],
        request_data: dict[str, Any] | None,
    ) -> list[str]:
        constraints: list[str] = []
        if scope.get("excluded_modules"):
            constraints.append(
                "Do not crawl or generate tests for excluded modules: "
                + ", ".join(scope["excluded_modules"])
            )
        if scope.get("excluded_pages"):
            constraints.append(
                "Do not visit excluded page patterns: " + ", ".join(scope["excluded_pages"])
            )
        if scope.get("included_pages"):
            constraints.append(
                "Restrict crawling to page patterns: " + ", ".join(scope["included_pages"])
            )
        if scope.get("coverage_preferences"):
            constraints.append(
                "Coverage must include: " + ", ".join(scope["coverage_preferences"])
            )
        if scope.get("environment"):
            constraints.append(f"Target environment: {scope['environment']}")
        if scope.get("target_url"):
            constraints.append(f"Target application URL: {scope['target_url']}")
        return constraints

    def _build_success_criteria(
        self,
        parsed: dict[str, Any],
        agent_state: Any | None,
        tasks: list[ExecutionTask],
    ) -> list[str]:
        criteria: list[str] = []
        if agent_state and getattr(agent_state, "success_criteria", None):
            criteria.extend(agent_state.success_criteria)
        elif parsed.get("success_criteria"):
            criteria.extend(parsed["success_criteria"])
        criteria.append("A test plan is generated covering all included modules/areas")
        criteria.append("The test plan is reviewed and approved (or auto-approved)")
        criteria.append("Playwright test files are generated from the approved plan")
        criteria.append("Tests execute and produce a report (pass or fail is reported)")
        return criteria


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_planner_singleton: ExecutionPlanner | None = None


def get_execution_planner() -> ExecutionPlanner:
    """Return the process-wide ExecutionPlanner singleton."""
    global _planner_singleton
    if _planner_singleton is None:
        _planner_singleton = ExecutionPlanner()
    return _planner_singleton

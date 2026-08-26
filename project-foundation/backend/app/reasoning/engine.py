"""
Reasoning Engine — converts natural language into structured execution strategy.

Phase 4: The agent THINKS before executing. Input: prompt + AgentState +
ExecutionPlan + inventory. Output: ReasoningResult that enriches ExecutionPlan.
"""

from __future__ import annotations

import re
from typing import Any

from app.context.execution_planner import ExecutionPlan
from app.core.interfaces import ILLMClient
from app.graph.expected_state import (
    EVIDENCE_AUTH_CHANGED,
    EVIDENCE_ELEMENTS_MUTATED,
    EVIDENCE_NAVIGATION_OCCURRED,
    EVIDENCE_NETWORK_ACTIVITY,
    EVIDENCE_STORAGE_CHANGED,
    ExpectedStateGraph,
    ExpectedStateNode,
    ExpectedStateTransition,
)
from app.logging import LoggerMixin
from app.reasoning.models import (
    BusinessIntent,
    CompletionCriterion,
    ConfidenceDetails,
    Constraint,
    ExecutionStrategy,
    NavigationIntent,
    ReasoningResult,
    ReasoningTrace,
    TestingIntent,
    WorkflowIntent,
)
from app.reasoning.prompts import REASONING_SYSTEM_PROMPT, REASONING_USER_TEMPLATE

# ---------------------------------------------------------------------------
# Generic capability routing (framework-level behaviour, NOT application
# specific). Verbs from the user's instruction are routed to a generic
# capability. There is no fixed workflow template and no business keyword.
# ---------------------------------------------------------------------------

# Generic action verb -> generic capability. Authentication ("login") is one
# capability among many; it is never a special-cased string.
_VERB_CAPABILITY: dict[str, str] = {
    "navigate": "navigate", "goto": "navigate", "visit": "navigate", "open": "navigate",
    "view": "navigate", "show": "navigate", "display": "navigate", "go": "navigate",
    "click": "click", "fill": "fill", "type": "fill", "enter": "fill",
    "create": "submit", "submit": "submit", "add": "submit", "new": "submit",
    "register": "submit", "enroll": "submit", "make": "submit", "save": "submit",
    "upload": "upload", "download": "download", "export": "download",
    "select": "select", "choose": "select", "pick": "select",
    "approve": "approve", "authorization": "approve", "authorise": "approve",
    "authorisation": "approve", "approval": "approve",
    "reject": "reject", "deny": "reject",
    "search": "search", "query": "search", "find": "search",
    "edit": "edit", "update": "edit", "modify": "edit",
    "delete": "delete", "remove": "delete",
    "reset": "reset", "forgot": "reset",
    "wait": "wait",
    # authentication capability — generic, routed by verb like any other action
    "login": "authenticate", "signin": "authenticate", "sign_in": "authenticate",
    "sign-in": "authenticate", "log_in": "authenticate", "log-in": "authenticate",
    "auth": "authenticate", "authenticate": "authenticate", "sso": "authenticate",
    "oauth": "authenticate",
}

# Generic capability -> supporting evidence types. These are framework-level
# evidence categories; they are supporting information only, never success rules.
_CAPABILITY_EVIDENCE: dict[str, list[str]] = {
    "navigate": [EVIDENCE_NAVIGATION_OCCURRED],
    "authenticate": [EVIDENCE_AUTH_CHANGED, EVIDENCE_NAVIGATION_OCCURRED],
    "click": [EVIDENCE_ELEMENTS_MUTATED],
    "fill": [EVIDENCE_ELEMENTS_MUTATED],
    "submit": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY, EVIDENCE_STORAGE_CHANGED],
    "approve": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
    "reject": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
    "search": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
    "upload": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
    "download": [EVIDENCE_NETWORK_ACTIVITY],
    "select": [EVIDENCE_ELEMENTS_MUTATED],
    "edit": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
    "delete": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
    "reset": [EVIDENCE_NAVIGATION_OCCURRED, EVIDENCE_ELEMENTS_MUTATED],
    "wait": [EVIDENCE_NAVIGATION_OCCURRED],
    "interact": [EVIDENCE_ELEMENTS_MUTATED, EVIDENCE_NETWORK_ACTIVITY],
}

# Words that indicate an authentication objective when present in a requested
# step/module. Generic language concepts — same class as resolver synonyms.
_AUTH_OBJECTIVE_TOKENS: frozenset[str] = frozenset({
    "login", "logon", "signin", "sign-in", "sign_in", "log-in", "log_in",
    "auth", "authenticate", "authentication", "sso", "oauth", "session",
})

# Auth-intent trigger phrases for the deterministic path.
_AUTH_INTENT_PHRASES: tuple[str, ...] = (
    "login", "signin", "sign-in", "log in", "log-in", "sign in",
    "auth", "authenticate", "authentication", "sso", "oauth",
)


class ReasoningEngine(LoggerMixin):
    """
    LLM-powered reasoning: human language → structured execution strategy.

    Does NOT replace ExecutionPlanner. Produces ReasoningResult which
    enriches ExecutionPlan with business intent, constraints, workflow
    understanding, and execution strategy.
    """

    def __init__(self, llm_client: ILLMClient | None = None) -> None:
        super().__init__()
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def reason(
        self,
        raw_prompt: str,
        *,
        agent_state: Any | None = None,
        execution_plan: ExecutionPlan | None = None,
        inventory: Any | None = None,
        conversation_context: str = "",
        application_metadata: dict[str, Any] | None = None,
        model: str | None = None,
    ) -> ReasoningResult:
        """
        Analyse the user prompt and produce a structured ReasoningResult.

        Falls back to deterministic keyword extraction when no LLM is available.
        """
        if not raw_prompt or not raw_prompt.strip():
            return ReasoningResult(confidence=0.0)

        if self._llm:
            try:
                return await self._llm_reason(
                    raw_prompt,
                    agent_state=agent_state,
                    execution_plan=execution_plan,
                    inventory=inventory,
                    conversation_context=conversation_context,
                    application_metadata=application_metadata,
                    model=model,
                )
            except Exception as e:
                self.logger.warning("llm_reasoning_failed_falling_back_to_deterministic", error=str(e))

        return self._deterministic_reason(raw_prompt, agent_state=agent_state)

    def generate_trace(self, result: ReasoningResult, run_id: str, raw_prompt: str) -> ReasoningTrace:
        """Create a debug ReasoningTrace from the reasoning result."""
        return ReasoningTrace(
            run_id=run_id,
            raw_prompt=raw_prompt,
            detected_intent=result.detected_intent,
            extracted_constraints=[c.description for c in result.constraints],
            decisions=list(result.decisions),
            execution_strategy=result.execution_strategy.approach,
            confidence_details=(
                result.confidence_details.model_dump(mode="json")
                if result.confidence_details is not None
                else {}
            ),
            expected_state_graph=result.expected_state_graph,
        )

    # ------------------------------------------------------------------
    # LLM reasoning
    # ------------------------------------------------------------------

    async def _llm_reason(
        self,
        raw_prompt: str,
        *,
        agent_state: Any | None,
        execution_plan: ExecutionPlan | None,
        inventory: Any | None,
        conversation_context: str,
        application_metadata: dict[str, Any] | None,
        model: str | None,
    ) -> ReasoningResult:
        inventory_summary = self._summarise_inventory(inventory)
        app_meta = application_metadata or {}
        if execution_plan:
            app_meta.setdefault("target_url", execution_plan.workflow_scope.get("target_url"))
            app_meta.setdefault("environment", execution_plan.workflow_scope.get("environment"))

        user_prompt = REASONING_USER_TEMPLATE.format(
            conversation_context=conversation_context or "None",
            inventory_summary=inventory_summary or "No inventory available yet",
            application_metadata=str(app_meta) if app_meta else "Unknown",
            raw_prompt=raw_prompt,
        )

        response = await self._llm.complete(  # type: ignore[union-attr]
            prompt=user_prompt,
            system_prompt=REASONING_SYSTEM_PROMPT,
            temperature=0.2,
            max_tokens=2000,
            model=model,
        )
        if not response:
            return self._deterministic_reason(raw_prompt, agent_state=agent_state)

        data = self._extract_json(response)
        return self._parse_result(data, raw_prompt=raw_prompt)

    # ------------------------------------------------------------------
    # Deterministic fallback (keyword-based, no LLM)
    # ------------------------------------------------------------------

    def _deterministic_reason(
        self,
        raw_prompt: str,
        *,
        agent_state: Any | None = None,
    ) -> ReasoningResult:
        """Keyword-based reasoning when LLM is unavailable. Fast and always available."""
        lower = raw_prompt.lower()

        constraints: list[Constraint] = []
        included: list[str] = []
        excluded: list[str] = []
        strategies: list[str] = []
        stopping: list[str] = []
        destructive_allowed = True

        if any(p in lower for p in ("only test", "focus on", "just test", "only crawl")):
            constraints.append(Constraint(type="scope", description="Only test explicitly mentioned modules", rule="focus_modules = extracted", severity="must", applies_to=["crawler", "test_design", "execution"]))

        if any(p in lower for p in ("ignore", "don't test", "do not test", "don't execute", "never open", "skip", "exclude")):
            constraints.append(Constraint(type="scope", description="Exclude explicitly mentioned modules", rule="excluded_modules = extracted", severity="must", applies_to=["crawler", "test_design", "inventory_aggregator"]))

        if "stop after" in lower:
            idx = lower.find("stop after") + 11
            stop_target = raw_prompt[idx:].split(".")[0].split(",")[0].split("\n")[0].strip()
            stopping.append(stop_target)
            constraints.append(Constraint(type="stop", description=f"Stop execution after {stop_target}", rule=f"stop_after = '{stop_target}'", severity="must", applies_to=["execution"]))

        if "if" in lower and "fails" in lower:
            constraints.append(Constraint(type="stop", description="Stop if a critical step fails", rule="stop_on_failure", severity="must", applies_to=["scheduler", "execution"]))

        if any(p in lower for p in ("do not modify", "do not create", "only read", "don't modify", "don't create", "only validate ui")):
            destructive_allowed = False
            constraints.append(Constraint(type="data", description="Do not perform destructive data operations", rule="destructive_allowed = false", severity="must", applies_to=["execution"]))

        if "staging" in lower and any(p in lower for p in ("use", "on", "in")):
            constraints.append(Constraint(type="environment", description="Use staging environment", rule="environment = 'staging'", severity="must", applies_to=["crawler", "execution"]))

        if "credentials below" in lower or "use the credentials" in lower:
            constraints.append(Constraint(type="auth", description="Use provided credentials", rule="auth_required = true", severity="must", applies_to=["crawler"]))

        for word in ("smoke", "boundary", "negative", "positive", "security"):
            if word in lower:
                strategies.append(word)
        if not strategies and "test" in lower:
            strategies = ["functional"]

        # Extract module names from focus/exclude language
        included = self._extract_entities(raw_prompt, ("only test", "focus on", "just test", "test", "crawl"))
        excluded = self._extract_entities(raw_prompt, ("ignore", "don't test", "do not test", "don't execute", "never open", "skip", "exclude"))

        # Detect workflows: sequences like "X → Y → Z"
        workflow_steps = self._detect_workflow(raw_prompt)

        # Authentication is a generic prerequisite capability — determined from
        # intent and the plan's credentials, never hardcoded as a special case.
        has_credentials = self._plan_has_credentials(agent_state)
        auth_required = self._auth_required(raw_prompt, included, constraints, has_credentials=has_credentials)

        # Build the dynamic ExpectedStateGraph from intent (the authoritative
        # completion contract). No fixed workflow templates.
        graph = self._build_expected_state_graph(
            raw_prompt=raw_prompt,
            included=included,
            workflow_steps=workflow_steps,
            auth_required=auth_required,
        )

        # Backward-compatible summary criteria derived from the graph (no
        # business keywords: success/confirm/thank or app URLs).
        completion_criteria = self._criteria_from_graph(graph)
        serialized_criteria = [c.model_dump(mode="json") for c in completion_criteria]

        # Documented, evidence-backed confidence (configurable weights).
        confidence, confidence_details = self._compute_confidence(
            raw_prompt=raw_prompt,
            included=included,
            workflow_steps=workflow_steps,
            strategies=strategies,
            constraints=constraints,
            graph=graph,
        )

        return ReasoningResult(
            detected_intent=f"User wants to test: {', '.join(included) if included else 'the application'}",
            business_intent=BusinessIntent(risk_level="medium"),
            workflow_intent=WorkflowIntent(steps=workflow_steps, entry_point=workflow_steps[0] if workflow_steps else None, exit_point=workflow_steps[-1] if workflow_steps else None) if workflow_steps else WorkflowIntent(),
            navigation_intent=NavigationIntent(pages_to_visit=included, pages_to_skip=excluded),
            testing_intent=TestingIntent(strategies=strategies, focus_modules=included, excluded_modules=excluded, destructive_allowed=destructive_allowed),
            constraints=constraints,
            completion_criteria=completion_criteria,
            expected_state_graph=graph.model_dump(mode="json"),
            execution_strategy=ExecutionStrategy(
                approach="conditional" if (stopping or completion_criteria) else "sequential",
                stopping_conditions=stopping,
                completion_criteria=serialized_criteria,
                priority_ordering=included,
                risk_mitigation=["Stop on unexpected failure"] if not stopping else stopping,
            ),
            confidence=confidence,
            confidence_details=confidence_details,
        )

    # ------------------------------------------------------------------
    # Intent-derived ExpectedStateGraph (dynamic — no fixed templates)
    # ------------------------------------------------------------------

    def _infer_completion_criteria(
        self,
        raw_prompt: str,
        focus_modules: list[str],
    ) -> list[CompletionCriterion]:
        """Backward-compatible criteria derived from the dynamic graph.

        The criteria are a summary of the intent-derived ExpectedStateGraph;
        they carry NO business keywords (success/confirm/thank) and no
        application URLs. Patterns, when present, come from plan tokens
        (user-derived intent).
        """
        graph = self._build_expected_state_graph(
            raw_prompt=raw_prompt,
            included=focus_modules,
            workflow_steps=[],
            auth_required=self._auth_required(raw_prompt, focus_modules, []),
        )
        return self._criteria_from_graph(graph)

    @staticmethod
    def _slugify(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", (text or "").strip().lower()).strip("_")
        return slug or "target"

    @staticmethod
    def _objective_tokens(step: str) -> set[str]:
        return {p for p in re.split(r"[^a-z0-9]+", (step or "").lower()) if p}

    def _objective_capability(self, step: str) -> str:
        """Route an objective (step/module) to a generic capability.

        Generic verb routing only — authentication is one capability among
        many and is never a special-cased string.
        """
        tokens = sorted(self._objective_tokens(step))
        for token in tokens:
            cap = _VERB_CAPABILITY.get(token)
            if cap:
                return cap
        for token in tokens:
            if token.endswith("s") and len(token) > 3:
                cap = _VERB_CAPABILITY.get(token[:-1])
                if cap:
                    return cap
            if token.endswith("ion") and len(token) > 4:
                cap = _VERB_CAPABILITY.get(token[:-3])
                if cap:
                    return cap
        return "navigate"

    def _auth_required(
        self,
        raw_prompt: str,
        focus_modules: list[str],
        constraints: list[Constraint],
        has_credentials: bool = False,
    ) -> bool:
        lower = (raw_prompt or "").lower()
        if has_credentials:
            return True
        if any(c.type == "auth" for c in constraints):
            return True
        if any(p in lower for p in _AUTH_INTENT_PHRASES):
            return True
        return any(
            any(t in _AUTH_OBJECTIVE_TOKENS for t in self._objective_tokens(m))
            for m in focus_modules
        )

    @staticmethod
    def _plan_has_credentials(agent_state: Any | None) -> bool:
        """Whether the ExecutionPlan/AgentState carries credentials (auth provisioned)."""
        if agent_state is None:
            return False
        parsed = getattr(agent_state, "parsed_intent", None) or {}
        if isinstance(parsed, dict):
            if parsed.get("has_credentials"):
                return True
            if parsed.get("credentials"):
                return True
        creds = getattr(agent_state, "credentials", None)
        if isinstance(creds, dict) and creds:
            return True
        return False

    def _build_expected_state_graph(
        self,
        *,
        raw_prompt: str,
        included: list[str],
        workflow_steps: list[str],
        auth_required: bool,
    ) -> ExpectedStateGraph:
        """Dynamically derive the ExpectedStateGraph from the detected intent.

        States and transitions are generated per-intent: authentication is a
        generic prerequisite capability (or the goal when the objective IS
        authentication). The number of states is dynamic. No business strings
        are hardcoded — node names derive from plan tokens.
        """
        graph = ExpectedStateGraph(source=f"reasoning:{str(raw_prompt)[:120]}")
        graph.add_node(ExpectedStateNode(name="initial", phase="initial", description="Starting state"))

        objectives = list(workflow_steps) if workflow_steps else list(included)

        # Authentication as goal vs prerequisite — derived from intent, never
        # from `if prompt == "Login"`.
        auth_is_goal = False
        if objectives:
            auth_is_goal = self._objective_capability(objectives[-1]) == "authenticate"
        elif auth_required:
            auth_is_goal = True

        if auth_required:
            graph.add_node(ExpectedStateNode(
                name="authenticated",
                phase="goal" if auth_is_goal else "prerequisite",
                capability="authenticate",
                description="Authentication completed",
                state_constraint={"authenticated": True},
                is_final=auth_is_goal,
            ))
            graph.add_transition(ExpectedStateTransition(
                source="initial",
                target="authenticated",
                capability="authenticate",
                required_evidence=list(_CAPABILITY_EVIDENCE["authenticate"]),
                semantic_change_description="Authentication completed",
            ))
            if auth_is_goal:
                graph.goal_state = "authenticated"
                return graph
            entry = "authenticated"
        else:
            entry = "initial"

        if not objectives:
            return graph

        # Skip steps already covered by the authentication prerequisite.
        if auth_required:
            objectives = [
                o for o in objectives
                if self._objective_capability(o) != "authenticate"
            ]

        previous = entry
        for idx, step in enumerate(objectives):
            node_name = self._slugify(step)
            capability = self._objective_capability(step)
            is_last = idx == len(objectives) - 1
            graph.add_node(ExpectedStateNode(
                name=node_name,
                phase="goal" if is_last else "milestone",
                capability=capability,
                description=step,
                is_final=is_last,
            ))
            graph.add_transition(ExpectedStateTransition(
                source=previous,
                target=node_name,
                capability=capability,
                required_evidence=list(_CAPABILITY_EVIDENCE.get(capability, ["interact"])),
                semantic_change_description=f"{capability} on {step}",
            ))
            if is_last:
                graph.goal_state = node_name
            previous = node_name

        return graph

    def _criteria_from_graph(self, graph: ExpectedStateGraph) -> list[CompletionCriterion]:
        """Summary criteria derived from graph transitions (no business keywords)."""
        criteria: list[CompletionCriterion] = []
        for transition in graph.transitions:
            capability = transition.capability
            target = transition.target
            if capability == "authenticate":
                criteria.append(CompletionCriterion(
                    description="authentication succeeded",
                    signal="auth_success",
                    required=True,
                ))
            elif capability in ("navigate", "click", "wait", "reset"):
                criteria.append(CompletionCriterion(
                    description=f"reached {target}",
                    signal="page_reached",
                    target_pattern=self._slugify(target),
                    required=True,
                ))
            else:
                criteria.append(CompletionCriterion(
                    description=f"{capability} completed for {target}",
                    signal="action_completed",
                    target_pattern=self._slugify(target),
                    required=True,
                ))
        return criteria

    # ------------------------------------------------------------------
    # Confidence — documented, evidence-backed, configurable
    # ------------------------------------------------------------------

    def _compute_confidence(
        self,
        *,
        raw_prompt: str,
        included: list[str],
        workflow_steps: list[str],
        strategies: list[str],
        constraints: list[Constraint],
        graph: ExpectedStateGraph,
    ) -> tuple[float, ConfidenceDetails]:
        """Compute confidence from explicit signals with a documented formula.

        Weights are framework-level defaults; they can be overridden via
        configuration. Each contribution and its weight is recorded so the
        score is never an unexplained arbitrary number.
        """
        weights = {
            "prompt": 0.2,
            "focus_modules": 0.15,
            "workflow_steps": 0.2,
            "graph_transitions": 0.2,
            "strategies": 0.1,
            "constraints": 0.05,
            "stopping": 0.1,
        }
        contributions: list[dict[str, Any]] = []
        evidence: list[str] = []
        score = 0.0

        if raw_prompt and raw_prompt.strip():
            score += weights["prompt"]
            contributions.append({"signal": "prompt", "weight": weights["prompt"], "satisfied": True})
            evidence.append("natural language prompt provided")
        if included:
            score += weights["focus_modules"]
            contributions.append({"signal": "focus_modules", "weight": weights["focus_modules"], "satisfied": True})
            evidence.append(f"focus modules derived: {len(included)}")
        if workflow_steps:
            score += weights["workflow_steps"]
            contributions.append({"signal": "workflow_steps", "weight": weights["workflow_steps"], "satisfied": True})
            evidence.append(f"workflow steps derived: {len(workflow_steps)}")
        if graph.transitions:
            score += weights["graph_transitions"]
            contributions.append({"signal": "graph_transitions", "weight": weights["graph_transitions"], "satisfied": True})
            evidence.append(f"expected transitions derived: {len(graph.transitions)}")
        if strategies:
            score += weights["strategies"]
            contributions.append({"signal": "strategies", "weight": weights["strategies"], "satisfied": True})
            evidence.append(f"test strategies derived: {len(strategies)}")
        if constraints:
            score += weights["constraints"]
            contributions.append({"signal": "constraints", "weight": weights["constraints"], "satisfied": True})
            evidence.append(f"constraints derived: {len(constraints)}")

        score = round(min(max(score, 0.2), 0.95), 2)
        formula = (
            "score = 0.2*prompt + 0.15*focus_modules + 0.2*workflow_steps "
            "+ 0.2*graph_transitions + 0.1*strategies + 0.05*constraints, clamped to [0.2, 0.95]"
        )
        details = ConfidenceDetails(score=score, formula=formula, contributions=contributions, evidence=evidence)
        return score, details

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_entities(text: str, prefixes: tuple[str, ...]) -> list[str]:
        """Extract module/page names after trigger phrases."""
        lower = text.lower()
        results: list[str] = []
        for prefix in prefixes:
            idx = lower.find(prefix)
            if idx == -1:
                continue
            after = text[idx + len(prefix):].strip()
            chunk = after.split(".")[0].split(",")[0].split(" and ")[0].split("\n")[0].strip()
            # strip leading/trailing scope words ("only"/"just") so the module
            # token is clean (e.g. "Test only Create X" -> "Create X")
            for stop in ("only ", "just "):
                while chunk.lower().startswith(stop):
                    chunk = chunk[len(stop):].strip()
            for stop in (" only", " just"):
                while chunk.lower().endswith(stop):
                    chunk = chunk[:-len(stop)].strip()
            lower_chunk = chunk.lower()
            if lower_chunk in ("it", "the", "a", "an", "this", "that", ""):
                continue
            if chunk not in results:
                results.append(chunk)
        return results

    @staticmethod
    def _detect_workflow(text: str) -> list[str]:
        """Detect sequential workflows. Supports →, ->, periods, 'then', 'next'."""
        import re
        # Split on explicit workflow separators or sentence boundaries
        text = re.sub(r"\s*→\s*|(?<=\w)\.\s+(?=[A-Z])|\s*->\s*|\s+then\s+|\s+and then\s+|\s+next\s+", " → ", text)
        steps = text.split(" → ")
        cleaned = [s.strip().rstrip(".,;:") for s in steps if len(s.strip()) > 3 and not s.strip().lower().startswith(("if", "only", "use", "stop", "generate", "do not", "don't", "ignore"))]
        if len(cleaned) >= 2:
            return cleaned
        return []

    @staticmethod
    def _extract_json(text: str) -> dict[str, Any]:
        import json
        import re as _re
        text = text.strip()
        first = text.find("{")
        last = text.rfind("}")
        if first != -1 and last != -1 and last > first:
            text = text[first:last + 1]
        text = _re.sub(r",\s*}", "}", text)
        text = _re.sub(r",\s*]", "]", text)
        text = _re.sub(r"```json\s*", "", text)
        text = _re.sub(r"```\s*", "", text)
        return json.loads(text)

    @staticmethod
    def _summarise_inventory(inventory: Any) -> str:
        if inventory is None:
            return "No inventory"
        try:
            if hasattr(inventory, "metadata"):
                m = inventory.metadata
                return f"{getattr(m, 'page_count', '?')} pages, {getattr(m, 'form_count', '?')} forms, {getattr(m, 'link_count', '?')} links"
        except Exception:
            pass
        return str(inventory)[:500]

    def _parse_result(self, data: dict[str, Any], raw_prompt: str = "") -> ReasoningResult:
        bi = data.get("business_intent") or {}
        wi = data.get("workflow_intent") or {}
        ni = data.get("navigation_intent") or {}
        ti = data.get("testing_intent") or {}
        es = data.get("execution_strategy") or {}
        constraints = [Constraint(**c) for c in (data.get("constraints") or [])]

        focus = ti.get("focus_modules") or ni.get("pages_to_visit") or []

        raw_cc = data.get("completion_criteria") or []
        raw_graph = data.get("expected_state_graph") or {}

        if raw_graph:
            graph = ExpectedStateGraph(**raw_graph)
            completion_criteria = [CompletionCriterion(**c) for c in raw_cc] if raw_cc else self._criteria_from_graph(graph)
        else:
            graph = self._build_expected_state_graph(
                raw_prompt=raw_prompt,
                included=focus,
                workflow_steps=(wi.get("steps") or []),
                auth_required=self._auth_required(raw_prompt, focus, constraints),
            )
            completion_criteria = [CompletionCriterion(**c) for c in raw_cc] if raw_cc else self._criteria_from_graph(graph)

        serialized_criteria = [c.model_dump(mode="json") for c in completion_criteria]
        if es and not es.get("completion_criteria"):
            es["completion_criteria"] = serialized_criteria

        confidence = float(data.get("confidence", 0.0))
        raw_details = data.get("confidence_details")
        confidence_details = ConfidenceDetails(**raw_details) if raw_details else None
        if not confidence_details and confidence <= 0.0:
            confidence, confidence_details = self._compute_confidence(
                raw_prompt=raw_prompt,
                included=focus,
                workflow_steps=(wi.get("steps") or []),
                strategies=(ti.get("strategies") or []),
                constraints=constraints,
                graph=graph,
            )

        return ReasoningResult(
            detected_intent=data.get("detected_intent"),
            business_intent=BusinessIntent(**bi) if bi else BusinessIntent(),
            workflow_intent=WorkflowIntent(**wi) if wi else WorkflowIntent(),
            navigation_intent=NavigationIntent(**ni) if ni else NavigationIntent(),
            testing_intent=TestingIntent(**ti) if ti else TestingIntent(),
            constraints=constraints,
            completion_criteria=completion_criteria,
            expected_state_graph=graph.model_dump(mode="json"),
            execution_strategy=ExecutionStrategy(**es) if es else ExecutionStrategy(),
            confidence=confidence,
            confidence_details=confidence_details,
        )

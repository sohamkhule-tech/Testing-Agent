"""
Tests for the corrected Goal Completion Engine.

Verifies the intent-derived ExpectedStateGraph (dynamic, no fixed workflow
templates), backward-compatible criteria summary, ExecutionPlan enrichment,
the graph-based evaluation path in ExecutionScopeResolver, goal achievement
in CrawlerService, and the critical authentication prerequisite/goal
regressions.

CRITICAL REGRESSION RULES (these are test cases, NOT production logic):
- "Test only Login": authentication success -> GOAL_COMPLETED
- "Test only Create RRF": authentication success -> GOAL_COMPLETED stays FALSE,
  execution continues, GOAL_COMPLETED only after the final expected transition.
"""

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.event_bus import EventType
from app.execution_scope.resolver import ExecutionScopeResolver
from app.reasoning.engine import ReasoningEngine
from app.reasoning.models import CompletionCriterion, CompletionResult
from app.context.execution_planner import ExecutionPlan, ExecutionPlanner
from app.graph.expected_state import ExpectedStateGraph, ObservedState
from app.graph.goal_completion_engine import GoalCompletionEngine, GoalStatus
from app.graph.evidence_providers import build_observed_state
from app.graph.transition_evaluator import TransitionEvaluator
from app.services.crawler_service import CrawlerService, CrawlPhase


def _graph_for(prompt: str, *, credentials: bool = False) -> ExpectedStateGraph:
    engine = ReasoningEngine(llm_client=None)
    state = SimpleNamespace(parsed_intent={"has_credentials": credentials}) if credentials else None
    result = engine._deterministic_reason(prompt, agent_state=state)
    return ExpectedStateGraph(**result.expected_state_graph)


# ---------------------------------------------------------------------------
# Intent-derived criteria summary (no business keywords)
# ---------------------------------------------------------------------------

def test_infer_completion_criteria_login_only():
    engine = ReasoningEngine()
    criteria = engine._infer_completion_criteria("Test the login only.", ["Login"])

    assert len(criteria) >= 1
    signals = [c.signal for c in criteria]
    assert "auth_success" in signals


def test_infer_completion_criteria_create_rrf():
    engine = ReasoningEngine()
    criteria = engine._infer_completion_criteria("Test only Create RRF.", ["Create RRF"])

    assert len(criteria) >= 1
    # The create action routes to a generic submit capability; the target
    # pattern derives from the plan token, NOT a success keyword.
    assert "rrf" in criteria[0].target_pattern
    assert "success" not in criteria[0].target_pattern
    assert "confirm" not in criteria[0].target_pattern
    assert "thank" not in criteria[0].target_pattern


def test_infer_completion_criteria_forgot_password():
    engine = ReasoningEngine()
    criteria = engine._infer_completion_criteria("Test only Forgot Password.", ["Forgot Password"])

    assert len(criteria) >= 1
    assert "forgot" in criteria[0].target_pattern or "password" in criteria[0].target_pattern


def test_infer_completion_criteria_approval_workflow():
    engine = ReasoningEngine()
    criteria = engine._infer_completion_criteria("Test Approval workflow.", ["Approval Workflow"])

    assert len(criteria) >= 1
    assert "approval" in criteria[0].target_pattern


def test_deterministic_reasoning_populates_completion_criteria():
    engine = ReasoningEngine()
    result = engine._deterministic_reason("Test the login only.")

    assert len(result.completion_criteria) >= 1
    assert len(result.execution_strategy.completion_criteria) >= 1
    # The authoritative contract is the intent-derived graph.
    graph = ExpectedStateGraph(**result.expected_state_graph)
    assert graph.goal_state is not None
    assert graph.node(graph.goal_state).is_final is True


# ---------------------------------------------------------------------------
# ExecutionPlan enrichment
# ---------------------------------------------------------------------------

def test_execution_plan_enrichment():
    engine = ReasoningEngine()
    reasoning = engine._deterministic_reason("Test the login only.")

    plan = ExecutionPlan()
    plan.enrich_from_reasoning(reasoning)

    assert len(plan.completion_criteria) >= 1
    assert plan.completion_criteria[0]["signal"] == "auth_success"
    # The plan carries the dynamic ExpectedStateGraph.
    assert plan.expected_state_graph.get("goal_state") == "authenticated"


# ---------------------------------------------------------------------------
# Legacy criteria evaluation (backward compatible, caller-supplied criteria)
# ---------------------------------------------------------------------------

def test_resolver_evaluate_completion_login_legacy():
    plan = {
        "completion_criteria": [
            {"description": "authentication succeeded", "signal": "auth_success", "required": True},
            {"description": "navigated away from login page", "signal": "url_changed", "target_pattern": "login|signin", "required": True},
        ]
    }
    resolver = ExecutionScopeResolver(plan)

    res1 = resolver.evaluate_completion(url="https://app.com/login", auth_succeeded=False)
    assert not res1.satisfied

    res2 = resolver.evaluate_completion(url="https://app.com/dashboard", auth_succeeded=True)
    assert res2.satisfied
    assert len(res2.matched_criteria) == 2


def test_resolver_evaluate_completion_page_reached_legacy():
    plan = {
        "completion_criteria": [
            {"description": "RRF successfully created", "signal": "page_reached", "target_pattern": "rrf|success", "required": True}
        ]
    }
    resolver = ExecutionScopeResolver(plan)

    res1 = resolver.evaluate_completion(url="https://app.com/form", title="Create RRF")
    assert res1.satisfied

    res2 = resolver.evaluate_completion(url="https://app.com/other", title="Other Page")
    assert not res2.satisfied


# ---------------------------------------------------------------------------
# CRITICAL REGRESSIONS — dynamic graph, semantics-free completion
# ---------------------------------------------------------------------------

def test_graph_login_auth_is_goal():
    graph = _graph_for("Test only Login", credentials=True)
    assert graph.goal_state == "authenticated"
    goal = graph.node(graph.goal_state)
    assert goal.is_final is True
    assert goal.phase == "goal"


def test_graph_create_rrf_auth_is_prerequisite_not_goal():
    graph = _graph_for("Test only Create RRF", credentials=True)
    auth_node = graph.node("authenticated")
    assert auth_node is not None
    assert auth_node.is_final is False
    assert auth_node.phase == "prerequisite"
    assert graph.goal_state == "create_rrf"
    goal = graph.node(graph.goal_state)
    assert goal.is_final is True
    assert goal.phase == "goal"


def test_auth_does_not_prematurely_complete_create_rrf():
    """Authentication success must NOT complete an unrelated workflow goal."""
    graph = _graph_for("Test only Create RRF", credentials=True)
    history = [
        _make_evidence("authenticate", url="/dashboard", auth=True, dom={"form_count": 0}),
    ]
    result = GoalCompletionEngine.evaluate_history(history, graph)
    assert result.status != GoalStatus.GOAL_COMPLETED
    assert result.status == GoalStatus.CONTINUE


def test_create_rrf_completes_only_after_goal_transition():
    graph = _graph_for("Test only Create RRF", credentials=True)
    auth_ev = _make_evidence("authenticate", url="/dashboard", auth=True, dom={"form_count": 0})
    visit_ev = _make_evidence("page_visit", url="/rrf", auth=True, dom={"form_count": 5}, prev=auth_ev.target_state)
    history = [auth_ev, visit_ev]
    assert GoalCompletionEngine.evaluate_history(history, graph).status == GoalStatus.CONTINUE

    submit_ev = _make_evidence("submit", url="/rrf/create", auth=True, dom={"form_count": 7}, prev=visit_ev.target_state)
    history.append(submit_ev)
    result = GoalCompletionEngine.evaluate_history(history, graph)
    assert result.status == GoalStatus.GOAL_COMPLETED
    assert result.matched_transitions == ["authenticated", "create_rrf"]


def test_login_completes_on_auth():
    graph = _graph_for("Test only Login", credentials=True)
    history = [_make_evidence("authenticate", url="/dashboard", auth=True, dom={})]
    result = GoalCompletionEngine.evaluate_history(history, graph)
    assert result.status == GoalStatus.GOAL_COMPLETED


def test_login_does_not_complete_without_authenticate_capability():
    """A mere page visit (capability mismatch) must not complete the auth goal."""
    graph = _graph_for("Test only Login", credentials=True)
    history = [_make_evidence("page_visit", url="/login", auth=False, dom={})]
    result = GoalCompletionEngine.evaluate_history(history, graph)
    assert result.status != GoalStatus.GOAL_COMPLETED


def test_missing_graph_returns_continue_never_completed():
    """Missing ExpectedStateGraph -> CONTINUE, never GOAL_COMPLETED."""
    result = GoalCompletionEngine.evaluate_history([], None)
    assert result.status == GoalStatus.CONTINUE
    assert not result.goal_achieved


def test_missing_graph_does_not_lift_scope_enforcement():
    """A missing graph must not turn into unrestricted crawling."""
    plan = {
        "workflow_scope": {
            "included_modules": ["Login"],
            "excluded_modules": [],
            "included_pages": [],
            "excluded_pages": [],
        }
    }
    resolver = ExecutionScopeResolver(plan)
    assert resolver.restricted is True
    assert resolver.evaluate("https://app.example.com/login").allowed
    assert not resolver.evaluate("https://app.example.com/reports").allowed


def test_capability_success_alone_is_not_goal_completion():
    """authenticate() succeeding does NOT mean GOAL_COMPLETED when the graph
    does not declare authentication as the final goal."""
    graph = _graph_for("Test only Create RRF", credentials=True)
    history = [_make_evidence("authenticate", url="/dashboard", auth=True, dom={})]
    result = GoalCompletionEngine.evaluate_history(history, graph)
    assert result.status == GoalStatus.CONTINUE
    assert not result.goal_achieved


# ---------------------------------------------------------------------------
# Resolver graph path (chronological history)
# ---------------------------------------------------------------------------

def test_resolver_graph_path_chronological():
    plan = {"expected_state_graph": _graph_for("Test only Create RRF", credentials=True).model_dump(mode="json")}
    resolver = ExecutionScopeResolver(plan)
    assert resolver.expected_state_graph is not None

    r1 = resolver.evaluate_completion(url="https://app.com/dashboard", auth_succeeded=True, capability="authenticate")
    assert not r1.satisfied
    assert r1.matched_criteria == ["authenticated"]
    assert "create_rrf" in r1.reason
    assert "submit" in r1.reason

    r2 = resolver.evaluate_completion(url="https://app.com/rrf/create", auth_succeeded=True, capability="submit",
                                      observations={"dom": {"form_count": 7}})
    assert r2.satisfied
    assert len(r2.matched_criteria) == 2


def test_resolver_graph_path_login():
    plan = {"expected_state_graph": _graph_for("Test only Login", credentials=True).model_dump(mode="json")}
    resolver = ExecutionScopeResolver(plan)

    r1 = resolver.evaluate_completion(url="https://app.com/dashboard", auth_succeeded=True, capability="authenticate")
    assert r1.satisfied
    assert r1.matched_criteria == ["authenticated"]


# ---------------------------------------------------------------------------
# CrawlerService goal achievement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_crawler_service_mark_goal_achieved():
    browser_mgr = MagicMock()
    service = CrawlerService(browser_manager=browser_mgr)

    comp_res = CompletionResult(satisfied=True, matched_criteria=["authentication succeeded"], reason="Matched auth_success")

    await service._mark_goal_achieved(comp_res, "test-run-123")

    assert service._goal_achieved is True
    assert service._stopped is True
    assert service._crawl_phase == CrawlPhase.GOAL_COMPLETION
    assert service._goal_criteria_met == ["authentication succeeded"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_evidence(capability, *, url, auth, dom, prev=None):
    from app.graph.expected_state import CompletionEvidence, calculate_state_diff
    current = build_observed_state(url=url, authenticated=auth, dom_observations=dom)
    previous = prev if prev is not None else ObservedState(timestamp=0.0)
    return CompletionEvidence(
        timestamp=current.timestamp,
        source_state=previous,
        target_state=current,
        diff=calculate_state_diff(previous, current),
        capability=capability,
    )

"""
Execution Scope Enforcement regression tests (Phases 1-9).

Covers ExecutionScopeResolver decisions, URL pattern derivation, --grep
construction, inventory filtering, and approved-plan scenario filtering —
all driven from the ExecutionPlan (single source of truth).
"""

from datetime import UTC, datetime
from uuid import uuid4

from app.context.execution_planner import ExecutionPlan
from app.execution_scope.filtering import (
    apply_execution_scope,
    filter_approved_plan_by_scope,
    filter_scenarios_by_scope,
)
from app.execution_scope.resolver import (
    ExecutionScopeResolver,
    build_scope_grep,
    derive_url_patterns,
)
from app.reasoning.constraints import ConstraintResolver
from app.reasoning.engine import ReasoningEngine
from app.schemas.crawler import (
    ButtonRecord,
    FormRecord,
    InputRecord,
    NavigationEdge,
    PageRecord,
    UserFlowRecord,
)
from app.schemas.inventory import (
    Inventory,
    InventoryMetadata,
    InventoryNavigation,
    InventoryStatistics,
)


def _reasoning_for(prompt: str):
    engine = ReasoningEngine(llm_client=None)
    return engine._deterministic_reason(prompt)


def _plan_for(prompt: str) -> ExecutionPlan:
    reasoning = _reasoning_for(prompt)
    plan = ExecutionPlan(goal=prompt)
    plan.enrich_from_reasoning(reasoning)
    plan = ConstraintResolver().apply_to_plan(plan, reasoning)
    return plan


def _serialized(plan: ExecutionPlan) -> dict:
    return plan.to_serializable()


class TestResolverScopeDecisions:
    def test_only_login_allows_login_blocks_others(self):
        resolver = ExecutionScopeResolver(
            _serialized(_plan_for("Only test Login"))
        )
        assert resolver.restricted
        assert resolver.included_modules == ["Login"]

        allowed = resolver.evaluate("https://app.example.com/login")
        assert allowed.allowed, allowed.reason
        assert allowed.matched_module == "Login"

        denied = resolver.evaluate("https://app.example.com/reports")
        assert not denied.allowed
        assert "Outside execution scope" in denied.reason

    def test_title_based_matching(self):
        resolver = ExecutionScopeResolver(
            _serialized(_plan_for("Only test Login"))
        )
        assert resolver.evaluate(
            "https://app.example.com/auth?tab=1", title="Sign In"
        ).allowed

    def test_ignore_reports_excludes_module(self):
        plan = ExecutionPlan(
            goal="Test the app. Ignore Reports.",
            workflow_scope={
                "included_modules": [],
                "excluded_modules": ["Reports"],
                "coverage_preferences": [],
            },
        )
        resolver = ExecutionScopeResolver(_serialized(plan))
        assert "Reports" in resolver.excluded_modules
        assert resolver.evaluate("https://app.example.com/reports").allowed is False
        assert resolver.evaluate("https://app.example.com/login").allowed is True

    def test_stopping_condition_detected(self):
        plan = _plan_for("Stop after Approval")
        resolver = ExecutionScopeResolver(_serialized(plan))
        assert resolver.stopping_conditions
        hit = resolver.stopping_condition_hit(
            "https://app.example.com/approval"
        )
        assert hit and "Approval" in hit
        assert resolver.stopping_condition_hit("https://app.example.com/login") is None

    def test_unconstrained_plan(self):
        resolver = ExecutionScopeResolver(_serialized(_plan_for("Test the app")))
        assert resolver.is_unconstrained()
        assert resolver.evaluate("https://app.example.com/anything").allowed

    def test_url_patterns_derived(self):
        patterns = derive_url_patterns(["Create RRF", "Login"])
        assert any("rrf" in p for p in patterns)
        assert any("login" in p for p in patterns)


class TestScopeGrep:
    def test_build_scope_grep_from_modules(self):
        plan = ExecutionPlan(
            goal="Only test Login and Reports",
            workflow_scope={"included_modules": ["Login", "Reports"]},
        )
        grep = build_scope_grep(_serialized(plan))
        assert grep
        assert "login" in grep.lower()
        assert "report" in grep.lower()

    def test_build_scope_grep_coverage_terms(self):
        plan = _plan_for("Only test Login. Generate smoke tests.")
        grep = build_scope_grep(_serialized(plan))
        assert grep and "smoke" in grep.lower()

    def test_build_scope_grep_none_when_unconstrained(self):
        plan = _plan_for("Test the app")
        assert build_scope_grep(_serialized(plan)) is None


class TestInventoryFiltering:
    def _inventory(self):
        login_id = uuid4()
        reports_id = uuid4()
        now = datetime.now(UTC)

        def page(pid, url, title, depth=0):
            return PageRecord(
                page_id=pid,
                url=url,
                title=title,
                status_code=200,
                content_type="text/html",
                depth=depth,
                discovered_at=now,
            )

        login_page = page(login_id, "https://app.example.com/login", "Sign In", 0)
        reports_page = page(reports_id, "https://app.example.com/reports", "Reports", 1)

        navigation = InventoryNavigation(
            edges=[
                NavigationEdge(
                    source_page_id=login_id,
                    target_page_id=reports_id,
                    link_text="Reports",
                    link_url="https://app.example.com/reports",
                )
            ],
            root_page_id=login_id,
            total_edges=1,
        )

        return Inventory(
            metadata=InventoryMetadata(
                run_id=uuid4(),
                request_id=uuid4(),
                generated_at=now,
                source_files=["contracts/crawl-package.json"],
                page_count=2,
                link_count=1,
            ),
            pages=[login_page, reports_page],
            navigation=navigation,
            forms=[
                FormRecord(page_id=login_id, form_id="login-form", method="POST"),
                FormRecord(page_id=reports_id, form_id="report-form", method="GET"),
            ],
            inputs=[
                InputRecord(page_id=login_id, input_type="text", name="username"),
                InputRecord(page_id=reports_id, input_type="text", name="q"),
            ],
            buttons=[
                ButtonRecord(page_id=login_id, text="Sign in", button_type="submit"),
                ButtonRecord(page_id=reports_id, text="Export", button_type="button"),
            ],
            links=[("https://app.example.com/reports", "Reports", "https://app.example.com/login")],
            user_flows=[
                UserFlowRecord(
                    flow_id=uuid4(),
                    name="Login",
                    start_url="https://app.example.com/login",
                ),
                UserFlowRecord(
                    flow_id=uuid4(),
                    name="Reports",
                    start_url="https://app.example.com/reports",
                ),
            ],
            statistics=InventoryStatistics(total_pages=2, total_forms=2),
        )

    def test_only_login_filters_inventory(self):
        inv = self._inventory()
        plan = _plan_for("Only test Login")
        filtered = apply_execution_scope(inv, _serialized(plan))

        assert len(filtered.pages) == 1
        assert filtered.pages[0].url.endswith("/login")
        assert len(filtered.forms) == 1
        assert len(filtered.inputs) == 1
        assert len(filtered.buttons) == 1
        assert filtered.navigation.total_edges == 0
        assert len(filtered.user_flows) == 1
        assert filtered.metadata.page_count == 1
        assert filtered.metadata.excluded_page_count == 1
        assert filtered.statistics.total_pages == 1

    def test_unconstrained_returns_same_inventory(self):
        inv = self._inventory()
        plan = _plan_for("Test the app")
        filtered = apply_execution_scope(inv, _serialized(plan))
        assert filtered is inv
        assert len(filtered.pages) == 2


class TestScenarioFiltering:
    def test_filters_modules_and_scenarios(self):
        modules = [
            {
                "name": "Login Module",
                "scenarios": [{"metadata": {"id": "TC-001", "module": "Login Module"}}],
            },
            {
                "name": "Reports Module",
                "scenarios": [{"metadata": {"id": "TC-002", "module": "Reports Module"}}],
            },
        ]
        scenarios = [
            {"metadata": {"id": "TC-001", "module": "Login Module"}},
            {"metadata": {"id": "TC-002", "module": "Reports Module"}},
        ]
        resolver = ExecutionScopeResolver(_serialized(_plan_for("Only test Login")))

        kept_modules, kept_scenarios = filter_scenarios_by_scope(
            modules, scenarios, resolver
        )

        assert [m["name"] for m in kept_modules] == ["Login Module"]
        assert [s["metadata"]["id"] for s in kept_scenarios] == ["TC-001"]

    def test_filter_approved_plan_by_scope(self):
        plan_data = {
            "modules": [
                {"name": "Login Module", "scenarios": [{"metadata": {"id": "TC-001", "module": "Login Module"}}]},
                {"name": "Reports Module", "scenarios": [{"metadata": {"id": "TC-002", "module": "Reports Module"}}]},
            ],
            "test_scenarios": [
                {"metadata": {"id": "TC-001", "module": "Login Module", "category": "happy_path", "priority": "high"}},
                {"metadata": {"id": "TC-002", "module": "Reports Module", "category": "smoke", "priority": "medium"}},
            ],
        }
        plan = _plan_for("Only test Login")
        result = filter_approved_plan_by_scope(plan_data, _serialized(plan))

        assert len(result["modules"]) == 1
        assert result["modules"][0]["name"] == "Login Module"
        assert len(result["test_scenarios"]) == 1
        assert result["coverage_summary"]["total_scenarios"] == 1

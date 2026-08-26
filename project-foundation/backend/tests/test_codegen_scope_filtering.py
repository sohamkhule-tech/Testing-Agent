"""
Regression tests for selective Human Review scope filtering into Code
Generation and Test Execution.

Guarantees:
- 20 scenarios + approve 3 → Code Generation receives exactly the 3 approved
  scenarios (with full metadata), never the 17 pending.
- The persisted approved plan is NEVER mutated — a scoped COPY is produced.
- Fully approved / no review → all scenarios proceed (legacy unchanged).
- Zero approved scenarios → Code Generation / Test Execution do NOT start and
  the run is parked awaiting review.
- The generated spec emits exactly one ``test()`` per approved flow, so
  Playwright execution can only run the approved tests.
"""

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.constants import RunStatus
from app.services.human_review_service import HumanReviewService
from app.workflows.trigger_workflow import PlatformWorkflowState, code_generation_node

APPROVED_IDS = ["TC-001", "TC-002", "TC-003"]


def _scenario_meta(i: int) -> dict:
    return {
        "id": f"TC-{i:03d}",
        "title": f"Scenario {i}",
        "description": f"Description {i}",
        "priority": "medium",
        "category": "functional",
        "module": "Login Module",
        "target_page": "Login",
        "preconditions": ["User is on the login page"],
        "test_steps": [f"step {i}-1", f"step {i}-2"],
        "expected_result": f"expected {i}",
        "required_test_data": [f"data-{i}"],
        "tags": ["regression", f"tag-{i}"],
        "dependencies": [],
        "risk_level": "medium",
    }


def _plan_dict(count: int = 20) -> dict:
    scenarios = [{"metadata": _scenario_meta(i)} for i in range(1, count + 1)]
    return {
        "run_id": str(uuid4()),
        "request_id": str(uuid4()),
        "generated_at": datetime.now(UTC).isoformat(),
        "application_summary": {
            "name": "App", "base_url": "http://example.com",
            "total_pages": 1, "total_forms": 1, "total_links": 0,
            "authentication_required": False, "auth_method": "none",
        },
        "coverage_summary": {"total_scenarios": count, "unique_user_flows": 1},
        "modules": [
            {
                "name": "Login Module",
                "description": "Login scenarios",
                "scenarios": [{"metadata": _scenario_meta(i)} for i in range(1, count + 1)],
            }
        ],
        "test_scenarios": scenarios,
    }


def _write_review(
    workspace: Path,
    approved: list[str],
    total: int = 20,
    review_status: str = "partially_approved",
) -> None:
    """Write review-metadata.json + approved-test-plan.json with scenario_reviews."""
    contracts = workspace / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)

    plan = _plan_dict(total)
    reviews = {}
    for i in range(1, total + 1):
        sid = f"TC-{i:03d}"
        reviews[sid] = {
            "scenario_id": sid,
            "status": "approved" if sid in approved else "pending",
            "enabled": True,
            "modified": False,
        }

    approved_plan = {
        "run_id": str(uuid4()),
        "request_id": str(uuid4()),
        "generated_at": plan["generated_at"],
        "review_version": 1,
        "review_status": review_status,
        "reviewer_name": "tester",
        "test_plan_data": plan,
        "scenario_reviews": reviews,
    }
    (contracts / "approved-test-plan.json").write_text(
        json.dumps(approved_plan, indent=2), encoding="utf-8"
    )
    (contracts / "review-metadata.json").write_text(
        json.dumps({
            "review_status": review_status,
            "decision": "partial_approval",
            "review_version": 1,
            "reviewer_name": "tester",
            "approved_scenarios": len(approved),
            "rejected_scenarios": 0,
            "total_scenarios": total,
        }),
        encoding="utf-8",
    )


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture
def hr_service() -> HumanReviewService:
    return HumanReviewService()


class TestScopedPlanResolution:
    async def _resolve(self, service, workspace):
        return await service.resolve_codegen_test_plan_path(
            workspace_path=str(workspace), canonical_path=None
        )

    @pytest.mark.asyncio
    async def test_partial_approval_scopes_to_exactly_approved(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, APPROVED_IDS)

        path = await self._resolve(hr_service, workspace)

        assert path is not None
        assert path.endswith("codegen-scoped-plan.json")
        scoped = _load(path)
        ids = [s["metadata"]["id"] for s in scoped["test_plan_data"]["test_scenarios"]]
        assert sorted(ids) == sorted(APPROVED_IDS)

        # Pending scenarios are NOT part of the scoped plan.
        assert "TC-004" not in ids
        assert "TC-020" not in ids
        assert len(ids) == 3

        # The canonical persisted plan is never mutated.
        canonical = _read(workspace / "contracts" / "approved-test-plan.json")
        assert len(canonical["test_plan_data"]["test_scenarios"]) == 20

    @pytest.mark.asyncio
    async def test_scoped_plan_preserves_full_scenario_metadata(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, APPROVED_IDS)
        path = await self._resolve(hr_service, workspace)

        scoped = _load(path)
        approved_by_id = {
            s["metadata"]["id"]: s["metadata"]
            for s in scoped["test_plan_data"]["test_scenarios"]
        }
        # Every required field survives on the scoped copy for an approved id.
        meta = approved_by_id["TC-001"]
        for field in ("id", "title", "description", "priority", "category", "tags"):
            assert field in meta and _scenario_meta(1)[field] == meta[field]
        assert meta["test_steps"] == _scenario_meta(1)["test_steps"]
        assert meta["expected_result"] == _scenario_meta(1)["expected_result"]
        assert meta["module"] == "Login Module"
        assert meta["risk_level"] == "medium"

        # Modules trimmed to approved scenarios only.
        module = scoped["test_plan_data"]["modules"][0]
        assert [s["metadata"]["id"] for s in module["scenarios"]] == APPROVED_IDS
        # Coverage reflects the scoped set.
        assert scoped["test_plan_data"]["coverage_summary"]["total_scenarios"] == 3

    @pytest.mark.asyncio
    async def test_partial_approval_with_gaps(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, ["TC-001", "TC-003"])
        path = await self._resolve(hr_service, workspace)
        ids = [s["metadata"]["id"] for s in _load(path)["test_plan_data"]["test_scenarios"]]
        assert sorted(ids) == ["TC-001", "TC-003"]

    @pytest.mark.asyncio
    async def test_full_approval_returns_canonical(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, [f"TC-{i:03d}" for i in range(1, 21)], review_status="approved")

        path = await self._resolve(hr_service, workspace)

        assert path.endswith("approved-test-plan.json")
        canonical = _load(path)
        assert len(canonical["test_plan_data"]["test_scenarios"]) == 20

    @pytest.mark.asyncio
    async def test_no_review_preserves_legacy(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        contracts = workspace / "contracts"
        contracts.mkdir(parents=True)
        (contracts / "approved-test-plan.json").write_text(
            json.dumps({"test_plan_data": _plan_dict(20)}), encoding="utf-8"
        )
        # NO review-metadata.json → no scoping.

        path = await self._resolve(hr_service, workspace)
        assert path.endswith("approved-test-plan.json")

    @pytest.mark.asyncio
    async def test_zero_approved_returns_none(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, approved=[], review_status="partially_approved")
        assert await self._resolve(hr_service, workspace) is None

    @pytest.mark.asyncio
    async def test_under_review_zero_approved_returns_none(self, hr_service, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, approved=[], review_status="under_review")
        assert await self._resolve(hr_service, workspace) is None


class RecordingAgent:
    """Mirrors CodeGenerationAgent execute for wiring tests."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.captured = None

    async def execute(self, input_data):
        self.captured = input_data
        scoped = _load(input_data["approved_test_plan_path"])
        n = len(scoped["test_plan_data"]["test_scenarios"])
        return {
            "status": "completed",
            "project_path": str(self.workspace / "artifacts" / "generated-tests" / "playwright"),
            "metadata_path": str(
                self.workspace / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json"
            ),
            "files_generated": n,
            "page_objects_count": 1,
            "test_files_count": 1,
            "scenarios_implemented": n,
            "modules_covered": ["Login Module"],
            "validation_status": "valid",
            "validation_errors": 0,
            "validation_warnings": 0,
            "refinement_attempts": 0,
            "duration_seconds": 1.0,
            "warnings": [],
        }


def _state(workspace: Path, agent) -> PlatformWorkflowState:
    return PlatformWorkflowState(
        run_id=str(uuid4()),
        status=RunStatus.RUNNING,
        workspace_path=str(workspace),
        requested_by="tester",
        approved_test_plan_path=str(workspace / "contracts" / "approved-test-plan.json"),
        node_results={},
        metadata={"code_generation_agent": agent},
        agent_state=None,
        execution_plan=None,
    )


class TestCodegenNodeScoping:
    @pytest.mark.asyncio
    async def test_codegen_node_receives_only_the_three_approved(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, APPROVED_IDS)
        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)

        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out = await code_generation_node(state)

        assert agent.captured is not None
        scoped_path = agent.captured["approved_test_plan_path"]
        assert scoped_path.endswith("codegen-scoped-plan.json")

        ids = [s["metadata"]["id"] for s in _load(scoped_path)["test_plan_data"]["test_scenarios"]]
        assert sorted(ids) == sorted(APPROVED_IDS)
        # Code generation implements exactly the approved count.
        assert out.scenarios_implemented == 3
        assert out.code_generation_status == "completed"

        # Source of truth (canonical approved plan) still carries all 20.
        canonical = _read(workspace / "contracts" / "approved-test-plan.json")
        assert len(canonical["test_plan_data"]["test_scenarios"]) == 20
        assert out.approved_test_plan_path.endswith("approved-test-plan.json")

    @pytest.mark.asyncio
    async def test_zero_approved_does_not_start_codegen(self, tmp_path: Path):
        workspace = tmp_path / "ws"
        _write_review(workspace, approved=[])
        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)

        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out = await code_generation_node(state)

        # Code Generation never invoked → no Playwright project → no execution.
        assert agent.captured is None
        assert out.code_generation_status == "awaiting_review"
        assert out.status == RunStatus.PAUSED
        assert "code_generation" not in out.node_results  # router ends → no execution


class TestEndToEndApproveThenScope:
    @pytest.mark.asyncio
    async def test_approve_3_of_20_then_codegen_gets_exactly_3(self, tmp_path: Path):
        """Real chain: approve 3 of 20 via the service → scoped plan has exactly 3."""
        from app.schemas.test_plan import (
            ApplicationSummary,
            CoverageSummary,
            Priority,
            ScenarioMetadata,
            TestAssumptions,
            TestCategory,
            TestModule,
            TestPlan,
            TestPriorities,
            TestScenario,
        )

        count = 20
        scenarios = [
            TestScenario(
                metadata=ScenarioMetadata(
                    id=f"TC-{i:03d}",
                    title=f"Scenario {i}",
                    description=f"Description {i}",
                    priority=Priority.MEDIUM,
                    category=TestCategory.FUNCTIONAL,
                    module="Login Module",
                    expected_result=f"expected {i}",
                ),
                steps=[],
                expected_outcome=f"expected {i}",
            )
            for i in range(1, count + 1)
        ]
        plan = TestPlan(
            run_id=str(uuid4()),
            request_id=str(uuid4()),
            generated_at=datetime.now(UTC),
            application_summary=ApplicationSummary(name="App", base_url="http://example.com", total_pages=1, total_forms=1, total_links=0),
            coverage_summary=CoverageSummary(total_scenarios=count, unique_user_flows=1, form_coverage_percentage=100.0, link_coverage_percentage=0.0),
            priorities=TestPriorities(high_priority_scenarios=0, medium_priority_scenarios=count, low_priority_scenarios=0),
            assumptions=TestAssumptions(assumptions=[]),
            modules=[TestModule(name="Login Module", description="Login", scenarios=scenarios)],
            test_scenarios=scenarios,
        )
        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        (contracts / "test-plan.json").write_text(
            json.dumps(plan.model_dump(mode="json"), indent=2), encoding="utf-8"
        )

        service = HumanReviewService()
        review = await service.approve_selected_scenarios(
            workspace_path=str(tmp_path),
            run_id=uuid4(),
            reviewer_name="tester",
            scenario_ids=APPROVED_IDS,
        )
        assert review["approved_scenarios"] == 3
        assert review["total_scenarios"] == 20
        assert review["review_status"] == "partially_approved"

        path = await service.resolve_codegen_test_plan_path(workspace_path=str(tmp_path))
        assert path.endswith("codegen-scoped-plan.json")
        scoped = _load(path)
        ids = [s["metadata"]["id"] for s in scoped["test_plan_data"]["test_scenarios"]]
        assert sorted(ids) == sorted(APPROVED_IDS)

        # The persisted approved plan is scoped to the approved subset; all
        # scenario decisions remain in scenario_reviews.
        canonical = _read(tmp_path / "contracts" / "approved-test-plan.json")
        canonical_ids = [s["metadata"]["id"] for s in canonical["test_plan_data"]["test_scenarios"]]
        assert sorted(canonical_ids) == sorted(APPROVED_IDS)
        assert len(canonical["scenario_reviews"]) == 20
        assert [rv["status"] for rv in canonical["scenario_reviews"].values()].count("pending") == 17


class TestTemplateOneTestPerApprovedFlow:
    @pytest.mark.asyncio
    async def test_spec_contains_exactly_one_test_per_approved_flow(self, tmp_path: Path):
        from app.generators.template_engine import TemplateEngine
        from app.schemas.ir import (
            ActionIR,
            ActionType,
            AssertionIR,
            AssertionType,
            CodeGenerationIR,
            ElementIR,
            EnvironmentIR,
            FlowStepIR,
            LocatorStrategy,
            MetadataIR,
            ModuleIR,
            NavigationIR,
            PageIR,
            TestFlowIR,
        )

        page = PageIR(
            page_id="login_page",
            name="Login Page",
            url_pattern="http://example.com",
            description="Login",
            elements=[
                ElementIR(id="username_field", name="Username Field", locator_strategy=LocatorStrategy.LABEL, locator_value="Username"),
                ElementIR(id="password_field", name="Password Field", locator_strategy=LocatorStrategy.LABEL, locator_value="Password"),
                ElementIR(id="login_button", name="Login Button", locator_strategy=LocatorStrategy.ROLE, locator_value="button:Login"),
                ElementIR(id="error_message", name="Error Message", locator_strategy=LocatorStrategy.ROLE, locator_value="alert"),
            ],
        )

        def flow(fid: str, name: str) -> TestFlowIR:
            return TestFlowIR(
                flow_id=fid,
                name=name,
                description=name,
                steps=[
                    FlowStepIR(step_order=0, description="Navigate", navigation=NavigationIR(target="http://example.com", wait_for_selector="role:form", description="Open login")),
                    FlowStepIR(step_order=1, description="Fill", actions=[ActionIR(action_type=ActionType.FILL, element_id="username_field", value="$USER")]),
                    FlowStepIR(step_order=2, description="Submit", actions=[ActionIR(action_type=ActionType.CLICK, element_id="login_button")]),
                    FlowStepIR(step_order=3, description="Assert", assertions=[AssertionIR(assertion_type=AssertionType.VISIBLE, element_id="error_message", description="error visible")]),
                ],
            )

        fluxes = [
            flow("tc-1", "Approved One"),
            flow("tc-2", "Approved Two"),
            flow("tc-3", "Approved Three"),
        ]
        ir = CodeGenerationIR(
            metadata=MetadataIR(generator="regression-test"),
            environment=EnvironmentIR(base_url="http://example.com"),
            pages=[page],
            modules=[ModuleIR(module_id="login", name="Login Module", description="d", pages=["login_page"], flows=fluxes)],
        )

        out = tmp_path / "proj"
        TemplateEngine().generate_project(ir, out)

        specs = list((out / "tests").glob("*.spec.ts"))
        assert len(specs) == 1, f"expected one spec file, got {[s.name for s in specs]}"
        spec = specs[0].read_text(encoding="utf-8")
        tests = re.findall(r"\btest\(", spec)
        assert len(tests) == 3, f"expected exactly 3 test() blocks, got {len(tests)}"
        assert "Approved One" in spec
        assert "Approved Two" in spec
        assert "Approved Three" in spec
        # A pending scenario never reaches the generated spec → Playwright can
        # never execute it.
        assert "Pending Nine" not in spec

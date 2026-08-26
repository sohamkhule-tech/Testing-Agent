"""
Regression tests: selective Human Review approval is preserved end-to-end.

Covered scenarios (22 total):
- TEST 1: approve 4 → 4 approved/generated; 18 pending never proceed.
- TEST 2: approve all 22 → all 22 proceed (full approval preserved).
- TEST 3: approve some + reject others → only approved are generated.
- TEST 4: human_review_node re-runs (post-review / resume) do NOT overwrite the
  persisted selective approval (approved_scenarios stays 4, never 22).
- TEST 5: POST /approve followed by the post-review human_review_node keeps 4.

Invariants verified throughout:
  review_status=partially_approved, review_decision=partial_approval,
  approved-* states, approved-test-plan.json/.md scoped, review-metadata counts,
  codegen input scenario count, and the persisted source of truth.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.api.routes import trigger as trigger_routes
from app.api.routes.trigger import _ApproveRunRequest, approve_run
from app.constants import RunStatus
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
from app.services.human_review_service import HumanReviewService
from app.workflows.trigger_workflow import (
    PlatformWorkflowState,
    code_generation_node,
    human_review_node,
)

TOTAL = 22
SUB4 = ["TC-001", "TC-002", "TC-003", "TC-004"]


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_test_plan(tmp_path: Path, count: int = TOTAL) -> Path:
    contracts = tmp_path / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
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
        modules=[
            TestModule(name="Login Module", description="Login", scenarios=[
                TestScenario(
                    metadata=ScenarioMetadata(
                        id=f"TC-{j:03d}",
                        title=f"Scenario {j}",
                        description=f"Description {j}",
                        priority=Priority.MEDIUM,
                        category=TestCategory.FUNCTIONAL,
                        module="Login Module",
                        expected_result=f"expected {j}",
                    ),
                    steps=[],
                    expected_outcome=f"expected {j}",
                )
                for j in range(1, count + 1)
            ])
        ],
        test_scenarios=scenarios,
    )
    (contracts / "test-plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return tmp_path


class RecordingAgent:
    """Replay of CodeGenerationAgent.execute for scope assertions."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.captured = None

    async def execute(self, input_data):
        self.captured = input_data
        plan = _read(Path(input_data["approved_test_plan_path"]))
        n = len(plan["test_plan_data"]["test_scenarios"])
        return {
            "status": "completed",
            "project_path": str(self.workspace / "artifacts" / "generated-tests" / "playwright"),
            "metadata_path": str(self.workspace / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json"),
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


def _state(workspace: Path, agent: RecordingAgent) -> PlatformWorkflowState:
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


async def _approve(*, workspace: Path, ids: list[str], reviewer: str = "tester") -> dict:
    return await HumanReviewService().approve_selected_scenarios(
        workspace_path=str(workspace), run_id=uuid4(), reviewer_name=reviewer, scenario_ids=ids
    )


def _plan_ids(workspace: Path) -> list[str]:
    return [s["metadata"]["id"] for s in _read(workspace / "contracts" / "approved-test-plan.json")["test_plan_data"]["test_scenarios"]]


class TestSelectiveApprovalPreserved:

    @pytest.mark.asyncio
    async def test_approve_4_of_22_preserved_end_to_end(self, tmp_path: Path):
        workspace = _write_test_plan(tmp_path, TOTAL)
        review = await _approve(workspace=workspace, ids=SUB4)

        # Initial decision is PARTIAL — never converted to approved.
        assert review["approved_scenarios"] == 4
        assert review["total_scenarios"] == 22
        assert review["review_status"] == "partially_approved"
        assert review["review_decision"] == "partial_approval"

        # approved-test-plan.json contains ONLY the 4 approved scenarios (E),
        # while scenario_reviews still record all 22 decisions.
        atp = _read(workspace / "contracts" / "approved-test-plan.json")
        assert sorted(_plan_ids(workspace)) == sorted(SUB4)
        assert len(atp["scenario_reviews"]) == 22
        statuses = [rv["status"] for rv in atp["scenario_reviews"].values()]
        assert statuses.count("approved") == 4
        assert statuses.count("pending") == 18

        # review-metadata accurately reflects the partial approval (G).
        meta = _read(workspace / "contracts" / "review-metadata.json")
        assert meta["approved_scenarios"] == 4
        assert meta["rejected_scenarios"] == 0
        assert meta["total_scenarios"] == 22
        assert meta["review_status"] == "partially_approved"
        assert meta["decision"] == "partial_approval"

        # approved-test-plan.md matches the scoped JSON (F).
        md = (workspace / "contracts" / "approved-test-plan.md").read_text(encoding="utf-8")
        for sid in SUB4:
            assert f"#### {sid}:" in md
        assert "TC-005:" not in md

        # ── TEST 4/5 core: the post-review human_review_node re-run MUST reuse
        #    the persisted decision and MUST NOT overwrite it with a full
        #    auto-approval (4 → 22).
        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out = await human_review_node(state)

        assert out.review_status == "partially_approved"
        assert out.approved_scenarios == 4
        assert out.total_scenarios == 22
        assert _read(workspace / "contracts" / "approved-test-plan.json") == atp  # untouched

        # Code Generation receives ONLY the 4 approved scenarios (D).
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out2 = await code_generation_node(out)

        assert agent.captured is not None
        plan_path = agent.captured["approved_test_plan_path"]
        assert plan_path.endswith("codegen-scoped-plan.json")
        scoped = _read(Path(plan_path))
        assert sorted(s["metadata"]["id"] for s in scoped["test_plan_data"]["test_scenarios"]) == sorted(SUB4)
        assert out2.scenarios_implemented == 4
        assert out2.code_generation_status == "completed"

    @pytest.mark.asyncio
    async def test_approve_all_22_full_approval_unchanged(self, tmp_path: Path):
        workspace = _write_test_plan(tmp_path, TOTAL)
        all_ids = [f"TC-{i:03d}" for i in range(1, TOTAL + 1)]
        review = await _approve(workspace=workspace, ids=all_ids)

        assert review["approved_scenarios"] == 22
        assert review["review_status"] == "approved"
        assert len(_plan_ids(workspace)) == 22  # full plan preserved

        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out = await human_review_node(state)
        assert out.approved_scenarios == 22
        assert out.review_status == "approved"

        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            await code_generation_node(out)
        assert agent.captured["approved_test_plan_path"].endswith("approved-test-plan.json")
        assert len(_read(Path(agent.captured["approved_test_plan_path"]))["test_plan_data"]["test_scenarios"]) == 22

    @pytest.mark.asyncio
    async def test_approve_some_reject_others_scopes_to_approved(self, tmp_path: Path):
        from app.schemas.review import ReviewRequest, ScenarioReviewStatus

        workspace = _write_test_plan(tmp_path, TOTAL)
        decisions = {
            f"TC-{i:03d}": ScenarioReviewStatus.REJECTED if i in (3, 4) else ScenarioReviewStatus.APPROVED
            for i in range(1, TOTAL + 1)
        }
        review_request = ReviewRequest(
            run_id=uuid4(),
            reviewer_name="tester",
            auto_approve=False,
            scenario_decisions=decisions,
        )
        result = await HumanReviewService().review_test_plan(str(workspace), review_request)

        assert result["review_status"] == "partially_approved"
        assert result["approved_scenarios"] == 20
        assert result["rejected_scenarios"] == 2
        plan_ids = [s["metadata"]["id"] for s in _read(workspace / "contracts" / "approved-test-plan.json")["test_plan_data"]["test_scenarios"]]
        assert len(plan_ids) == 20
        assert "TC-003" not in plan_ids and "TC-004" not in plan_ids

        # Persisted review survives a human_review_node re-run.
        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out = await human_review_node(state)
        assert out.approved_scenarios == 20
        assert out.review_status == "partially_approved"

        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            await code_generation_node(out)
        assert agent.captured is not None
        scoped_ids = [s["metadata"]["id"] for s in _read(Path(agent.captured["approved_test_plan_path"]))["test_plan_data"]["test_scenarios"]]
        assert len(scoped_ids) == 20
        assert "TC-003" not in scoped_ids and "TC-004" not in scoped_ids

    @pytest.mark.asyncio
    async def test_resume_reruns_keep_4_approved(self, tmp_path: Path):
        """Repeated human_review_node executions (resume/retry/checkpoint) never flip 4 → 22."""
        workspace = _write_test_plan(tmp_path, TOTAL)
        await _approve(workspace=workspace, ids=SUB4)
        snapshot = _read(workspace / "contracts" / "approved-test-plan.json")

        for _ in range(3):
            agent = RecordingAgent(workspace)
            state = _state(workspace, agent)
            with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
                out = await human_review_node(state)
            assert out.review_status == "partially_approved"
            assert out.approved_scenarios == 4
            assert _read(workspace / "contracts" / "approved-test-plan.json") == snapshot

    @pytest.mark.asyncio
    async def test_post_approve_route_then_post_review_keeps_4(self, tmp_path: Path, monkeypatch):
        """POST /approve (selective) followed by the post-review human_review_node keeps 4."""
        workspace = _write_test_plan(tmp_path, TOTAL)

        # Route-level: mirror POST /approve (selective body).
        _spawned = {"count": 0}

        def _fake_create_task(coro):
            _spawned["count"] += 1
            coro.close()
            return SimpleNamespace(add_done_callback=lambda cb: None, cancelled=lambda: False, exception=lambda: None)

        async def _noop(*a, **k):
            return None

        monkeypatch.setattr(trigger_routes.asyncio, "create_task", _fake_create_task)
        monkeypatch.setattr(trigger_routes, "_run_post_review_workflow", _noop)
        monkeypatch.setattr(trigger_routes, "get_code_generation_agent", lambda: object())

        service = SimpleNamespace(
            workspace_path=str(workspace),
            update_status=AsyncMock(return_value=True),
        )
        service.get_run = AsyncMock(side_effect=lambda run_id: SimpleNamespace(
            status=RunStatus.PAUSED, workspace_path=str(workspace), requested_by="reviewer",
        ))

        response = await approve_run(
            uuid4(), service=service,
            payload=_ApproveRunRequest(test_case_ids=SUB4),
        )
        assert sorted(response["approved_test_case_ids"]) == sorted(SUB4)
        assert response["approved_scenarios"] == 4
        assert response["review_status"] == "partially_approved"
        assert _spawned["count"] == 1  # workflow continued

        # The post-review workflow re-runs human_review_node first — it must NOT
        # overwrite the selective approval.
        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)
        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            out = await human_review_node(state)
        assert out.review_status == "partially_approved"
        assert out.approved_scenarios == 4
        assert out.total_scenarios == 22

        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            await code_generation_node(out)
        plan = _read(Path(agent.captured["approved_test_plan_path"]))
        assert sorted(s["metadata"]["id"] for s in plan["test_plan_data"]["test_scenarios"]) == sorted(SUB4)
        assert out.scenarios_implemented == 4

    @pytest.mark.asyncio
    async def test_post_review_graph_preserves_selective_approval(self, tmp_path: Path, monkeypatch):
        """Boots the REAL post-review graph (START→human_review→codegen→execution).

        The human_review re-run must reuse the persisted partial decision (4),
        code generation must receive exactly 4, and execution must run exactly 4.
        """
        from app.workflows import trigger_workflow as tw

        workspace = _write_test_plan(tmp_path, TOTAL)
        await _approve(workspace=workspace, ids=SUB4)

        agent = RecordingAgent(workspace)
        state = _state(workspace, agent)

        original_codegen = tw.code_generation_node
        executed: dict = {}

        async def _fake_codegen(s):
            s = await original_codegen(s)  # real node incl. scoped-plan resolution
            executed["codegen_scenarios"] = s.scenarios_implemented
            executed["codegen_plan"] = agent.captured["approved_test_plan_path"]
            return s

        async def _fake_execution(s):
            executed["execution_scenarios"] = s.scenarios_implemented
            s.execution_status = "completed"
            s.tests_total = s.scenarios_implemented
            return s

        monkeypatch.setattr(tw, "code_generation_node", _fake_codegen)
        monkeypatch.setattr(tw, "execution_node", _fake_execution)

        with patch("app.workflows.trigger_workflow.emit", new=AsyncMock()):
            workflow = tw.create_post_review_workflow()
            final = await workflow.ainvoke(state)

        # The human_review re-run inside the post-review graph preserved the partial decision.
        assert final["review_status"] == "partially_approved"
        assert final["approved_scenarios"] == 4
        assert final["total_scenarios"] == 22

        # Code generation received exactly the 4 approved scenarios.
        assert executed["codegen_plan"].endswith("codegen-scoped-plan.json")
        assert executed["codegen_scenarios"] == 4
        # Execution ran with exactly the 4 generated scenarios.
        assert executed["execution_scenarios"] == 4

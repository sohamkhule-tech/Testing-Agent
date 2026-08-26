"""
Regression tests for selective Human Review approval (test-case level).

Covers the end-to-end approval contract:
- POST /runs/{run_id}/approve with test_case_ids approves ONLY those IDs.
- Unselected test cases remain PENDING / unapproved (partial review).
- The whole plan is never marked APPROVED when only a subset is approved.
- Invalid / nonexistent test-case IDs are rejected safely (no writes, no
  workflow spawn).
- Backward compatibility: a call without a body keeps the legacy approve-all
  behaviour.
- The post-review workflow preserves a persisted partial review instead of
  overwriting it with a blanket auto-approval.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

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
    TestPriorities,
    TestPlan,
    TestScenario,
)
from app.workflows.trigger_workflow import _load_persisted_review

RUN = uuid4()


def _build_workspace(tmp_path: Path, count: int = 20) -> Path:
    """Create a workspace whose test plan has ``count`` scenarios (TC-001..)."""
    contracts = tmp_path / "contracts"
    contracts.mkdir(parents=True)

    scenarios = [
        TestScenario(
            metadata=ScenarioMetadata(
                id=f"TC-{i:03d}",
                title=f"Scenario {i}",
                description="Regression scenario",
                priority=Priority.MEDIUM,
                category=TestCategory.FUNCTIONAL,
                module="Login Module",
                expected_result="ok",
            ),
            steps=[],
            expected_outcome="ok",
        )
        for i in range(1, count + 1)
    ]

    plan = TestPlan(
        run_id=str(uuid4()),
        request_id=str(uuid4()),
        generated_at=datetime.now(timezone.utc),
        application_summary=ApplicationSummary(
            name="Test App", base_url="http://example.com",
            total_pages=1, total_forms=1, total_links=0,
        ),
        coverage_summary=CoverageSummary(
            total_scenarios=count, unique_user_flows=1,
            form_coverage_percentage=100.0, link_coverage_percentage=0.0,
        ),
        priorities=TestPriorities(
            high_priority_scenarios=0, medium_priority_scenarios=count,
            low_priority_scenarios=0,
        ),
        assumptions=TestAssumptions(assumptions=[]),
        modules=[
            TestModule(name="Login Module", description="Login scenarios", scenarios=scenarios)
        ],
        test_scenarios=[],
    )
    (contracts / "test-plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), indent=2), encoding="utf-8"
    )
    return tmp_path


class _FakeTask:
    def __init__(self, coro):
        self._coro = coro

    def add_done_callback(self, cb):
        pass

    def cancelled(self):
        return False

    def exception(self):
        return None


class _Base:
    @pytest.fixture(autouse=True)
    def _controls(self, monkeypatch, tmp_path):
        self.workspace = _build_workspace(tmp_path, count=20)
        self.spawned = {"count": 0}

        def _fake_create_task(coro):
            self.spawned["count"] += 1
            coro.close()
            return _FakeTask(None)

        async def _fake_run_post_review(*args, **kwargs):
            return None

        monkeypatch.setattr(trigger_routes.asyncio, "create_task", _fake_create_task)
        monkeypatch.setattr(trigger_routes, "_run_post_review_workflow", _fake_run_post_review)
        monkeypatch.setattr(trigger_routes, "get_code_generation_agent", lambda: object())

        service = SimpleNamespace()
        service.workspace_path = str(self.workspace)
        service.update_status = AsyncMock(return_value=True)
        service.get_run = AsyncMock(side_effect=lambda run_id: self._entity())
        self.service = service
        yield
        from app.api.routes.trigger import _release_post_review
        _release_post_review(str(RUN))

    def _entity(self):
        return SimpleNamespace(
            status=RunStatus.PAUSED,
            workspace_path=self.service.workspace_path,
            requested_by="reviewer",
        )


class TestSelectiveApproval(_Base):
    @pytest.mark.asyncio
    async def test_approve_two_of_20_approves_only_those(self):
        response = await approve_run(
            RUN,
            service=self.service,
            payload=_ApproveRunRequest(test_case_ids=["TC-001", "TC-002"]),
        )

        assert response["status"] == "running"
        assert sorted(response["approved_test_case_ids"]) == ["TC-001", "TC-002"]
        assert response["review_status"] == "partially_approved"
        assert response["approved_scenarios"] == 2
        assert response["total_scenarios"] == 20
        assert "Approved 2 of 20" in response["message"]
        # Workflow still continues (one background task spawned).
        assert self.spawned["count"] == 1

    @pytest.mark.asyncio
    async def test_unselected_remain_pending_in_persisted_state(self):
        await approve_run(
            RUN, service=self.service,
            payload=_ApproveRunRequest(test_case_ids=["TC-001"]),
        )

        metadata = json.loads(
            (self.workspace / "contracts" / "review-metadata.json").read_text(encoding="utf-8")
        )
        assert metadata["review_status"] == "partially_approved"
        assert metadata["approved_scenarios"] == 1
        assert metadata["total_scenarios"] == 20
        assert metadata["decision"] == "partial_approval"

        approved = json.loads(
            (self.workspace / "contracts" / "approved-test-plan.json").read_text(encoding="utf-8")
        )
        reviews = approved["scenario_reviews"]
        assert reviews["TC-001"]["status"] == "approved"
        assert reviews["TC-002"]["status"] == "pending"
        assert reviews["TC-020"]["status"] == "pending"
        assert sum(1 for r in reviews.values() if r["status"] == "approved") == 1
        assert sum(1 for r in reviews.values() if r["status"] == "pending") == 19

    @pytest.mark.asyncio
    async def test_invalid_ids_rejected_no_writes_no_workflow(self):
        with pytest.raises(Exception) as excinfo:
            await approve_run(
                RUN, service=self.service,
                payload=_ApproveRunRequest(test_case_ids=["TC-001", "NOPE"]),
            )
        assert "do not belong" in str(excinfo.value.detail)

        assert not (self.workspace / "contracts" / "review-metadata.json").exists()
        assert not (self.workspace / "contracts" / "approved-test-plan.json").exists()
        # A rejected request must not spawn the post-review workflow.
        assert self.spawned["count"] == 0
        assert self.service.update_status.await_count == 0

    @pytest.mark.asyncio
    async def test_empty_selection_rejected(self):
        with pytest.raises(Exception) as excinfo:
            await approve_run(
                RUN, service=self.service,
                payload=_ApproveRunRequest(test_case_ids=[]),
            )
        assert "No test cases selected" in str(excinfo.value.detail)
        assert self.spawned["count"] == 0

    @pytest.mark.asyncio
    async def test_no_body_preserves_legacy_approve_all(self):
        response = await approve_run(RUN, service=self.service)
        assert response["status"] == "running"
        assert "approved_test_case_ids" not in response
        assert "review_status" not in response
        assert self.spawned["count"] == 1
        # Legacy path does not rewrite review state from the endpoint.
        assert not (self.workspace / "contracts" / "review-metadata.json").exists()


class TestPersistedReviewPreservation:
    def test_load_persisted_review_returns_partial_state(self, tmp_path):
        contracts = tmp_path / "contracts"
        contracts.mkdir(parents=True)
        (contracts / "review-metadata.json").write_text(
            json.dumps({
                "review_status": "partially_approved",
                "decision": "partial_approval",
                "review_version": 1,
                "reviewer_name": "reviewer",
                "approved_scenarios": 2,
                "rejected_scenarios": 0,
                "total_scenarios": 20,
            }),
            encoding="utf-8",
        )
        (contracts / "approved-test-plan.json").write_text("{}", encoding="utf-8")

        result = asyncio_run(_load_persisted_review(str(tmp_path)))
        assert result is not None
        assert result["review_status"] == "partially_approved"
        assert result["review_decision"] == "partial_approval"
        assert result["approved_scenarios"] == 2
        assert result["total_scenarios"] == 20
        assert result["approved_test_plan_path"].replace("\\", "/").endswith("contracts/approved-test-plan.json")
        assert result["review_metadata_path"].replace("\\", "/").endswith("contracts/review-metadata.json")

    def test_load_persisted_review_none_when_no_metadata(self, tmp_path):
        assert asyncio_run(_load_persisted_review(str(tmp_path))) is None


class TestFastAPIWire(_Base):
    """Verify FastAPI deserializes the optional body (real HTTP request path)."""

    @pytest.fixture(autouse=True)
    def _wire(self):
        from fastapi.testclient import TestClient
        from app.dependencies import get_trigger_service
        from app.main import app

        app.dependency_overrides[get_trigger_service] = lambda: self.service
        self.client = TestClient(app)
        yield
        app.dependency_overrides.pop(get_trigger_service, None)

    def test_http_selective_approve_body(self):
        resp = self.client.post(
            f"/api/v1/runs/{RUN}/approve",
            json={"test_case_ids": ["TC-001", "TC-002"]},
        )
        assert resp.status_code == 202
        data = resp.json()
        assert sorted(data["approved_test_case_ids"]) == ["TC-001", "TC-002"]
        assert data["review_status"] == "partially_approved"
        assert data["approved_scenarios"] == 2
        assert data["total_scenarios"] == 20

    def test_http_no_body_legacy(self):
        resp = self.client.post(f"/api/v1/runs/{RUN}/approve")
        assert resp.status_code == 202
        data = resp.json()
        assert "approved_test_case_ids" not in data

    def test_http_invalid_id_400(self):
        resp = self.client.post(
            f"/api/v1/runs/{RUN}/approve",
            json={"test_case_ids": ["TC-001", "BOGUS"]},
        )
        assert resp.status_code == 400
        assert "do not belong" in resp.json()["detail"]


def asyncio_run(coro):
    import asyncio
    return asyncio.run(coro)
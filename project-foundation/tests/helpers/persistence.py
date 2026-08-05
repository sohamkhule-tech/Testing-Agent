"""
Persistence test helpers.

Factories, builders, comparison functions, and mock objects
for testing every layer of the persistence architecture.
"""

from __future__ import annotations

import random
import string
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.models.orm.core import Project, Run, User
from app.models.orm.discovery import CrawlPackage, Inventory
from app.models.orm.design import HumanReview, TestPlan, TestScenario
from app.models.orm.execution import Execution, TestResult
from app.models.orm.generation import GeneratedProject, IRDocument
from app.models.orm.system import Artifact, AuditLog


# ===================================================================
# Factories — create minimal valid ORM instances
# ===================================================================

_RANDOM_SEED = 0


def _unique_slug(prefix: str = "") -> str:
    global _RANDOM_SEED
    _RANDOM_SEED += 1
    return f"{prefix}{_RANDOM_SEED}_{uuid4().hex[:8]}"


def make_user(**overrides: dict) -> User:
    data = dict(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        email=f"{_unique_slug()}@example.com",
        display_name=_unique_slug("user_"),
        role="engineer",
        status="active",
        avatar_url=None,
        metadata_json={},
        deleted_at=None,
        last_login_at=None,
    )
    data.update(overrides)
    return User(**data)


def make_project(**overrides: dict) -> Project:
    data = dict(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        name=_unique_slug("project_"),
        description=None,
        base_url=f"https://{_unique_slug()}.example.com",
        environment="staging",
        created_by=None,
        default_browser="chromium",
        default_timeout=30000,
        authentication_type=None,
        repository_url=None,
        metadata_json={},
        deleted_at=None,
    )
    data.update(overrides)
    return Project(**data)


def make_run(**overrides: dict) -> Run:
    slug = _unique_slug()
    data = dict(
        run_id=uuid4(),
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        project_id=None,
        request_id=uuid4(),
        requested_by=None,
        trigger_type="api",
        trigger_source=None,
        environment_name=None,
        status="pending",
        current_stage=None,
        progress_percent=0,
        message=None,
        error=None,
        workspace_path=f"/tmp/workspace/{slug}",
        started_at=None,
        completed_at=None,
        duration_seconds=None,
        config={},
        node_execution={},
        metadata_json={},
    )
    data.update(overrides)
    return Run(**data)


def make_crawl_package(**overrides: dict) -> CrawlPackage:
    data = dict(
        run_id=uuid4(),
        status="completed",
        pages_visited=5,
        pages_skipped=0,
        total_links=10,
        crawl_depth_reached=2,
        bytes_downloaded=100000,
        duration_ms=5000,
        authenticated=False,
        auth_method=None,
        har_path=None,
        file_path=f"/tmp/crawl/{_unique_slug()}.json",
    )
    data.update(overrides)
    return CrawlPackage(**data)


def make_inventory(**overrides: dict) -> Inventory:
    data = dict(
        run_id=uuid4(),
        page_count=5,
        form_count=2,
        link_count=10,
        button_count=3,
        input_count=8,
        table_count=1,
        api_call_count=0,
        user_flow_count=1,
        screenshot_count=5,
        duplicate_pages_removed=0,
        duplicate_links_removed=1,
        authenticated=False,
        auth_method=None,
        pages_data=[],
        elements_data=[],
        navigation_data={},
        statistics={},
        errors=[],
        file_path=f"/tmp/inventory/{_unique_slug()}.json",
    )
    data.update(overrides)
    return Inventory(**data)


def make_test_plan(**overrides: dict) -> TestPlan:
    slug = _unique_slug()
    data = dict(
        run_id=uuid4(),
        version=1,
        is_latest=True,
        status="draft",
        model_used=None,
        llm_provider=None,
        prompt_version=None,
        prompt_hash=None,
        token_usage=None,
        prompt_latency_ms=None,
        estimated_cost=None,
        module_count=1,
        scenario_count=3,
        estimated_duration_minutes=15,
        coverage_summary={},
        application_summary={},
        json_path=f"/tmp/plans/{slug}.json",
        md_path=None,
        superseded_at=None,
    )
    data.update(overrides)
    return TestPlan(**data)


def make_test_scenario(**overrides: dict) -> TestScenario:
    data = dict(
        test_plan_id=uuid4(),
        scenario_id=_unique_slug("TC-"),
        title=_unique_slug("test_"),
        description="Test scenario description",
        priority="medium",
        category="functional",
        module_name=_unique_slug("module_"),
        target_page=None,
        risk_level="medium",
        preconditions=[],
        test_steps=["Step 1", "Step 2"],
        expected_result="Expected outcome",
        required_test_data=[],
        tags=["smoke"],
        dependencies=[],
        sort_order=0,
    )
    data.update(overrides)
    return TestScenario(**data)


def make_human_review(**overrides: dict) -> HumanReview:
    data = dict(
        run_id=uuid4(),
        test_plan_id=uuid4(),
        version=1,
        status="approved",
        decision="approve",
        reviewer_id=None,
        reviewer_name=_unique_slug("reviewer_"),
        reviewer_email=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
        duration_seconds=None,
        total_scenarios=5,
        approved_scenarios=5,
        rejected_scenarios=0,
        modified_scenarios=0,
        disabled_scenarios=0,
        decision_data={},
        general_comments=None,
        approval_summary=None,
        auto_approved=True,
        approved_plan_path=f"/tmp/review/{_unique_slug()}.json",
        approved_md_path=None,
        review_metadata_path=f"/tmp/review/{_unique_slug()}_meta.json",
    )
    data.update(overrides)
    return HumanReview(**data)


def make_ir_document(**overrides: dict) -> IRDocument:
    slug = _unique_slug()
    data = dict(
        test_plan_id=uuid4(),
        run_id=uuid4(),
        version=1,
        is_latest=True,
        ir_schema_version="1.0.0",
        valid=True,
        validation_errors=[],
        validation_warnings=[],
        refinement_attempts=0,
        total_pages=3,
        total_elements=10,
        total_flows=5,
        total_modules=2,
        model_used=None,
        llm_provider=None,
        prompt_version=None,
        token_usage=None,
        prompt_latency_ms=None,
        estimated_cost=None,
        ir_path=f"/tmp/ir/{slug}.json",
        dep_graph_path=None,
    )
    data.update(overrides)
    return IRDocument(**data)


def make_generated_project(**overrides: dict) -> GeneratedProject:
    slug = _unique_slug()
    data = dict(
        run_id=uuid4(),
        ir_document_id=None,
        status="completed",
        project_path=f"/tmp/gen/{slug}",
        ir_path=None,
        metadata_path=f"/tmp/gen/{slug}/metadata.json",
        files_data=[],
        files_generated=5,
        page_objects_count=3,
        test_files_count=2,
        scenarios_implemented=5,
        modules_covered=[],
        total_lines_of_code=200,
        validation_status="passed",
        validation_errors=0,
        validation_warnings=0,
        generation_duration_seconds=10.5,
        model_used=None,
        deleted_at=None,
    )
    data.update(overrides)
    return GeneratedProject(**data)


def make_execution(**overrides: dict) -> Execution:
    data = dict(
        run_id=uuid4(),
        project_id=None,
        triggered_by=None,
        trigger_type="api",
        environment_name=None,
        status="completed",
        browser="chromium",
        headless=True,
        config={},
        total_tests=10,
        tests_passed=8,
        tests_failed=2,
        tests_skipped=0,
        tests_flaky=0,
        pass_rate=80.0,
        total_duration_seconds=120.5,
        health_score=None,
        health_status=None,
        metrics_data={},
        playwright_exit_code=None,
        artifacts_path=f"/tmp/exec/artifacts/{_unique_slug()}",
        reports_path=f"/tmp/exec/reports/{_unique_slug()}",
        execution_logs=None,
        started_at=datetime.now(timezone.utc),
        completed_at=None,
    )
    data.update(overrides)
    return Execution(**data)


def make_test_result(**overrides: dict) -> TestResult:
    data = dict(
        execution_id=uuid4(),
        title=_unique_slug("test_"),
        file="tests/sample.spec.ts",
        line=10,
        status="passed",
        duration_ms=500.0,
        browser="chromium",
        retry_count=0,
        was_retried=False,
        original_status=None,
        error_message=None,
        error_stack=None,
        failure_data=None,
        retry_data=None,
        artifact_refs={},
        annotations=None,
    )
    data.update(overrides)
    return TestResult(**data)


def make_artifact(**overrides: dict) -> Artifact:
    data = dict(
        run_id=uuid4(),
        execution_id=None,
        test_result_id=None,
        artifact_type="screenshot",
        file_name=f"{_unique_slug()}.png",
        file_path=f"/tmp/artifacts/{_unique_slug()}.png",
        file_size_bytes=10240,
        mime_type="image/png",
        checksum=None,
        storage_backend="local",
        storage_config={},
        metadata_json={},
        deleted_at=None,
    )
    data.update(overrides)
    return Artifact(**data)


def make_audit_log(**overrides: dict) -> AuditLog:
    data = dict(
        tenant_id=UUID("00000000-0000-0000-0000-000000000001"),
        action="run.started",
        entity_type="run",
        entity_id=uuid4(),
        actor_id=None,
        actor_name=None,
        details={},
        ip_address=None,
        user_agent=None,
        correlation_id=None,
        created_at=datetime.now(timezone.utc),
    )
    data.update(overrides)
    return AuditLog(**data)

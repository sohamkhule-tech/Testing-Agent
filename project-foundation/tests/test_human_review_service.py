"""
Tests for Human Review Service
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from app.exceptions import ValidationError
from app.schemas.review import (
    ReviewDecision,
    ReviewRequest,
    ReviewStatus,
    ScenarioReviewStatus,
)
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


@pytest.fixture
async def review_service():
    """Create review service instance."""
    service = HumanReviewService()
    await service.initialize()
    yield service
    await service.cleanup()


@pytest.fixture
def sample_test_plan():
    """Create sample test plan."""
    run_id = str(uuid4())
    request_id = str(uuid4())
    
    return TestPlan(
        run_id=run_id,
        request_id=request_id,
        generated_at=datetime.now(timezone.utc),
        application_summary=ApplicationSummary(
            name="Test App",
            base_url="http://example.com",
            total_pages=5,
            total_forms=3,
            total_links=10,
        ),
        coverage_summary=CoverageSummary(
            total_scenarios=3,
            unique_user_flows=2,
            form_coverage_percentage=80.0,
            link_coverage_percentage=75.0,
        ),
        priorities=TestPriorities(
            high_priority_scenarios=1,
            medium_priority_scenarios=1,
            low_priority_scenarios=1,
        ),
        assumptions=TestAssumptions(
            assumptions=[
                "User has valid credentials",
                "Application is accessible",
            ],
        ),
        modules=[
            TestModule(
                name="Authentication",
                description="User authentication scenarios",
                scenarios=[
                    TestScenario(
                        metadata=ScenarioMetadata(
                            id="TC001",
                            title="Login with valid credentials",
                            description="Test user login with valid credentials",
                            priority=Priority.HIGH,
                            category=TestCategory.FUNCTIONAL,
                            module="Authentication",
                            expected_result="User is logged in successfully",
                        ),
                        steps=[
                            {"action": "Navigate to login page"},
                            {"action": "Enter username"},
                            {"action": "Enter password"},
                            {"action": "Click login button"},
                        ],
                        expected_outcome="User is logged in successfully",
                    ),
                    TestScenario(
                        metadata=ScenarioMetadata(
                            id="TC002",
                            title="Login with invalid credentials",
                            description="Test user login with invalid credentials",
                            priority=Priority.MEDIUM,
                            category=TestCategory.NEGATIVE,
                            module="Authentication",
                            expected_result="Error message is displayed",
                        ),
                        steps=[
                            {"action": "Navigate to login page"},
                            {"action": "Enter invalid username"},
                            {"action": "Enter invalid password"},
                            {"action": "Click login button"},
                        ],
                        expected_outcome="Error message is displayed",
                    ),
                ],
            ),
            TestModule(
                name="Registration",
                description="User registration scenarios",
                scenarios=[
                    TestScenario(
                        metadata=ScenarioMetadata(
                            id="TC003",
                            title="Register new user",
                            description="Test new user registration",
                            priority=Priority.LOW,
                            category=TestCategory.FUNCTIONAL,
                            module="Registration",
                            expected_result="User is registered successfully",
                        ),
                        steps=[
                            {"action": "Navigate to registration page"},
                            {"action": "Fill registration form"},
                            {"action": "Submit form"},
                        ],
                        expected_outcome="User is registered successfully",
                    ),
                ],
            ),
        ],
        test_scenarios=[],
    )


@pytest.fixture
def workspace_with_test_plan(tmp_path, sample_test_plan):
    """Create temporary workspace with test plan."""
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir(parents=True)
    
    test_plan_path = contracts_dir / "test-plan.json"
    test_plan_path.write_text(
        json.dumps(sample_test_plan.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    
    return tmp_path


@pytest.mark.asyncio
async def test_load_test_plan_success(review_service, workspace_with_test_plan):
    """Test successful test plan loading."""
    test_plan = await review_service.load_test_plan(str(workspace_with_test_plan))
    
    assert test_plan is not None
    assert test_plan.application_summary.name == "Test App"
    assert len(test_plan.modules) == 2


@pytest.mark.asyncio
async def test_load_test_plan_missing_workspace(review_service):
    """Test loading from non-existent workspace."""
    with pytest.raises(ValidationError, match="Workspace not found"):
        await review_service.load_test_plan("/non/existent/path")


@pytest.mark.asyncio
async def test_load_test_plan_missing_file(review_service, tmp_path):
    """Test loading when test plan file is missing."""
    with pytest.raises(ValidationError, match="Test plan not found"):
        await review_service.load_test_plan(str(tmp_path))


@pytest.mark.asyncio
async def test_auto_approve_review(review_service, workspace_with_test_plan):
    """Test auto-approve review workflow."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=True,
        general_comments="Auto-approved for testing",
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    assert result["success"] is True
    assert result["review_status"] == ReviewStatus.APPROVED.value
    assert result["review_decision"] == ReviewDecision.APPROVE.value
    assert result["approved_scenarios"] == 3
    assert result["total_scenarios"] == 3
    assert result["rejected_scenarios"] == 0
    
    # Check artifacts were created
    approved_plan_path = Path(result["approved_test_plan_path"])
    approved_md_path = Path(result["approved_test_plan_md_path"])
    metadata_path = Path(result["review_metadata_path"])
    
    assert approved_plan_path.exists()
    assert approved_md_path.exists()
    assert metadata_path.exists()


@pytest.mark.asyncio
async def test_partial_approval_review(review_service, workspace_with_test_plan):
    """Test partial approval workflow."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=False,
        scenario_decisions={
            "TC001": ScenarioReviewStatus.APPROVED,
            "TC002": ScenarioReviewStatus.REJECTED,
            "TC003": ScenarioReviewStatus.APPROVED,
        },
        general_comments="Partially approved",
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    assert result["success"] is True
    assert result["review_status"] == ReviewStatus.PARTIALLY_APPROVED.value
    assert result["review_decision"] == ReviewDecision.PARTIAL_APPROVAL.value
    assert result["approved_scenarios"] == 2
    assert result["rejected_scenarios"] == 1
    assert result["total_scenarios"] == 3


@pytest.mark.asyncio
async def test_reject_all_scenarios(review_service, workspace_with_test_plan):
    """Test rejecting all scenarios."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=False,
        scenario_decisions={
            "TC001": ScenarioReviewStatus.REJECTED,
            "TC002": ScenarioReviewStatus.REJECTED,
            "TC003": ScenarioReviewStatus.REJECTED,
        },
        general_comments="All scenarios rejected",
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    assert result["success"] is True
    assert result["review_status"] == ReviewStatus.REJECTED.value
    assert result["review_decision"] == ReviewDecision.REJECT.value
    assert result["approved_scenarios"] == 0
    assert result["rejected_scenarios"] == 3


@pytest.mark.asyncio
async def test_modified_scenarios(review_service, workspace_with_test_plan):
    """Test modified scenarios tracking."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=False,
        scenario_decisions={
            "TC001": ScenarioReviewStatus.MODIFIED,
            "TC002": ScenarioReviewStatus.APPROVED,
            "TC003": ScenarioReviewStatus.DISABLED,
        },
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    assert result["success"] is True
    assert result["review_status"] == ReviewStatus.PARTIALLY_APPROVED.value
    
    # Check metadata for modification counts
    metadata_path = Path(result["review_metadata_path"])
    metadata_data = json.loads(metadata_path.read_text(encoding="utf-8"))
    
    assert metadata_data["modified_scenarios"] == 1
    assert metadata_data["disabled_scenarios"] == 1


@pytest.mark.asyncio
async def test_approved_markdown_generation(review_service, workspace_with_test_plan):
    """Test approved markdown generation."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=True,
        general_comments="Test markdown generation",
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    md_path = Path(result["approved_test_plan_md_path"])
    md_content = md_path.read_text(encoding="utf-8")
    
    # Check markdown structure
    assert "# Approved Test Plan" in md_content
    assert "## Review Summary" in md_content
    assert "## Application Overview" in md_content
    assert "## Test Scenarios" in md_content
    assert "test_reviewer" in md_content
    assert "Test markdown generation" in md_content


@pytest.mark.asyncio
async def test_review_metadata_structure(review_service, workspace_with_test_plan):
    """Test review metadata structure."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=True,
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    metadata_path = Path(result["review_metadata_path"])
    metadata_data = json.loads(metadata_path.read_text(encoding="utf-8"))
    
    # Check required fields
    assert "run_id" in metadata_data
    assert "review_version" in metadata_data
    assert "review_status" in metadata_data
    assert "reviewer_name" in metadata_data
    assert "reviewer_email" in metadata_data
    assert "review_started_at" in metadata_data
    assert "review_completed_at" in metadata_data
    assert "decision" in metadata_data
    assert "total_scenarios" in metadata_data
    assert "approved_scenarios" in metadata_data
    
    assert metadata_data["review_version"] == 1
    assert metadata_data["reviewer_name"] == "test_reviewer"


@pytest.mark.asyncio
async def test_versioning_initialization(review_service, workspace_with_test_plan):
    """Test that review version starts at 1."""
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=True,
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    assert result["review_version"] == 1


@pytest.mark.asyncio
async def test_invalid_test_plan_handling(review_service, tmp_path):
    """Test handling of invalid test plan data."""
    contracts_dir = tmp_path / "contracts"
    contracts_dir.mkdir(parents=True)
    
    test_plan_path = contracts_dir / "test-plan.json"
    test_plan_path.write_text('{"invalid": "data"}', encoding="utf-8")
    
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=True,
    )
    
    with pytest.raises(ValidationError, match="Review processing failed"):
        await review_service.review_test_plan(
            workspace_path=str(tmp_path),
            review_request=review_request,
        )


@pytest.mark.asyncio
async def test_general_comments_in_metadata(review_service, workspace_with_test_plan):
    """Test that general comments are included in metadata."""
    comment_text = "This is a test comment"
    
    review_request = ReviewRequest(
        run_id=str(uuid4()),
        reviewer_name="test_reviewer",
        reviewer_email="reviewer@example.com",
        auto_approve=True,
        general_comments=comment_text,
    )
    
    result = await review_service.review_test_plan(
        workspace_path=str(workspace_with_test_plan),
        review_request=review_request,
    )
    
    metadata_path = Path(result["review_metadata_path"])
    metadata_data = json.loads(metadata_path.read_text(encoding="utf-8"))
    
    assert metadata_data["approval_summary"] == comment_text
    assert len(metadata_data["general_comments"]) == 1
    assert metadata_data["general_comments"][0]["comment_text"] == comment_text

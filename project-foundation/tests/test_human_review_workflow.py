"""
Integration Tests for Human Review Workflow
"""

from pathlib import Path

import pytest

from app.agents import CrawlerAgent, TestDesignAgent, TriggerAgent
from app.constants import RunStatus
from app.dependencies import (
    get_browser_manager,
    get_crawler_agent,
    get_human_review_service,
    get_test_design_agent,
    get_trigger_agent,
)
from app.schemas.review import ReviewStatus
from app.workflows.trigger_workflow import execute_platform_workflow


@pytest.fixture
async def agents():
    """Initialize agents for testing."""
    trigger_agent = get_trigger_agent()
    crawler_agent = get_crawler_agent()
    test_design_agent = get_test_design_agent()
    
    # Initialize browser manager
    browser_manager = get_browser_manager()
    await browser_manager.initialize()
    
    yield trigger_agent, crawler_agent, test_design_agent
    
    # Cleanup
    await browser_manager.cleanup()


@pytest.mark.asyncio
async def test_workflow_with_human_review(agents):
    """Test complete workflow including human review node."""
    trigger_agent, crawler_agent, test_design_agent = agents
    
    request_data = {
        "target_application": {
            "name": "Test Application",
            "base_url": "http://example.com",
            "starting_urls": ["http://example.com"],
        },
        "execution_config": {
            "max_pages": 2,
            "max_depth": 1,
            "timeout_seconds": 30,
        },
    }
    
    result = await execute_platform_workflow(
        trigger_agent=trigger_agent,
        crawler_agent=crawler_agent,
        request_data=request_data,
        requested_by="test_user",
        test_design_agent=test_design_agent,
    )
    
    # Check workflow completion
    assert result["success"] is True
    assert result["status"] == RunStatus.COMPLETED.value
    
    # Check review artifacts
    assert "review_status" in result
    assert "review_decision" in result
    assert "approved_test_plan_path" in result
    assert "approved_test_plan_md_path" in result
    assert "review_metadata_path" in result
    
    # Verify review was auto-approved
    assert result["review_status"] == ReviewStatus.APPROVED.value
    
    # Verify artifacts exist
    workspace_path = Path(result["workspace_path"])
    approved_plan = workspace_path / "contracts" / "approved-test-plan.json"
    approved_md = workspace_path / "contracts" / "approved-test-plan.md"
    review_metadata = workspace_path / "contracts" / "review-metadata.json"
    
    assert approved_plan.exists()
    assert approved_md.exists()
    assert review_metadata.exists()


@pytest.mark.asyncio
async def test_workflow_review_node_in_results(agents):
    """Test that review node results are included in workflow output."""
    trigger_agent, crawler_agent, test_design_agent = agents
    
    request_data = {
        "target_application": {
            "name": "Test Application",
            "base_url": "http://example.com",
            "starting_urls": ["http://example.com"],
        },
        "execution_config": {
            "max_pages": 2,
            "max_depth": 1,
        },
    }
    
    result = await execute_platform_workflow(
        trigger_agent=trigger_agent,
        crawler_agent=crawler_agent,
        request_data=request_data,
        requested_by="test_user",
        test_design_agent=test_design_agent,
    )
    
    # Check review node result exists
    assert "review" in result
    assert result["review"] is not None
    
    # Check review result structure
    review_result = result["review"]
    assert "success" in review_result
    assert "review_status" in review_result
    assert "approved_scenarios" in review_result
    assert "total_scenarios" in review_result


@pytest.mark.asyncio
async def test_human_review_service_initialization():
    """Test human review service can be initialized."""
    service = get_human_review_service()
    assert service is not None
    
    await service.initialize()
    await service.cleanup()


@pytest.mark.asyncio
async def test_workflow_creates_all_phase_6_artifacts(agents):
    """Test that all Phase 6 artifacts are created."""
    trigger_agent, crawler_agent, test_design_agent = agents
    
    request_data = {
        "target_application": {
            "name": "Test Application",
            "base_url": "http://example.com",
            "starting_urls": ["http://example.com"],
        },
        "execution_config": {
            "max_pages": 2,
            "max_depth": 1,
        },
    }
    
    result = await execute_platform_workflow(
        trigger_agent=trigger_agent,
        crawler_agent=crawler_agent,
        request_data=request_data,
        requested_by="test_user",
        test_design_agent=test_design_agent,
    )
    
    workspace = Path(result["workspace_path"])
    contracts_dir = workspace / "contracts"
    
    # Check all Phase 6 artifacts
    assert (contracts_dir / "approved-test-plan.json").exists()
    assert (contracts_dir / "approved-test-plan.md").exists()
    assert (contracts_dir / "review-metadata.json").exists()
    
    # Also verify Phase 5 artifacts still exist
    assert (contracts_dir / "test-plan.json").exists()
    assert (contracts_dir / "test-plan.md").exists()

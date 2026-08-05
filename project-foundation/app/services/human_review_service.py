"""
Human Review Service

Business logic for human review and approval workflow.
"""

from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from app.core.interfaces import IService
from app.exceptions import ValidationError
from app.logging import LoggerMixin
from app.schemas.review import (
    ApprovedTestPlan,
    ReviewComment,
    ReviewDecision,
    ReviewMetadata,
    ReviewRequest,
    ReviewStatus,
    ScenarioReview,
    ScenarioReviewStatus,
)
from app.schemas.test_plan import TestPlan
from app.utils import load_file, save_file


class HumanReviewService(IService, LoggerMixin):
    """
    Human review service for test plan approval workflow.
    
    Responsibilities:
    - Load AI-generated test plans
    - Apply human reviewer decisions
    - Track review versions
    - Persist approved artifacts
    - Generate review metadata
    
    No AI/LLM logic - deterministic review processing only.
    """

    def __init__(self) -> None:
        """Initialize human review service."""
        super().__init__()

    async def initialize(self) -> None:
        """Initialize service resources."""
        self.logger.info("human_review_service_initializing")
        self.logger.info("human_review_service_initialized")

    async def cleanup(self) -> None:
        """Cleanup service resources."""
        self.logger.info("human_review_service_cleaning_up")
        self.logger.info("human_review_service_cleaned_up")

    async def load_test_plan(self, workspace_path: str) -> TestPlan:
        """
        Load AI-generated test plan from workspace.

        Args:
            workspace_path: Run workspace directory path

        Returns:
            Validated TestPlan

        Raises:
            ValidationError: If test plan is missing or invalid
        """
        workspace = Path(workspace_path)
        if not workspace.exists():
            raise ValidationError(f"Workspace not found: {workspace_path}")

        test_plan_path = workspace / "contracts" / "test-plan.json"
        if not test_plan_path.exists():
            raise ValidationError(f"Test plan not found: {test_plan_path}")

        try:
            data = await load_file(test_plan_path)
            return TestPlan(**data)
        except Exception as e:
            raise ValidationError(f"Invalid test plan: {str(e)}")

    async def review_test_plan(
        self,
        workspace_path: str,
        review_request: ReviewRequest,
    ) -> dict:
        """
        Process human review of test plan.

        Args:
            workspace_path: Run workspace directory path
            review_request: Review request with reviewer decisions

        Returns:
            Review result with paths to approved artifacts

        Raises:
            ValidationError: If review processing fails
        """
        try:
            self.logger.info(
                "review_started",
                run_id=str(review_request.run_id),
                reviewer=review_request.reviewer_name,
            )

            review_start_time = datetime.now(timezone.utc)

            # Load test plan
            test_plan = await self.load_test_plan(workspace_path)

            # Build scenario reviews
            scenario_reviews = self._build_scenario_reviews(
                test_plan,
                review_request.scenario_decisions or {},
            )

            # Calculate review statistics
            stats = self._calculate_review_stats(scenario_reviews)

            # Determine review status and decision
            review_status, review_decision = self._determine_review_outcome(
                review_request.auto_approve,
                scenario_reviews,
            )

            review_completed_time = datetime.now(timezone.utc)
            review_duration = int((review_completed_time - review_start_time).total_seconds())

            # Build review metadata
            review_metadata = ReviewMetadata(
                run_id=review_request.run_id,
                request_id=test_plan.request_id,
                review_version=1,  # TODO: Implement versioning
                review_status=review_status,
                reviewer_name=review_request.reviewer_name,
                reviewer_email=review_request.reviewer_email,
                review_started_at=review_start_time,
                review_completed_at=review_completed_time,
                approval_date=review_completed_time if review_status == ReviewStatus.APPROVED else None,
                decision=review_decision,
                review_duration_seconds=review_duration,
                total_scenarios=stats["total"],
                approved_scenarios=stats["approved"],
                rejected_scenarios=stats["rejected"],
                modified_scenarios=stats["modified"],
                disabled_scenarios=stats["disabled"],
                approval_summary=review_request.general_comments,
            )

            # Add general comments if provided
            if review_request.general_comments:
                review_metadata.general_comments.append(
                    ReviewComment(
                        comment_id=uuid4(),
                        reviewer_name=review_request.reviewer_name,
                        reviewer_email=review_request.reviewer_email,
                        comment_text=review_request.general_comments,
                        created_at=review_completed_time,
                    )
                )

            # Build approved test plan
            approved_plan = ApprovedTestPlan(
                run_id=test_plan.run_id,
                request_id=test_plan.request_id,
                generated_at=test_plan.generated_at,
                approved_at=review_completed_time,
                review_version=1,
                review_status=review_status,
                reviewer_name=review_request.reviewer_name,
                test_plan_data=test_plan.model_dump(mode="json"),
                scenario_reviews=scenario_reviews,
            )

            # Persist approved artifacts
            approved_plan_path = await self._persist_approved_plan(workspace_path, approved_plan, test_plan)
            approved_md_path = await self._generate_approved_markdown(workspace_path, test_plan, review_metadata)
            metadata_path = await self._persist_review_metadata(workspace_path, review_metadata)

            self.logger.info(
                "review_completed",
                run_id=str(review_request.run_id),
                status=review_status.value,
                decision=review_decision.value if review_decision else None,
                approved_scenarios=stats["approved"],
                rejected_scenarios=stats["rejected"],
            )

            return {
                "success": True,
                "run_id": str(review_request.run_id),
                "review_status": review_status.value,
                "review_decision": review_decision.value if review_decision else None,
                "approved_test_plan_path": approved_plan_path,
                "approved_test_plan_md_path": approved_md_path,
                "review_metadata_path": metadata_path,
                "review_version": 1,
                "reviewer_name": review_request.reviewer_name,
                "approved_scenarios": stats["approved"],
                "rejected_scenarios": stats["rejected"],
                "total_scenarios": stats["total"],
            }

        except Exception as e:
            self.logger.error("review_failed", error=str(e))
            raise ValidationError(f"Review processing failed: {str(e)}")

    def _build_scenario_reviews(
        self,
        test_plan: TestPlan,
        scenario_decisions: dict[str, ScenarioReviewStatus],
    ) -> dict[str, ScenarioReview]:
        """Build scenario review records."""
        scenario_reviews = {}
        
        # Extract scenarios from test_scenarios or modules
        all_scenarios = test_plan.test_scenarios if test_plan.test_scenarios else []
        if not all_scenarios:
            # Extract from modules if test_scenarios is empty
            for module in test_plan.modules:
                all_scenarios.extend(module.scenarios)
        
        for scenario in all_scenarios:
            scenario_id = scenario.metadata.id
            decision = scenario_decisions.get(scenario_id, ScenarioReviewStatus.APPROVED)
            
            scenario_reviews[scenario_id] = ScenarioReview(
                scenario_id=scenario_id,
                status=decision,
                enabled=decision != ScenarioReviewStatus.REJECTED and decision != ScenarioReviewStatus.DISABLED,
                modified=decision == ScenarioReviewStatus.MODIFIED,
            )
        
        return scenario_reviews

    def _calculate_review_stats(self, scenario_reviews: dict[str, ScenarioReview]) -> dict:
        """Calculate review statistics."""
        stats = {
            "total": len(scenario_reviews),
            "approved": 0,
            "rejected": 0,
            "modified": 0,
            "disabled": 0,
        }
        
        for review in scenario_reviews.values():
            if review.status == ScenarioReviewStatus.APPROVED:
                stats["approved"] += 1
            elif review.status == ScenarioReviewStatus.REJECTED:
                stats["rejected"] += 1
            elif review.status == ScenarioReviewStatus.MODIFIED:
                stats["modified"] += 1
            elif review.status == ScenarioReviewStatus.DISABLED:
                stats["disabled"] += 1
        
        return stats

    def _determine_review_outcome(
        self,
        auto_approve: bool,
        scenario_reviews: dict[str, ScenarioReview],
    ) -> tuple[ReviewStatus, ReviewDecision]:
        """Determine final review status and decision."""
        if auto_approve:
            return ReviewStatus.APPROVED, ReviewDecision.APPROVE
        
        stats = self._calculate_review_stats(scenario_reviews)
        
        # Count enabled scenarios (approved + modified)
        enabled_count = stats["approved"] + stats["modified"]
        disabled_count = stats["rejected"] + stats["disabled"]
        
        if disabled_count == stats["total"]:
            # All scenarios rejected or disabled
            return ReviewStatus.REJECTED, ReviewDecision.REJECT
        elif stats["approved"] == stats["total"]:
            # All scenarios approved without modification
            return ReviewStatus.APPROVED, ReviewDecision.APPROVE
        elif enabled_count > 0 and disabled_count > 0:
            # Mix of enabled and disabled
            return ReviewStatus.PARTIALLY_APPROVED, ReviewDecision.PARTIAL_APPROVAL
        elif stats["modified"] > 0:
            # Some scenarios modified
            return ReviewStatus.PARTIALLY_APPROVED, ReviewDecision.PARTIAL_APPROVAL
        else:
            return ReviewStatus.UNDER_REVIEW, ReviewDecision.REQUEST_CHANGES

    async def _persist_approved_plan(
        self,
        workspace_path: str,
        approved_plan: ApprovedTestPlan,
        original_plan: TestPlan,
    ) -> str:
        """Persist approved test plan."""
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "approved-test-plan.json"

        approved_data = approved_plan.model_dump(mode="json")
        approved_data["test_plan_data"] = original_plan.model_dump(mode="json")

        await save_file(output_path, approved_data)
        
        self.logger.info(
            "approved_plan_persisted",
            path=str(output_path),
        )
        
        return str(output_path)

    async def _generate_approved_markdown(
        self,
        workspace_path: str,
        test_plan: TestPlan,
        review_metadata: ReviewMetadata,
    ) -> str:
        """Generate approved test plan markdown."""
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "approved-test-plan.md"

        markdown_content = self._build_approved_markdown(test_plan, review_metadata)
        output_path.write_text(markdown_content, encoding="utf-8")
        
        self.logger.info(
            "approved_markdown_generated",
            path=str(output_path),
        )
        
        return str(output_path)

    def _build_approved_markdown(self, test_plan: TestPlan, review_metadata: ReviewMetadata) -> str:
        """Build approved markdown content."""
        lines = []
        
        lines.append("# Approved Test Plan")
        lines.append("")
        lines.append(f"**Status:** {review_metadata.review_status.value}")
        lines.append(f"**Reviewer:** {review_metadata.reviewer_name}")
        lines.append(f"**Approved:** {review_metadata.approval_date.strftime('%Y-%m-%d %H:%M:%S UTC') if review_metadata.approval_date else 'N/A'}")
        lines.append(f"**Review Version:** {review_metadata.review_version}")
        lines.append("")
        
        lines.append("## Review Summary")
        lines.append("")
        lines.append(f"- **Total Scenarios:** {review_metadata.total_scenarios}")
        lines.append(f"- **Approved:** {review_metadata.approved_scenarios}")
        lines.append(f"- **Rejected:** {review_metadata.rejected_scenarios}")
        lines.append(f"- **Modified:** {review_metadata.modified_scenarios}")
        lines.append(f"- **Disabled:** {review_metadata.disabled_scenarios}")
        lines.append("")
        
        if review_metadata.approval_summary:
            lines.append("## Approval Notes")
            lines.append("")
            lines.append(review_metadata.approval_summary)
            lines.append("")
        
        lines.append("## Application Overview")
        lines.append("")
        app_sum = test_plan.application_summary
        lines.append(f"- **Application:** {app_sum.name}")
        lines.append(f"- **Total Pages:** {app_sum.total_pages}")
        lines.append(f"- **Total Forms:** {app_sum.total_forms}")
        lines.append("")
        
        lines.append("## Test Scenarios")
        lines.append("")
        for module in test_plan.modules:
            lines.append(f"### {module.name}")
            lines.append("")
            for scenario in module.scenarios:
                meta = scenario.metadata
                lines.append(f"#### {meta.id}: {meta.title}")
                lines.append(f"- **Priority:** {meta.priority}")
                lines.append(f"- **Category:** {meta.category}")
                lines.append("")
        
        return "\n".join(lines)

    async def _persist_review_metadata(
        self,
        workspace_path: str,
        review_metadata: ReviewMetadata,
    ) -> str:
        """Persist review metadata."""
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "review-metadata.json"

        data = review_metadata.model_dump(mode="json")
        await save_file(output_path, data)
        
        self.logger.info(
            "review_metadata_persisted",
            path=str(output_path),
        )
        
        return str(output_path)

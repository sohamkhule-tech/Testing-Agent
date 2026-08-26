"""
Human Review Service

Business logic for human review and approval workflow.
"""

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
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

            # Build approved test plan. For a PARTIAL (or non-fully-approved)
            # review the persisted plan reflects ONLY the approved scenarios so
            # every downstream consumer (code generation, reports, UI) sees the
            # exact approved subset — never the original full plan.
            plan_data = test_plan.model_dump(mode="json")
            enabled_ids = {
                scenario_id
                for scenario_id, review in scenario_reviews.items()
                if review.status
                in (ScenarioReviewStatus.APPROVED, ScenarioReviewStatus.MODIFIED)
            }
            if review_status != ReviewStatus.APPROVED and enabled_ids:
                plan_data = self._scope_plan_data(plan_data, enabled_ids)

            approved_plan = ApprovedTestPlan(
                run_id=test_plan.run_id,
                request_id=test_plan.request_id,
                generated_at=test_plan.generated_at,
                approved_at=review_completed_time,
                review_version=1,
                review_status=review_status,
                reviewer_name=review_request.reviewer_name,
                test_plan_data=plan_data,
                scenario_reviews=scenario_reviews,
            )

            # Persist approved artifacts
            approved_plan_path = await self._persist_approved_plan(workspace_path, approved_plan, test_plan)
            approved_md_path = await self._generate_approved_markdown(workspace_path, plan_data, review_metadata)
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
        """Determine final review status and decision.

        Rules:
        * ``auto_approve`` short-circuits to APPROVED (legacy behaviour).
        * All scenarios rejected/disabled → REJECTED.
        * Every scenario approved → APPROVED.
        * Some (but not all) scenarios approved/modified, or a mix of enabled and
          disabled → PARTIALLY_APPROVED. Scenarios left ``PENDING`` (not yet
          reviewed) therefore produce a PARTIALLY_APPROVED review when at least
          one scenario has a positive decision — the plan is NOT stamped approved
          merely because some test cases were approved.
        * Nothing decided yet → UNDER_REVIEW.
        """
        if auto_approve:
            return ReviewStatus.APPROVED, ReviewDecision.APPROVE

        stats = self._calculate_review_stats(scenario_reviews)

        # Count enabled scenarios (approved + modified)
        enabled_count = stats["approved"] + stats["modified"]
        disabled_count = stats["rejected"] + stats["disabled"]
        pending_count = stats["total"] - enabled_count - disabled_count

        if disabled_count == stats["total"]:
            # All scenarios rejected or disabled
            return ReviewStatus.REJECTED, ReviewDecision.REJECT
        if stats["approved"] == stats["total"]:
            # Every scenario approved without modification
            return ReviewStatus.APPROVED, ReviewDecision.APPROVE
        if stats["approved"] > 0 or stats["modified"] > 0 or (enabled_count > 0 and disabled_count > 0):
            # Any mix of approved/modified with pending or disabled scenarios.
            # A selective approval (some approved, others pending) is PARTIAL —
            # never treated as a full plan approval.
            return ReviewStatus.PARTIALLY_APPROVED, ReviewDecision.PARTIAL_APPROVAL
        if pending_count > 0:
            # Nothing approved/modified yet — review is still in progress.
            return ReviewStatus.UNDER_REVIEW, ReviewDecision.REQUEST_CHANGES
        return ReviewStatus.UNDER_REVIEW, ReviewDecision.REQUEST_CHANGES

    async def approve_selected_scenarios(
        self,
        workspace_path: str,
        run_id: UUID,
        reviewer_name: str,
        scenario_ids: list[str],
    ) -> dict:
        """Approve ONLY the given scenario IDs; every other scenario stays pending.

        Args:
            workspace_path: Run workspace directory path
            run_id: Test run identifier
            reviewer_name: Person approving the selection
            scenario_ids: Scenario/test-case IDs to approve (subset of the plan)

        Returns:
            The review result from :meth:`review_test_plan` (approved-state dict).

        Raises:
            ValidationError: When an ID does not belong to the run's test plan.
        """
        test_plan = await self.load_test_plan(workspace_path)

        valid_ids: set[str] = set()
        for scenario in test_plan.test_scenarios or []:
            valid_ids.add(scenario.metadata.id)
        if not valid_ids:
            for module in test_plan.modules:
                for scenario in module.scenarios:
                    valid_ids.add(scenario.metadata.id)
        if not valid_ids:
            raise ValidationError("Test plan contains no test scenarios to approve.")

        selected = set(dict.fromkeys(scenario_ids))  # preserve order, drop dups
        invalid = sorted(selected - valid_ids)
        if invalid:
            raise ValidationError(
                f"Test-case IDs do not belong to this run's test plan: {invalid}"
            )

        # Explicit decision for EVERY scenario: selected → APPROVED; all others
        # stay PENDING so a partial approval is never turned into a full one.
        decisions = {
            scenario_id: (
                ScenarioReviewStatus.APPROVED
                if scenario_id in selected
                else ScenarioReviewStatus.PENDING
            )
            for scenario_id in valid_ids
        }

        review_request = ReviewRequest(
            run_id=run_id,
            reviewer_name=reviewer_name,
            reviewer_email=None,
            auto_approve=False,
            scenario_decisions=decisions,
            general_comments=(
                f"Selective approval: {len(selected)} of {len(valid_ids)} "
                "scenario(s) approved."
            ),
        )

        result = await self.review_test_plan(workspace_path, review_request)
        result["approved_test_case_ids"] = sorted(selected)
        return result

    SCOPED_CODEGEN_PLAN_FILENAME = "codegen-scoped-plan.json"

    async def resolve_codegen_test_plan_path(
        self,
        workspace_path: str,
        canonical_path: str | None = None,
    ) -> str | None:
        """Resolve the test-plan file that Code Generation should consume.

        The persisted Human Review decision is the source of truth:

        * No review decision yet, or the review is FULLY approved → return the
          canonical ``approved-test-plan.json`` unchanged (legacy behaviour —
          all scenarios may proceed).
        * PARTIALLY_APPROVED → write a SCOPED COPY containing ONLY the approved
          scenarios and return its path. The original persisted plan is NEVER
          mutated; full scenario metadata is preserved on the copy.
        * An existing review with ZERO approved scenarios → return ``None`` so
          the caller does NOT start Code Generation or Test Execution.

        Args:
            workspace_path: Run workspace directory path
            canonical_path: Canonical approved-plan path (defaults to
                ``<workspace>/contracts/approved-test-plan.json``).

        Returns:
            Path to feed Code Generation, or ``None`` when nothing is approved.
        """
        contracts = Path(workspace_path) / "contracts"
        if canonical_path:
            canonical = Path(canonical_path)
            if not canonical.is_absolute():
                canonical = Path(workspace_path) / canonical
        else:
            canonical = contracts / "approved-test-plan.json"

        # When no scoping applies we return the caller's canonical path verbatim
        # (never re-normalising it) so legacy flows behave exactly as before.
        def _legacy_path() -> str:
            return canonical_path or str(canonical)

        # No persisted review decision → preserve the existing (unscoped) path.
        metadata_path = contracts / "review-metadata.json"
        if not metadata_path.exists():
            return _legacy_path()

        try:
            metadata = await load_file(metadata_path)
        except Exception:
            return _legacy_path()
        review_status = metadata.get("review_status") if isinstance(metadata, dict) else None

        if review_status in ("approved", "draft", "archived"):
            # Fully approved (or no active review) → every scenario may proceed.
            return _legacy_path()

        if not canonical.exists():
            # No approved plan file yet — let downstream decide as before.
            return _legacy_path()

        try:
            data = await load_file(canonical)
        except Exception:
            return _legacy_path()
        if not isinstance(data, dict):
            return _legacy_path()

        scenario_reviews = data.get("scenario_reviews") or {}
        approved_ids = {
            rid
            for rid, rv in scenario_reviews.items()
            if isinstance(rv, dict) and rv.get("status") in ("approved", "modified")
        }
        if not approved_ids:
            # A review decision exists but nothing is approved → stop.
            return None

        plan_data = data.get("test_plan_data")
        if not isinstance(plan_data, dict):
            return _legacy_path()
        scenarios = plan_data.get("test_scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            # Plan shape we do not scope (module-only plans) → legacy behaviour.
            return _legacy_path()

        def _scenario_id(scenario: Any) -> str | None:
            if isinstance(scenario, dict):
                meta = scenario.get("metadata")
                if isinstance(meta, dict) and meta.get("id"):
                    return str(meta["id"])
                if meta is not None and hasattr(meta, "id") and meta.id:
                    return str(meta.id)
                return str(scenario["id"]) if scenario.get("id") else None
            meta = getattr(scenario, "metadata", None)
            value = (meta.id if meta is not None and hasattr(meta, "id") else None) or getattr(scenario, "id", None)
            return str(value) if value else None

        filtered = [s for s in scenarios if _scenario_id(s) in approved_ids]
        if not filtered:
            return None

        # Scoped COPY — the persisted source of truth is never mutated.
        scoped = deepcopy(data)
        scoped_tp = scoped["test_plan_data"]
        scoped_tp["test_scenarios"] = filtered

        # Keep module lists consistent for any module-based downstream consumer,
        # dropping modules that end up with zero approved scenarios.
        modules = scoped_tp.get("modules")
        if isinstance(modules, list):
            new_modules: list[Any] = []
            for mod in modules:
                if not isinstance(mod, dict):
                    new_modules.append(mod)
                    continue
                mod_scenarios = mod.get("scenarios")
                if isinstance(mod_scenarios, list):
                    kept = [s for s in mod_scenarios if _scenario_id(s) in approved_ids]
                    kept_mod = dict(mod)
                    kept_mod["scenarios"] = kept
                    if kept or not mod_scenarios:
                        new_modules.append(kept_mod)
                else:
                    new_modules.append(mod)
            scoped_tp["modules"] = new_modules

        coverage = scoped_tp.get("coverage_summary")
        if isinstance(coverage, dict):
            coverage["total_scenarios"] = len(filtered)
        if "total_scenarios" in scoped_tp:
            scoped_tp["total_scenarios"] = len(filtered)

        out_path = contracts / self.SCOPED_CODEGEN_PLAN_FILENAME
        await save_file(out_path, scoped)
        self.logger.info(
            "codegen_scoped_plan_written",
            path=str(out_path),
            approved=len(filtered),
            total=len(scenarios),
            review_status=review_status,
        )
        return str(out_path)

    async def _persist_approved_plan(
        self,
        workspace_path: str,
        approved_plan: ApprovedTestPlan,
        original_plan: TestPlan,
    ) -> str:
        """Persist approved test plan.

        The persisted ``test_plan_data`` is the APPROVED plan exactly as built
        (for a partial review that means ONLY the approved scenarios) — it is
        never re-expanded to the original full plan.
        """
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "approved-test-plan.json"

        approved_data = approved_plan.model_dump(mode="json")
        await save_file(output_path, approved_data)

        self.logger.info(
            "approved_plan_persisted",
            path=str(output_path),
            scenario_count=len((approved_data.get("test_plan_data") or {}).get("test_scenarios") or []),
        )

        return str(output_path)

    def _scope_plan_data(
        self,
        plan_data: dict[str, Any],
        kept_ids: set[str],
    ) -> dict[str, Any]:
        """Return a copy of ``plan_data`` containing ONLY the ``kept_ids`` scenarios.

        Used to persist an approved plan scoped to the approved scenarios for a
        partial review. ``plan_data`` itself is never mutated.
        """
        data = deepcopy(plan_data)

        def _sid(scenario: Any) -> str | None:
            if isinstance(scenario, dict):
                meta = scenario.get("metadata")
                if isinstance(meta, dict) and meta.get("id"):
                    return str(meta["id"])
                return str(scenario["id"]) if scenario.get("id") else None
            meta = getattr(scenario, "metadata", None)
            value = (meta.id if meta is not None and hasattr(meta, "id") else None) or getattr(scenario, "id", None)
            return str(value) if value else None

        scenarios = data.get("test_scenarios")
        if isinstance(scenarios, list):
            data["test_scenarios"] = [s for s in scenarios if _sid(s) in kept_ids]

        modules = data.get("modules")
        if isinstance(modules, list):
            new_modules: list[Any] = []
            for mod in modules:
                if not isinstance(mod, dict):
                    new_modules.append(mod)
                    continue
                mod_scenarios = mod.get("scenarios")
                if isinstance(mod_scenarios, list):
                    kept = [s for s in mod_scenarios if _sid(s) in kept_ids]
                    kept_mod = dict(mod)
                    kept_mod["scenarios"] = kept
                    if kept or not mod_scenarios:
                        new_modules.append(kept_mod)
                else:
                    new_modules.append(mod)
            data["modules"] = new_modules

        kept_count = len(data.get("test_scenarios") or [])
        coverage = data.get("coverage_summary")
        if isinstance(coverage, dict):
            coverage["total_scenarios"] = kept_count
        if "total_scenarios" in data:
            data["total_scenarios"] = kept_count

        return data

    async def _generate_approved_markdown(
        self,
        workspace_path: str,
        plan_data: dict[str, Any],
        review_metadata: ReviewMetadata,
    ) -> str:
        """Generate approved test plan markdown from the scoped plan data."""
        contracts_dir = Path(workspace_path) / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)
        output_path = contracts_dir / "approved-test-plan.md"

        markdown_content = self._build_approved_markdown(plan_data, review_metadata)
        output_path.write_text(markdown_content, encoding="utf-8")

        self.logger.info(
            "approved_markdown_generated",
            path=str(output_path),
        )

        return str(output_path)

    def _build_approved_markdown(self, plan_data: dict[str, Any], review_metadata: ReviewMetadata) -> str:
        """Build approved markdown content (``plan_data`` is scoped to approved)."""
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
        app_sum = plan_data.get("application_summary") or {}
        lines.append(f"- **Application:** {app_sum.get('name', 'Unknown')}")
        lines.append(f"- **Total Pages:** {app_sum.get('total_pages', 0)}")
        lines.append(f"- **Total Forms:** {app_sum.get('total_forms', 0)}")
        lines.append("")

        lines.append("## Test Scenarios")
        lines.append("")
        for module in plan_data.get("modules") or []:
            if not isinstance(module, dict):
                continue
            lines.append(f"### {module.get('name', 'Unknown')}")
            lines.append("")
            for scenario in module.get("scenarios") or []:
                if isinstance(scenario, dict):
                    meta = scenario.get("metadata") or {}
                else:
                    meta = getattr(scenario, "metadata", None)
                    meta = meta.model_dump(mode="json") if hasattr(meta, "model_dump") else (meta or {})
                lines.append(f"#### {meta.get('id', '')}: {meta.get('title', '')}")
                lines.append(f"- **Priority:** {meta.get('priority', '')}")
                lines.append(f"- **Category:** {meta.get('category', '')}")
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

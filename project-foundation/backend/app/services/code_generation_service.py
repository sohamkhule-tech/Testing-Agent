"""
Code Generation Service

Business logic for AI-powered code generation.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

from app.agents.code_generation_agent import CodeGenerationAgent
from app.core.interfaces import ILLMClient, IService
from app.exceptions import ValidationError
from app.logging import LoggerMixin
from app.schemas.code_generation import CodeGenerationResult, CodeGenerationStatus
from app.utils import load_file


class CodeGenerationService(IService, LoggerMixin):
    """
    Code generation service for Playwright test automation.
    
    Responsibilities:
    - Validate workspace and approved test plan
    - Invoke CodeGenerationAgent
    - Handle generation failures
    - Return generation summary
    - No execution logic (that's Phase 8)
    
    Deterministic except for LLM-based code generation.
    """

    def __init__(self, llm_client: ILLMClient) -> None:
        """
        Initialize code generation service.

        Args:
            llm_client: LLM client for code generation
        """
        super().__init__()
        self.llm_client = llm_client
        self.agent: CodeGenerationAgent | None = None

    async def initialize(self) -> None:
        """Initialize service resources."""
        self.logger.info("code_generation_service_initializing")
        
        # Initialize agent
        self.agent = CodeGenerationAgent(llm_client=self.llm_client)
        
        self.logger.info("code_generation_service_initialized")

    async def generate_tests(
        self,
        run_id: UUID | str,
        workspace_path: str,
        base_url: str = "http://localhost:3000",
    ) -> dict[str, Any]:
        """
        Generate Playwright test automation from approved test plan.

        Args:
            run_id: Workflow run ID
            workspace_path: Workspace directory path
            base_url: Application base URL

        Returns:
            Dictionary with generation summary

        Raises:
            ValidationError: If validation fails
        """
        start_time = datetime.now(timezone.utc)
        run_id_str = str(run_id) if isinstance(run_id, UUID) else run_id

        self.logger.info(
            "code_generation_started",
            run_id=run_id_str,
            workspace_path=workspace_path
        )

        try:
            # Validate workspace
            workspace = Path(workspace_path)
            if not workspace.exists():
                raise ValidationError(f"Workspace not found: {workspace_path}")

            # Locate approved test plan
            approved_plan_path = await self._find_approved_test_plan(workspace)
            if not approved_plan_path:
                raise ValidationError("Approved test plan not found in workspace")

            self.logger.info("approved_plan_found", path=str(approved_plan_path))

            # Ensure agent is initialized
            if not self.agent:
                await self.initialize()

            # Generate project
            input_data = {
                "run_id": run_id_str,
                "workspace_path": workspace_path,
                "approved_test_plan_path": str(approved_plan_path),
                "base_url": base_url,
                "overwrite": True,  # Always overwrite in workflow
            }

            result = await self.agent.execute(input_data)

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Build summary
            summary = {
                "status": result["status"],
                "project_path": result["project_path"],
                "ir_path": result.get("ir_path"),  # New: IR JSON path
                "dependency_graph_path": result.get("dependency_graph_path"),  # New: Dependency graph path
                "metadata_path": result["metadata_path"],
                "files_generated": result["files_generated"],
                "page_objects_count": result["page_objects_count"],
                "test_files_count": result["test_files_count"],
                "scenarios_implemented": result["scenarios_implemented"],
                "modules_covered": result["modules_covered"],
                "validation_status": result["validation_status"],
                "validation_errors": result.get("validation_errors", 0),
                "validation_warnings": result.get("validation_warnings", 0),
                "refinement_attempts": result.get("refinement_attempts", 0),  # New: IR refinement attempts
                "duration_seconds": duration,
                "warnings": result.get("warnings", []),
            }

            self.logger.info(
                "code_generation_completed",
                run_id=run_id_str,
                status=summary["status"],
                files_generated=summary["files_generated"],
                duration=duration
            )

            return summary

        except Exception as e:
            self.logger.error(
                "code_generation_failed",
                run_id=run_id_str,
                error=str(e)
            )
            raise

    async def _find_approved_test_plan(self, workspace: Path) -> Path | None:
        """
        Find approved test plan in workspace.

        Args:
            workspace: Workspace directory

        Returns:
            Path to approved test plan, or None if not found
        """
        # Check standard location
        approved_plan_path = workspace / "contracts" / "approved-test-plan.json"
        
        if approved_plan_path.exists():
            return approved_plan_path

        # Check review directory
        review_dir = workspace / "review"
        if review_dir.exists():
            # Look for latest approved plan
            approved_plans = list(review_dir.glob("approved-test-plan-v*.json"))
            if approved_plans:
                # Sort by version (latest first)
                approved_plans.sort(reverse=True)
                return approved_plans[0]
            
            # Check for non-versioned plan
            approved_plan = review_dir / "approved-test-plan.json"
            if approved_plan.exists():
                return approved_plan

        return None

    async def validate_generation_input(
        self,
        workspace_path: str
    ) -> tuple[bool, list[str]]:
        """
        Validate inputs for code generation.

        Args:
            workspace_path: Workspace directory path

        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []

        # Check workspace exists
        workspace = Path(workspace_path)
        if not workspace.exists():
            errors.append(f"Workspace not found: {workspace_path}")
            return False, errors

        # Check for approved test plan
        approved_plan_path = await self._find_approved_test_plan(workspace)
        if not approved_plan_path:
            errors.append("Approved test plan not found")
            return False, errors

        # Validate approved test plan structure
        try:
            data = await load_file(approved_plan_path)
            
            if "test_scenarios" not in data:
                errors.append("Approved test plan missing test_scenarios")
            elif not data["test_scenarios"]:
                errors.append("No approved scenarios in test plan")
                
            if "review_metadata" not in data:
                errors.append("Approved test plan missing review_metadata")
                
        except Exception as e:
            errors.append(f"Invalid approved test plan: {str(e)}")

        is_valid = len(errors) == 0
        return is_valid, errors

    async def get_generation_status(
        self,
        workspace_path: str
    ) -> dict[str, Any]:
        """
        Get status of code generation for a workspace.

        Args:
            workspace_path: Workspace directory path

        Returns:
            Dictionary with generation status
        """
        workspace = Path(workspace_path)
        project_path = workspace / "artifacts" / "generated-tests" / "playwright"
        metadata_path = project_path / "code-generation-metadata.json"

        if not project_path.exists():
            return {
                "exists": False,
                "status": "not_started",
            }

        if not metadata_path.exists():
            return {
                "exists": True,
                "status": "incomplete",
                "project_path": str(project_path),
            }

        try:
            metadata = await load_file(metadata_path)
            return {
                "exists": True,
                "status": "completed",
                "project_path": str(project_path),
                "metadata": metadata,
            }
        except Exception:
            return {
                "exists": True,
                "status": "error",
                "project_path": str(project_path),
            }

    def get_service_info(self) -> dict[str, Any]:
        """
        Get service information.

        Returns:
            Dictionary with service details
        """
        return {
            "name": "CodeGenerationService",
            "version": "1.0.0",
            "phase": 7,
            "description": "Generates Playwright test automation code from approved test plans",
            "capabilities": [
                "Validate generation inputs",
                "Locate approved test plans",
                "Invoke code generation agent",
                "Track generation status",
                "Handle generation failures",
            ],
        }

"""
Code Generation Agent (IR-driven)

AI Agent responsible for generating Playwright test automation code
from approved test plans using Intermediate Representation.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import asyncio

from app.agents.ir_generation_agent import IRGenerationAgent
from app.core.artifact_writer import ArtifactWriter
from app.core.event_bus import EventType, emit
from app.core.formatter import CodeFormatter
from app.core.interfaces import IAgent, ILLMClient
from app.exceptions import AgentExecutionError
from app.generators.template_engine import TemplateEngine
from app.logging import LoggerMixin
from app.schemas.code_generation import (
    CodeGenerationRequest,
    CodeGenerationResult,
    CodeGenerationStatus,
)
from app.schemas.ir import CodeGenerationIR
from app.schemas.review import ApprovedTestPlan
from app.utils import load_file


async def _emit(run_id: str | None, event_type: str, data: dict[str, Any]) -> None:
    """Awaited event emit for live UI progress. Always called from async context."""
    if not run_id:
        return
    await emit(run_id, event_type, data)


class CodeGenerationAgent(IAgent, LoggerMixin):
    """
    Code Generation Agent (IR-driven) - generates Playwright code via IR.

    **REFACTORED FOR IR-BASED GENERATION**

    Workflow:
    1. Load approved test plan
    2. Generate IR using IRGenerationAgent (LLM)
    3. Validate IR
    4. Generate code using TemplateEngine (deterministic)
    5. Format code using CodeFormatter
    6. Persist artifacts

    Responsibilities:
    - Orchestrate IR → Code pipeline
    - Never generate code directly via LLM
    - Validate generated artifacts
    - Generate metadata

    Phase: 7 (Code Generation - IR-driven)
    """

    def __init__(
        self,
        llm_client: ILLMClient,
    ) -> None:
        """
        Initialize code generation agent.

        Args:
            llm_client: LLM client for IR generation
        """
        super().__init__()
        self.llm_client = llm_client

        # Initialize IR-based components
        self.ir_agent = IRGenerationAgent(llm_client=llm_client)
        self.template_engine = TemplateEngine()
        self.formatter = CodeFormatter()
        self.artifact_writer = ArtifactWriter()

    async def execute(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """
        Execute IR-driven code generation.

        Args:
            input_data: Input containing:
                - run_id: Workflow run ID
                - workspace_path: Workspace directory
                - approved_test_plan_path: Path to approved test plan
                - base_url: Application base URL (optional)
                - overwrite: Whether to overwrite existing project (optional)

        Returns:
            Dictionary containing:
                - status: Generation status
                - project_path: Path to generated project
                - ir_path: Path to IR JSON
                - dependency_graph_path: Path to dependency graph JSON
                - metadata_path: Path to metadata file
                - files_generated: Number of files generated
                - scenarios_implemented: Number of scenarios implemented
                - validation_status: Validation result
                - duration_seconds: Generation duration
                - warnings: List of warnings

        Raises:
            AgentExecutionError: If generation fails
        """
        import time
        start_time = datetime.now(timezone.utc)
        agent_start_time = time.time()
        run_id = input_data.get("run_id")

        self.logger.info("code_generation_agent_started_ir_driven", 
                        run_id=run_id,
                        timestamp=time.time())

        try:
            # STEP 1: Extract and validate input parameters
            step_start = time.time()
            self.logger.info("codegen_step_1_extract_parameters", run_id=run_id)
            
            workspace_path = input_data.get("workspace_path")
            approved_plan_path = input_data.get("approved_test_plan_path")
            base_url = input_data.get("base_url", "http://localhost:3000")
            overwrite = input_data.get("overwrite", False)
            run_id_str = str(run_id) if run_id else None

            # Phase 1: preserved context threaded through the workflow — the
            # original prompt, the execution plan, the inventory, and the
            # serialised AgentState (credentials already redacted). Recorded
            # in the generation metadata for traceability.
            context_snapshot = {
                "original_prompt": input_data.get("original_prompt"),
                "execution_plan": input_data.get("execution_plan"),
                "inventory_path": input_data.get("inventory_path"),
                "agent_context": input_data.get("agent_context"),
            }

            if not workspace_path:
                raise AgentExecutionError("workspace_path is required")
            if not approved_plan_path:
                raise AgentExecutionError("approved_test_plan_path is required")
            
            self.logger.info("codegen_step_1_complete", run_id=run_id, duration=time.time() - step_start)

            # STEP 2: Emit start event
            step_start = time.time()
            self.logger.info("codegen_step_2_emit_start_event", run_id=run_id)
            
            await _emit(run_id_str, EventType.CODE_GENERATION_STARTED, {
                "stage": "code_generation",
                "label": "Code Generation Started",
                "base_url": base_url,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            
            self.logger.info("codegen_step_2_complete", run_id=run_id, duration=time.time() - step_start)

            # STEP 3: Initialize metrics
            step_start = time.time()
            self.logger.info("codegen_step_3_initialize_metrics", run_id=run_id)
            
            metrics = {
                "files_generated": 0,
                "page_objects": 0,
                "test_files": 0,
                "fixtures": 0,
                "config_files": 0,
                "helpers": 0,
                "scenarios_count": 0,
                "modules_count": 0,
                "elapsed_seconds": 0,
            }
            
            self.logger.info("codegen_step_3_complete", run_id=run_id, duration=time.time() - step_start)

            # STEP 4: Load approved test plan
            step_start = time.time()
            self.logger.info("codegen_step_4_load_test_plan", 
                           run_id=run_id,
                           plan_path=approved_plan_path)
            
            await _emit(run_id_str, EventType.LOADING_TEST_PLAN, {
                "path": approved_plan_path,
                "label": "Loading approved test plan..."
            })
            
            approved_plan = await self._load_approved_plan(approved_plan_path)

            # Execution Scope Enforcement (Phase 6): only scenarios within
            # ExecutionPlan scope may be turned into code. Filter the approved
            # plan through the same resolver used by crawler/inventory/test
            # design so codegen never receives out-of-scope scenarios.
            execution_plan_for_scope = input_data.get("execution_plan")
            if execution_plan_for_scope:
                from app.execution_scope.filtering import filter_approved_plan_object

                filter_approved_plan_object(approved_plan, execution_plan_for_scope)

            load_duration = time.time() - step_start
            self.logger.info("codegen_step_4_complete", 
                           run_id=run_id,
                           scenario_count=len(approved_plan.test_scenarios) if approved_plan.test_scenarios else 0,
                           duration=load_duration)
            
            await _emit(run_id_str, EventType.TEST_PLAN_LOADED, {
                "scenario_count": len(approved_plan.test_scenarios) if approved_plan.test_scenarios else 0,
                "label": f"Test plan loaded ({len(approved_plan.test_scenarios)} scenarios)",
                "duration_seconds": load_duration,
            })

            # Load inventory for richer context (optional)
            inventory_path = Path(workspace_path) / "contracts" / "inventory.json"
            if inventory_path.exists():
                await _emit(run_id_str, EventType.LOADING_INVENTORY, {"path": str(inventory_path)})

            # Load screenshots manifest if available
            screenshots_dir = Path(workspace_path) / "screenshots"
            if screenshots_dir.exists():
                await _emit(run_id_str, EventType.LOADING_SCREENSHOTS, {"path": str(screenshots_dir)})

            scenarios = approved_plan.test_scenarios
            modules = len(set(
                (s.get("metadata", {}) if isinstance(s, dict) else getattr(s, "metadata", {})).get("module", "")
                for s in scenarios
            )) if scenarios else 0
            
            metrics["scenarios_count"] = len(scenarios)
            metrics["modules_count"] = modules
            
            self.logger.info(
                "approved_plan_loaded",
                scenario_count=len(scenarios),
                modules=modules,
            )

            # STEP 5: Plan project structure
            step_start = time.time()
            self.logger.info("codegen_step_5_plan_structure", run_id=run_id)
            
            await _emit(run_id_str, EventType.PLANNING_PROJECT_STRUCTURE, {
                "scenario_count": len(scenarios),
                "modules": modules,
                "label": f"Planning project structure ({modules} modules, {len(scenarios)} scenarios)",
            })

            await _emit(run_id_str, EventType.GENERATION_METRICS_UPDATE, metrics)
            
            self.logger.info("codegen_step_5_complete", run_id=run_id, duration=time.time() - step_start)

            # STEP 6: Determine output paths
            step_start = time.time()
            self.logger.info("codegen_step_6_create_directories", run_id=run_id)
            
            workspace = Path(workspace_path)
            output_path = workspace / "artifacts" / "generated-tests" / "playwright"
            ir_output_path = workspace / "artifacts" / "ir"

            # Create directories
            output_path.mkdir(parents=True, exist_ok=True)
            ir_output_path.mkdir(parents=True, exist_ok=True)
            
            self.logger.info("codegen_step_6_complete", 
                           run_id=run_id,
                           output_path=str(output_path),
                           ir_path=str(ir_output_path),
                           duration=time.time() - step_start)

            # STEP 7: Build prompt and generate IR using LLM
            step_start = time.time()
            self.logger.info("codegen_step_7_generate_ir", run_id=run_id)
            
            await _emit(run_id_str, EventType.CURRENT_ACTIVITY_UPDATE, {
                "activity": "Building Intermediate Representation",
                "current_step": "prompt_preparation",
                "label": "Preparing prompts for IR generation...",
            })
            
            await _emit(run_id_str, EventType.BUILDING_PROMPTS, {
                "scenario_count": len(scenarios),
                "modules": modules,
                "label": "Building IR generation prompts...",
            })
            
            self.logger.info("codegen_step_7a_calling_ir_agent", run_id=run_id)
            self.ir_agent.run_id = run_id_str
            
            ir_result = await self.ir_agent.execute({
                "approved_test_plan": approved_plan,
                "base_url": base_url,
            })
            
            ir_duration = time.time() - step_start
            self.logger.info("codegen_step_7_complete", 
                           run_id=run_id,
                           ir_pages=len(ir_result["ir"].pages),
                           ir_modules=len(ir_result["ir"].modules),
                           duration=ir_duration)

            ir: CodeGenerationIR = ir_result["ir"]
            validation_result = ir_result["validation_result"]
            dependency_graph = ir_result["dependency_graph"]

            await _emit(run_id_str, EventType.PARSING_RESPONSE, {
                "pages": len(ir.pages),
                "modules": len(ir.modules),
                "label": f"IR generated ({len(ir.pages)} pages, {len(ir.modules)} modules)",
            })
            
            await _emit(run_id_str, EventType.GENERATION_PROGRESS_UPDATE, {
                "progress": 25,
                "milestone": "IR Generation Complete",
            })

            # Save IR artifacts
            ir_path = ir_output_path / "code-generation-ir.json"
            ir_path.write_text(
                json.dumps(ir.model_dump(mode="json"), indent=2),
                encoding="utf-8"
            )

            dep_graph_path = ir_output_path / "dependency-graph.json"
            dep_graph_path.write_text(
                json.dumps(dependency_graph.model_dump(mode="json"), indent=2),
                encoding="utf-8"
            )

            self.logger.info(
                "ir_generated_and_saved",
                ir_path=str(ir_path),
                graph_path=str(dep_graph_path)
            )

            # Step 2: Generate code using Template Engine (deterministic)
            self.logger.info("step_2_generating_code_from_ir")
            
            await _emit(run_id_str, EventType.CURRENT_ACTIVITY_UPDATE, {
                "activity": "Generating Playwright Project",
                "current_step": "code_generation",
                "label": "Generating code from IR...",
            })
            
            await _emit(run_id_str, EventType.GENERATION_PROGRESS_UPDATE, {
                "progress": 40,
                "milestone": "Starting Code Generation",
            })
            
            self.template_engine._run_id = run_id_str
            # Run in thread pool so the event loop stays free to dispatch SSE
            # events emitted by the template engine in real-time (live streaming).
            loop = asyncio.get_event_loop()
            generated_files = await loop.run_in_executor(
                None,
                self.template_engine.generate_project,
                ir,
                output_path,
            )

            
            # Update metrics
            metrics["files_generated"] = len(generated_files)
            metrics["page_objects"] = len(ir.pages)
            metrics["test_files"] = len(ir.modules)
            metrics["elapsed_seconds"] = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            await _emit(run_id_str, EventType.GENERATION_METRICS_UPDATE, metrics)
            
            await _emit(run_id_str, EventType.GENERATION_PROGRESS_UPDATE, {
                "progress": 82,
                "milestone": "Code Generation Complete",
            })

            # Step 3: Format generated code
            await _emit(run_id_str, EventType.CURRENT_ACTIVITY_UPDATE, {
                "activity": "Formatting Code",
                "current_step": "formatting",
                "label": "Running code formatter...",
            })
            
            await _emit(run_id_str, EventType.FORMATTING_CODE, {
                "files": len(generated_files),
                "label": f"Formatting {len(generated_files)} files...",
            })
            
            self.logger.info("step_3_formatting_code")
            await loop.run_in_executor(None, self.formatter.format_directory, output_path)

            
            await _emit(run_id_str, EventType.CODE_FORMATTED, {
                "files": len(generated_files),
                "label": "Code formatted successfully",
            })
            
            await _emit(run_id_str, EventType.GENERATION_PROGRESS_UPDATE, {
                "progress": 91,
                "milestone": "Code Formatted",
            })

            # Step 4: Generate metadata
            metadata = self._generate_metadata(
                ir=ir,
                validation_result=validation_result,
                generated_files=generated_files,
                refinement_attempts=ir_result["refinement_attempts"],
                context_snapshot=context_snapshot,
            )

            metadata_path = output_path / "code-generation-metadata.json"
            metadata_path.write_text(
                json.dumps(metadata, indent=2),
                encoding="utf-8"
            )

            # Calculate duration
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()
            
            metrics["elapsed_seconds"] = duration
            await _emit(run_id_str, EventType.GENERATION_METRICS_UPDATE, metrics)

            await _emit(run_id_str, EventType.CURRENT_ACTIVITY_UPDATE, {
                "activity": "Finalizing Project",
                "current_step": "packaging",
                "label": "Packaging generated project...",
            })

            await _emit(run_id_str, EventType.PACKAGING_PROJECT, {
                "project_path": str(output_path),
                "files_generated": len(generated_files),
                "label": "Packaging project files...",
            })
            
            await _emit(run_id_str, EventType.PROJECT_PACKAGED, {
                "project_path": str(output_path),
                "files_generated": len(generated_files),
                "label": "Project packaged successfully",
            })
            
            await _emit(run_id_str, EventType.GENERATION_PROGRESS_UPDATE, {
                "progress": 100,
                "milestone": "Generation Complete",
            })

            # Build result
            result = {
                "status": CodeGenerationStatus.COMPLETED.value,
                "project_path": str(output_path),
                "ir_path": str(ir_path),
                "dependency_graph_path": str(dep_graph_path),
                "metadata_path": str(metadata_path),
                "files_generated": len(generated_files),
                "page_objects_count": len(ir.pages),
                "test_files_count": len(ir.modules),
                "scenarios_implemented": sum(len(m.flows) for m in ir.modules),
                "modules_covered": len(ir.modules),
                "validation_status": "valid" if validation_result.is_valid else "invalid",
                "validation_errors": validation_result.error_count,
                "validation_warnings": validation_result.warning_count,
                "refinement_attempts": ir_result["refinement_attempts"],
                "duration_seconds": duration,
                "warnings": metadata.get("warnings", []),
            }

            await _emit(run_id_str, EventType.CODE_GENERATION_COMPLETED, {
                "files_generated": len(generated_files),
                "page_objects_count": len(ir.pages),
                "test_files_count": len(ir.modules),
                "scenarios_implemented": sum(len(m.flows) for m in ir.modules),
                "project_path": str(output_path),
                "duration_seconds": duration,
            })

            self.logger.info(
                "code_generation_agent_completed_ir_driven",
                run_id=run_id,
                duration=duration,
                files_generated=result["files_generated"],
                status=result["status"]
            )

            return result

        except Exception as e:
            self.logger.error(
                "code_generation_agent_failed",
                run_id=run_id,
                error=str(e)
            )
            await _emit(str(run_id) if run_id else None, EventType.CODE_GENERATION_FAILED, {
                "error": str(e),
                "stage": "code_generation",
            })
            raise AgentExecutionError(f"Code generation failed: {str(e)}") from e

    async def _load_approved_plan(self, plan_path: str) -> ApprovedTestPlan:
        """
        Load and validate approved test plan.

        Args:
            plan_path: Path to approved test plan JSON

        Returns:
            Validated ApprovedTestPlan

        Raises:
            AgentExecutionError: If plan is invalid or missing
        """
        self.logger.info("loading_approved_plan", path=plan_path)

        path = Path(plan_path)
        if not path.exists():
            raise AgentExecutionError(f"Approved test plan not found: {plan_path}")

        try:
            data = await load_file(path)
            approved_plan = ApprovedTestPlan(**data)

            plan_data = approved_plan.test_plan_data or {}
            scenarios = plan_data.get("test_scenarios", []) if isinstance(plan_data, dict) else []
            self.logger.info(
                "approved_plan_validated",
                scenario_count=len(scenarios),
                version=approved_plan.review_version
            )

            return approved_plan

        except Exception as e:
            raise AgentExecutionError(f"Invalid approved test plan: {str(e)}") from e

    def _generate_metadata(
        self,
        ir: CodeGenerationIR,
        validation_result: Any,
        generated_files: dict[str, Path],
        refinement_attempts: int,
        context_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Generate metadata for code generation.

        Args:
            ir: Generated IR
            validation_result: IR validation result
            generated_files: Dictionary of generated files
            refinement_attempts: Number of IR refinement attempts
            context_snapshot: Phase 1 preserved context (original prompt,
                execution plan, inventory, agent state) recorded for traceability.

        Returns:
            Metadata dictionary
        """
        metadata: dict[str, Any] = {
            "generator": "IR-driven Template Engine",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ir_version": ir.metadata.ir_version,
            "refinement_attempts": refinement_attempts,
            "files_generated": len(generated_files),
            "pages": len(ir.pages),
            "modules": len(ir.modules),
            "flows": sum(len(m.flows) for m in ir.modules),
            "validation": {
                "is_valid": validation_result.is_valid,
                "errors": validation_result.error_count,
                "warnings": validation_result.warning_count,
            },
            "environment": {
                "base_url": ir.environment.base_url,
                "browsers": ir.environment.browsers,
                "auth_required": ir.environment.auth_required,
            },
            "warnings": [
                issue.message
                for issue in validation_result.issues
                if issue.severity == "warning"
            ][:10],  # Limit to 10 warnings
        }
        # Phase 1: record the preserved context (original prompt, execution
        # plan, inventory, agent state) so code generation is provably
        # traceable back to the user's intent.
        if context_snapshot:
            metadata["context"] = {
                k: v for k, v in context_snapshot.items() if v is not None
            }
        return metadata

    async def generate_from_request(
        self,
        request: CodeGenerationRequest
    ) -> CodeGenerationResult:
        """
        Generate project from request object.

        Args:
            request: CodeGenerationRequest

        Returns:
            CodeGenerationResult
        """
        start_time = datetime.now(timezone.utc)

        try:
            # Execute agent
            input_data = {
                "run_id": request.run_id,
                "workspace_path": request.workspace_path,
                "approved_test_plan_path": request.approved_test_plan_path,
                "overwrite": request.overwrite,
                "base_url": getattr(request, "base_url", "http://localhost:3000"),
            }

            result_data = await self.execute(input_data)

            # Build result
            duration = (datetime.now(timezone.utc) - start_time).total_seconds()

            result = CodeGenerationResult(
                status=CodeGenerationStatus(result_data["status"]),
                metadata_path=result_data.get("metadata_path"),
                duration_seconds=duration,
                warnings=result_data.get("warnings", []),
            )

            return result

        except Exception as e:
            return CodeGenerationResult(
                status=CodeGenerationStatus.FAILED,
                error_message=str(e),
                duration_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
            )

    def get_agent_info(self) -> dict[str, Any]:
        """
        Get agent information.

        Returns:
            Dictionary with agent details
        """
        return {
            "name": "CodeGenerationAgent",
            "version": "2.0.0",
            "phase": 7,
            "approach": "IR-driven",
            "description": "Generates Playwright code via Intermediate Representation (IR)",
            "workflow": [
                "1. Load approved test plan",
                "2. Generate IR using LLM (IRGenerationAgent)",
                "3. Validate IR structure",
                "4. Generate code using Template Engine (deterministic)",
                "5. Format code",
                "6. Persist artifacts",
            ],
            "capabilities": [
                "IR generation from test plans",
                "IR validation and refinement",
                "Dependency graph generation",
                "Deterministic code generation",
                "Page Object Model generation",
                "Test specification generation",
                "Code formatting",
                "Artifact persistence",
            ],
            "inputs": [
                "run_id",
                "workspace_path",
                "approved_test_plan_path",
                "base_url (optional)",
                "overwrite (optional)",
            ],
            "outputs": [
                "Intermediate Representation (JSON)",
                "Dependency Graph (JSON)",
                "Complete Playwright project",
                "Page objects",
                "Test files",
                "Fixtures",
                "Utilities",
                "Configuration files",
                "Generation metadata",
            ],
            "advantages": [
                "Framework-independent IR",
                "Deterministic code generation",
                "Better validation",
                "Dependency analysis",
                "Easier debugging",
            ],
        }

    def get_system_prompt(self) -> str:
        return "You are the Code Generation Agent. Generate Playwright TypeScript test automation code."

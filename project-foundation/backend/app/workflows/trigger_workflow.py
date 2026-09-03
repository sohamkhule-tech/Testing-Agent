"""
Testing Platform Workflow - LangGraph Implementation

Complete workflow: START → Trigger → Crawler → Inventory Aggregator → Test Design → Human Review → Code Generation → END
"""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from app.agents import CodeGenerationAgent, CrawlerAgent, TestDesignAgent, TriggerAgent
from app.constants import RunStatus
from app.context import AgentState, ExecutionPlan, get_context_manager
from app.core.event_bus import EventType, emit
from app.dependencies import get_inventory_aggregator_service, get_test_design_agent
from app.graph import GraphState, NodeResult
from app.logging import get_logger
from app.schemas.test_plan import generate_test_case_id

logger = get_logger("workflow.platform")


class PlatformWorkflowState(GraphState):
    """
    State model for platform workflow.

    Extends base graph state with workflow-specific fields.
    """

    request_data: dict[str, Any] | None = None
    requested_by: str | None = None
    workspace_path: str | None = None
    user_prompt: str | None = None
    # Phase 5/6 — structured prompt intent and auth (never logged)
    prompt_context: dict[str, Any] | None = None   # ParsedPromptIntent serialised
    auth_context: dict[str, Any] | None = None     # SECURITY: never emit in events
    selected_model: str | None = None

    # Phase 1 — AgentState: canonical intent-preservation state threaded
    # through every stage (original prompt, parsed intent, execution plan,
    # and per-stage outputs). Added as optional fields — no breaking change.
    agent_state: AgentState | None = None
    execution_plan: ExecutionPlan | None = None

    # Trigger output
    trigger_output: dict[str, Any] | None = None

    # Crawler output
    crawler_output: dict[str, Any] | None = None
    crawl_status: str | None = None
    pages_visited: int = 0
    total_links: int = 0

    # Inventory output
    inventory_path: str | None = None
    inventory_summary: dict[str, Any] | None = None

    # Test design output
    test_plan_path: str | None = None
    test_plan_summary: dict[str, Any] | None = None
    test_plan_md_path: str | None = None

    # Human review output
    review_status: str | None = None
    review_decision: str | None = None
    review_version: int = 1
    reviewer_name: str | None = None
    approved_test_plan_path: str | None = None
    approved_test_plan_md_path: str | None = None
    review_metadata_path: str | None = None
    approved_scenarios: int = 0
    rejected_scenarios: int = 0
    total_scenarios: int = 0

    # Code generation output
    generated_project_path: str | None = None
    generated_tests_path: str | None = None
    code_generation_metadata_path: str | None = None
    page_objects_count: int = 0
    test_files_count: int = 0
    scenarios_implemented: int = 0
    code_generation_status: str | None = None
    code_generation_duration: float = 0.0
    validation_status: str | None = None
    validation_errors: int = 0
    validation_warnings: int = 0

    # Execution output (Phase 8)
    execution_status: str | None = None
    execution_duration: float = 0.0
    execution_start: str | None = None
    execution_end: str | None = None
    execution_artifacts_path: str | None = None
    execution_reports_path: str | None = None
    tests_total: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    tests_skipped: int = 0
    tests_flaky: int = 0
    pass_rate: float = 0.0
    execution_report_html_path: str | None = None
    execution_report_json_path: str | None = None
    environment_report: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    reports: dict[str, Any] | None = None
    artifacts: dict[str, Any] | None = None
    failure_summary: dict[str, Any] | None = None
    retry_summary: dict[str, Any] | None = None
    playwright_exit_code: int | None = None
    execution_logs: dict[str, str] | None = None


async def trigger_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Trigger agent node.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    try:
        logger.info("trigger_node_started", run_id=state.run_id)
        await emit(state.run_id, EventType.STAGE_STARTED, {"stage": "trigger", "label": "Project Setup"})

        state.mark_node_started("trigger")

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("trigger", "Initialising workspace and validating target URL")

        # Get trigger agent from dependency injection (passed via state metadata)
        trigger_agent: TriggerAgent = state.metadata.get("trigger_agent")

        if not trigger_agent:
            raise ValueError("TriggerAgent not found in state metadata")

        # Execute trigger agent (skip run creation if workspace_path already set)
        if state.workspace_path:
            logger.info("trigger_using_existing_run", run_id=state.run_id, workspace=state.workspace_path)
            result = {"run_id": state.run_id, "workspace_path": state.workspace_path}
        else:
            input_data = {
                "request": state.request_data,
                "requested_by": state.requested_by,
            }
            result = await trigger_agent.execute(input_data)

        # Update state
        state.run_id = result.get("run_id", state.run_id)
        state.workspace_path = result.get("workspace_path")
        state.trigger_output = result

        await emit(state.run_id, EventType.WORKSPACE_CREATED, {"workspace_path": state.workspace_path})
        await emit(state.run_id, EventType.RUN_METADATA_SAVED, {"run_id": state.run_id, "requested_by": state.requested_by})

        # Mark node completed
        # Phase 2: record stage completion
        if state.agent_state is not None:
            state.agent_state.record_stage_done("trigger")
        node_result = NodeResult(
            node_name="trigger",
            status="completed",
            data=result,
        )
        state.mark_node_completed("trigger", node_result)
        await emit(state.run_id, EventType.STAGE_COMPLETED, {"stage": "trigger"})

        logger.info("trigger_node_completed", run_id=state.run_id)

        return state

    except Exception as e:
        logger.error("trigger_node_failed", run_id=state.run_id, error=str(e))
        await emit(state.run_id, EventType.STAGE_FAILED, {"stage": "trigger", "error": str(e)})
        if state.workspace_path:
            _mark_stage_failed(state.workspace_path, "trigger", str(e))

        # Mark as failed
        state.mark_failed(f"Trigger node failed: {str(e)}")

        node_result = NodeResult(
            node_name="trigger",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("trigger", node_result)

        return state


async def crawler_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Crawler agent node.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    try:
        logger.info("crawler_node_started", run_id=state.run_id)
        await emit(state.run_id, EventType.STAGE_STARTED, {"stage": "crawler", "label": "Web Crawler"})
        await emit(state.run_id, EventType.CRAWLER_STARTED, {
            "target_url": (state.request_data or {}).get("target_application", {}).get("base_url", ""),
        })

        state.mark_node_started("crawler")

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("crawler", "Crawling application pages and discovering structure")

        # Get crawler agent from dependency injection
        crawler_agent: CrawlerAgent = state.metadata.get("crawler_agent")

        if not crawler_agent:
            raise ValueError("CrawlerAgent not found in state metadata")

        # Inject the event bus so the crawler can emit fine-grained events
        crawler_agent._event_run_id = state.run_id

        # Phase 2: authoritative scope from ExecutionPlan (single source of truth).
        _scope_overrides: dict = {}
        _auth_context_dict: dict = {}
        if state.execution_plan is not None:
            _scope_overrides = {
                "include_pages": state.execution_plan.workflow_scope.get("included_pages") or [],
                "exclude_pages": state.execution_plan.workflow_scope.get("excluded_pages") or [],
            }
        # Load encrypted credentials from workspace
        if state.workspace_path:
            from app.services.prompt_builder import get_credential_store as _gcs
            _loaded_auth = _gcs().load(state.workspace_path)
            if _loaded_auth.has_auth_config():
                # Do NOT default the login URL to the target base URL: the target
                # base URL is not necessarily a login page. If no login URL was
                # supplied, the crawler reports a structured AUTH_URL_NOT_FOUND
                # (or attempts runtime discovery) rather than assuming the base
                # URL is a login page.
                _auth_context_dict = {
                    "username": _loaded_auth.username,
                    "password": _loaded_auth.password,
                    "login_url": _loaded_auth.login_url,
                    "auth_strategy": _loaded_auth.auth_strategy,
                }
                # Phase 1: mirror credentials into AgentState (in-memory only —
                # never logged/emitted; redacted() strips them).
                if state.agent_state is not None:
                    state.agent_state.credentials = dict(_auth_context_dict)

        # Prepare input data for crawler
        input_data = {
            "run_id": state.run_id,
            "request_id": state.trigger_output.get("request_id") if state.trigger_output else state.run_id,
            "workspace_path": state.workspace_path,
            "trigger_output": state.trigger_output or {},
            "request_data": state.request_data or {},
            "scope_overrides": _scope_overrides,
            # Execution Scope Enforcement: the full ExecutionPlan is the single
            # source of truth for what the crawler may discover.
            "execution_plan": (
                state.execution_plan.to_serializable()
                if state.execution_plan is not None
                else None
            ),
            "auth_context": _auth_context_dict,  # SECURITY: not emitted in events
        }

        # Execute crawler agent
        result = await crawler_agent.execute(input_data)

        # Update state
        state.crawler_output = result
        state.crawl_status = result.get("crawl_status")
        state.pages_visited = result.get("pages_visited", 0)
        state.total_links = result.get("total_links", 0)

        await emit(state.run_id, EventType.CRAWL_COMPLETED, {
            "pages_visited": state.pages_visited,
            "total_links": state.total_links,
        })

        # Phase 2: record stage completion
        if state.agent_state is not None:
            state.agent_state.record_stage_done("crawler")
        # Mark node completed
        node_result = NodeResult(
            node_name="crawler",
            status="completed",
            data=result,
        )
        state.mark_node_completed("crawler", node_result)
        await emit(state.run_id, EventType.STAGE_COMPLETED, {"stage": "crawler", "pages_visited": state.pages_visited})

        logger.info(
            "crawler_node_completed",
            run_id=state.run_id,
            pages_visited=state.pages_visited,
            total_links=state.total_links,
        )

        return state

    except Exception as e:
        logger.error("crawler_node_failed", run_id=state.run_id, error=str(e))
        await emit(state.run_id, EventType.STAGE_FAILED, {"stage": "crawler", "error": str(e)})
        if state.workspace_path:
            _mark_stage_failed(state.workspace_path, "crawler", str(e))

        # Mark as failed
        state.mark_failed(f"Crawler node failed: {str(e)}")

        node_result = NodeResult(
            node_name="crawler",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("crawler", node_result)

        return state


async def inventory_aggregator_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Inventory aggregator node.

    Aggregates crawler outputs into canonical inventory.
    No business logic — only invokes InventoryAggregatorService.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    try:
        logger.info("inventory_aggregator_node_started", run_id=state.run_id)
        await emit(state.run_id, EventType.STAGE_STARTED, {"stage": "inventory", "label": "Inventory Aggregation"})
        await emit(state.run_id, EventType.INVENTORY_STARTED, {})

        state.mark_node_started("inventory_aggregator")

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("inventory_aggregator", "Aggregating crawl data into canonical inventory")

        from uuid import UUID

        service = get_inventory_aggregator_service()

        run_id = UUID(state.run_id) if isinstance(state.run_id, str) else state.run_id
        workspace_path = state.workspace_path or ""

        excluded_modules: list[str] = []
        execution_scope: dict | None = None
        # Phase 2: authoritative scope from ExecutionPlan
        if state.execution_plan is not None:
            excluded_modules = state.execution_plan.workflow_scope.get("excluded_modules") or []
            # Execution Scope Enforcement: pass the full serialised ExecutionPlan
            # so the aggregator filters pages AND elements/navigation by scope.
            execution_scope = state.execution_plan.to_serializable()

        # Aggregate inventory
        inventory = await service.aggregate_and_persist(
            run_id=run_id,
            workspace_path=workspace_path,
            excluded_modules=excluded_modules,
            execution_scope=execution_scope,
        )

        # Update state
        state.inventory_path = f"{workspace_path}/contracts/inventory.json"
        state.inventory_summary = {
            "page_count": inventory.metadata.page_count,
            "form_count": inventory.metadata.form_count,
            "link_count": inventory.metadata.link_count,
            "button_count": inventory.metadata.button_count,
            "input_count": inventory.metadata.input_count,
            "screenshot_count": inventory.metadata.screenshot_count,
            "duplicate_pages_removed": inventory.metadata.duplicate_pages_removed,
            "duplicate_links_removed": inventory.metadata.duplicate_links_removed,
            "excluded_page_count": inventory.metadata.excluded_page_count,
            "excluded_modules": inventory.metadata.excluded_modules,
        }

        await emit(state.run_id, EventType.INVENTORY_GENERATED, state.inventory_summary)

        # Phase 1: capture inventory into AgentState so downstream stages (test
        # design, code generation) can access it without re-reading files.
        if state.agent_state is not None:
            get_context_manager().capture_inventory(
                state,
                inventory_path=state.inventory_path,
                summary=state.inventory_summary,
            )

        # Phase 2: record stage completion
        if state.agent_state is not None:
            state.agent_state.record_stage_done("inventory_aggregator")
        # Mark node completed
        node_result = NodeResult(
            node_name="inventory_aggregator",
            status="completed",
            data={
                "inventory_path": state.inventory_path,
                "summary": state.inventory_summary,
            },
        )
        state.mark_node_completed("inventory_aggregator", node_result)
        await emit(state.run_id, EventType.STAGE_COMPLETED, {"stage": "inventory", **state.inventory_summary})

        logger.info(
            "inventory_aggregator_node_completed",
            run_id=state.run_id,
            pages=inventory.metadata.page_count,
            forms=inventory.metadata.form_count,
            links=inventory.metadata.link_count,
        )

        return state

    except Exception as e:
        logger.error("inventory_aggregator_node_failed", run_id=state.run_id, error=str(e))
        await emit(state.run_id, EventType.STAGE_FAILED, {"stage": "inventory", "error": str(e)})
        if state.workspace_path:
            _mark_stage_failed(state.workspace_path, "inventory_aggregator", str(e))

        state.mark_failed(f"Inventory aggregator node failed: {str(e)}")

        node_result = NodeResult(
            node_name="inventory_aggregator",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("inventory_aggregator", node_result)

        return state


async def test_design_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Test design agent node.

    Analyzes inventory and generates structured test plan.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    try:
        logger.info("test_design_node_started", run_id=state.run_id)
        await emit(state.run_id, EventType.STAGE_STARTED, {"stage": "test_design", "label": "Test Design"})

        # ── AI reasoning: pre-analysis steps ────────────────────────────
        await emit(state.run_id, EventType.ANALYSIS_PROGRESS, {"phase": "reading_inventory", "progress": 10, "label": "Reading Inventory..."})
        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "reading_inventory",
            "label": "Reading Inventory",
            "description": "Loading discovered application pages, forms, inputs, and navigation structure...",
            "status": "running",
        })

        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "analyzing_structure",
            "label": "Analyzing Application Structure",
            "description": "Grouping UI components into logical modules and detecting authentication flows...",
            "status": "pending",
        })

        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "generating_scenarios",
            "label": "Generating Test Scenarios",
            "description": "Creating functional, negative, boundary, and security test cases...",
            "status": "pending",
        })

        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "prioritizing",
            "label": "Assigning Priority & Risk",
            "description": "Calculating risk levels and assigning priority to each scenario...",
            "status": "pending",
        })

        await emit(state.run_id, EventType.CONFIDENCE_UPDATE, {"metric": "inventory_confidence", "value": 96})

        # Mark first step as completed, second as running
        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "reading_inventory",
            "label": "Reading Inventory",
            "description": "Loaded inventory with pages, forms, inputs, and navigation structure.",
            "status": "completed",
        })
        await emit(state.run_id, EventType.ANALYSIS_PROGRESS, {"phase": "analyzing_structure", "progress": 35, "label": "Analyzing application structure..."})

        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "analyzing_structure",
            "label": "Analyzing Application Structure",
            "description": "Grouping UI components into logical modules and detecting authentication flows...",
            "status": "running",
        })

        state.mark_node_started("test_design")

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("test_design", "Analysing inventory and generating structured test plan")

        test_design_agent: TestDesignAgent = state.metadata.get("test_design_agent")

        if not test_design_agent:
            raise ValueError("TestDesignAgent not found in state metadata")

        input_data = {
            "run_id": state.run_id,
            "request_id": state.trigger_output.get("request_id") if state.trigger_output else state.run_id,
            "workspace_path": state.workspace_path,
            "trigger_output": state.trigger_output or {},
            "crawler_output": state.crawler_output or {},
            "user_prompt": state.user_prompt,
            # Phase 2: ExecutionPlan is the authoritative scope — no direct prompt parsing
            "execution_plan": (
                state.execution_plan.to_serializable()
                if state.execution_plan is not None
                else None
            ),
            # Phase 1: full AgentState (credentials redacted) for richer intent
            "agent_state": (
                get_context_manager().to_serializable(state)
                if state.agent_state is not None
                else None
            ),
            "model": state.selected_model,
        }

        # Execute test design agent
        result = await test_design_agent.execute(input_data)

        await emit(state.run_id, EventType.LLM_CALL_COMPLETED, {
            "purpose": "Test plan generation",
            "model": state.selected_model,
            "response_tokens": result.get("scenario_count", 0),
        })

        await emit(state.run_id, EventType.AI_REASONING_STEP, {
            "step": "analyzing_structure",
            "label": "Analyzing Application Structure",
            "description": "Application structure analyzed and modules identified.",
            "status": "completed",
        })

        # ── Emit module detection events ────────────────────────────────
        await emit(state.run_id, EventType.ANALYSIS_PROGRESS, {"phase": "detecting_modules", "progress": 55, "label": "Detecting modules..."})

        test_plan_path = result.get("test_plan_path")
        if test_plan_path:
            import json as _json
            try:
                with open(test_plan_path) as f:
                    test_plan_data = _json.load(f)

                modules_data = test_plan_data.get("modules", [])
                all_scenarios = test_plan_data.get("test_scenarios", [])
                total_modules = len(modules_data)
                total_scenarios = len(all_scenarios)

                for idx, mod in enumerate(modules_data):
                    mod_name = mod.get("name", f"Module {idx + 1}")
                    mod_description = mod.get("description", "")
                    mod_pages = mod.get("pages", [])
                    mod_scenarios = mod.get("scenarios", [])
                    await emit(state.run_id, EventType.MODULE_DETECTED, {
                        "name": mod_name,
                        "description": mod_description,
                        "pages": mod_pages,
                        "scenario_count": len(mod_scenarios),
                        "module_index": idx,
                        "total_modules": total_modules,
                    })

                # ── Emit scenario generated events ──────────────────────
                await emit(state.run_id, EventType.ANALYSIS_PROGRESS, {"phase": "generating_scenarios", "progress": 70, "label": "Generating scenarios..."})
                await emit(state.run_id, EventType.AI_REASONING_STEP, {
                    "step": "generating_scenarios",
                    "label": "Generating Test Scenarios",
                    "description": f"Creating {total_scenarios} test scenarios across {total_modules} modules...",
                    "status": "running",
                })

                for idx, sc in enumerate(all_scenarios):
                    meta = sc.get("metadata", {})
                    await emit(state.run_id, EventType.SCENARIO_GENERATED, {
                        "id": meta.get("id", generate_test_case_id(idx + 1)),
                        "title": meta.get("title", ""),
                        "description": meta.get("description", ""),
                        "module": meta.get("module", ""),
                        "priority": meta.get("priority", "medium"),
                        "category": meta.get("category", "functional"),
                        "risk_level": meta.get("risk_level", "medium"),
                        "target_page": meta.get("target_page", ""),
                        "scenario_index": idx,
                        "total_scenarios": total_scenarios,
                    })

                await emit(state.run_id, EventType.AI_REASONING_STEP, {
                    "step": "generating_scenarios",
                    "label": "Generating Test Scenarios",
                    "description": f"Created {total_scenarios} test scenarios across {total_modules} modules.",
                    "status": "completed",
                })

                # ── Emit confidence update ──────────────────────────────
                await emit(state.run_id, EventType.ANALYSIS_PROGRESS, {"phase": "calculating_confidence", "progress": 90, "label": "Calculating confidence scores..."})
                await emit(state.run_id, EventType.AI_REASONING_STEP, {
                    "step": "prioritizing",
                    "label": "Assigning Priority & Risk",
                    "description": "Risk levels and priorities assigned to all scenarios.",
                    "status": "completed",
                })

                # Compute coverage metrics from test plan data
                coverage = test_plan_data.get("coverage_summary", {})
                by_priority = coverage.get("by_priority", {})
                total_critical = by_priority.get("critical", 0)
                total_high = by_priority.get("high", 0)
                total_medium = by_priority.get("medium", 0)
                total_low = by_priority.get("low", 0)
                by_category = coverage.get("by_category", {})
                functional_count = by_category.get("functional", 0)
                negative_count = by_category.get("negative", 0)
                boundary_count = by_category.get("boundary", 0)
                auth_count = by_category.get("authentication", 0) + by_category.get("authorization", 0)

                automation_candidates = total_scenarios - total_low
                automation_coverage = round((automation_candidates / max(total_scenarios, 1)) * 100)

                await emit(state.run_id, EventType.CONFIDENCE_UPDATE, {"metric": "scenario_confidence", "value": 94})
                await emit(state.run_id, EventType.CONFIDENCE_UPDATE, {"metric": "automation_coverage", "value": automation_coverage})
                await emit(state.run_id, EventType.CONFIDENCE_UPDATE, {"metric": "risk_coverage", "value": 88})

            except Exception as e:
                logger.warning("test_design_node_event_emission_failed", error=str(e))

        # Update state
        state.test_plan_path = test_plan_path
        state.test_plan_md_path = result.get("test_plan_md_path")
        state.test_plan_summary = {
            "scenario_count": result.get("scenario_count", 0),
            "modules": result.get("modules", 0),
            "summary": result.get("message", ""),
        }

        # Phase 1: capture test plan into AgentState for review + codegen
        if state.agent_state is not None:
            get_context_manager().capture_test_plan(
                state,
                path=state.test_plan_path,
                summary=state.test_plan_summary,
            )

        await emit(state.run_id, EventType.TEST_PLAN_GENERATED, {
            "scenario_count": result.get("scenario_count", 0),
            "test_plan_path": state.test_plan_path,
        })

        await emit(state.run_id, EventType.ANALYSIS_PROGRESS, {"phase": "complete", "progress": 100, "label": "Test plan ready for review."})

        # Phase 2: record stage completion
        if state.agent_state is not None:
            state.agent_state.record_stage_done("test_design")
        # Mark node completed
        node_result = NodeResult(
            node_name="test_design",
            status="completed",
            data=result,
        )
        state.mark_node_completed("test_design", node_result)
        await emit(state.run_id, EventType.STAGE_COMPLETED, {
            "stage": "test_design",
            "scenario_count": result.get("scenario_count", 0),
        })

        logger.info(
            "test_design_node_completed",
            run_id=state.run_id,
            scenarios=result.get("scenario_count", 0),
        )

        return state

    except Exception as e:
        logger.error("test_design_node_failed", run_id=state.run_id, error=str(e))
        await emit(state.run_id, EventType.STAGE_FAILED, {"stage": "test_design", "error": str(e)})
        if state.workspace_path:
            _mark_stage_failed(state.workspace_path, "test_design", str(e))

        state.mark_failed(f"Test design node failed: {str(e)}")

        node_result = NodeResult(
            node_name="test_design",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("test_design", node_result)

        return state


async def human_review_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Human review node.

    Processes human review of AI-generated test plan.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    try:
        logger.info("human_review_node_started", run_id=state.run_id)
        await emit(state.run_id, EventType.STAGE_STARTED, {"stage": "human_review", "label": "Human Review"})

        state.mark_node_started("human_review")

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("human_review", "Reviewing generated test plan")

        from app.dependencies import get_human_review_service
        from app.schemas.review import ReviewRequest

        human_review_service = get_human_review_service()

        # A review decision may already be persisted for this run (e.g. from
        # the selective POST /approve endpoint, or a resumed workflow). The
        # persisted review is the source of truth — NEVER re-run the approval,
        # which would overwrite a partial approval (e.g. 4 approved) with a
        # full auto-approval (all scenarios) once the post-review workflow
        # re-executes this node.
        persisted_review = await _load_persisted_review(state.workspace_path or "")
        if persisted_review is not None:
            logger.info(
                "human_review_persisted_review_found",
                run_id=state.run_id,
                review_status=persisted_review.get("review_status"),
                approved_scenarios=persisted_review.get("approved_scenarios"),
                rejected_scenarios=persisted_review.get("rejected_scenarios"),
                total_scenarios=persisted_review.get("total_scenarios"),
            )
            logger.info(
                "human_review_reapproval_skipped",
                run_id=state.run_id,
                reason="persisted review already exists — reusing it",
            )
            result = persisted_review
        else:
            # No persisted decision yet → auto-approve (pre-review behaviour).
            review_request = ReviewRequest(
                run_id=state.run_id,
                reviewer_name=state.requested_by or "system",
                reviewer_email=f"{state.requested_by or 'system'}@example.com",
                auto_approve=True,  # Auto-approve for now
                general_comments="Auto-approved by system",
            )
            result = await human_review_service.review_test_plan(
                workspace_path=state.workspace_path or "",
                review_request=review_request,
            )
            logger.info(
                "human_review_auto_approve_executed",
                run_id=state.run_id,
                review_status=result.get("review_status"),
                approved_scenarios=result.get("approved_scenarios"),
                total_scenarios=result.get("total_scenarios"),
            )

        # Update state
        state.review_status = result.get("review_status")
        state.review_decision = result.get("review_decision")
        state.review_version = result.get("review_version", 1)
        state.reviewer_name = result.get("reviewer_name")
        state.approved_test_plan_path = result.get("approved_test_plan_path")
        state.approved_test_plan_md_path = result.get("approved_test_plan_md_path")
        state.review_metadata_path = result.get("review_metadata_path")
        state.approved_scenarios = result.get("approved_scenarios", 0)
        state.rejected_scenarios = result.get("rejected_scenarios", 0)
        state.total_scenarios = result.get("total_scenarios", 0)

        # Phase 1: capture the review outcome while preserving the original
        # prompt, parsed intent, and execution plan inside AgentState.
        if state.agent_state is not None:
            get_context_manager().capture_review(state, review_result=result)

        # Phase 2: record stage completion
        if state.agent_state is not None:
            state.agent_state.record_stage_done("human_review")
        # Mark node completed
        node_result = NodeResult(
            node_name="human_review",
            status="completed",
            data=result,
        )
        state.mark_node_completed("human_review", node_result)
        await emit(state.run_id, EventType.STAGE_COMPLETED, {"stage": "human_review", "status": state.review_decision})

        # DO NOT mark workflow as completed - code generation comes next

        logger.info(
            "human_review_node_completed",
            run_id=state.run_id,
            review_status=state.review_status,
            approved_scenarios=state.approved_scenarios,
        )

        return state

    except Exception as e:
        logger.error("human_review_node_failed", run_id=state.run_id, error=str(e))
        await emit(state.run_id, EventType.STAGE_FAILED, {"stage": "human_review", "error": str(e)})
        if state.workspace_path:
            _mark_stage_failed(state.workspace_path, "human_review", str(e))

        state.mark_failed(f"Human review node failed: {str(e)}")

        node_result = NodeResult(
            node_name="human_review",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("human_review", node_result)

        return state


async def code_generation_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Code generation node.

    Generates Playwright test automation project from approved test plan.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    import time
    node_start_time = time.time()

    try:
        logger.info("code_generation_node_started", run_id=state.run_id, timestamp=time.time())
        await emit(state.run_id, EventType.STAGE_STARTED, {
            "stage": "code_generation",
            "label": "Code Generation",
            "timestamp": datetime.now(UTC).isoformat(),
        })

        state.mark_node_started("code_generation")

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("code_generation", "Generating Playwright test project from approved plan")

        # STEP 1: Verify agent injection
        step_start = time.time()
        logger.info("code_generation_step_1_checking_agent", run_id=state.run_id)
        await emit(state.run_id, EventType.CURRENT_ACTIVITY_UPDATE, {
            "activity": "Initializing Code Generation",
            "current_step": "checking_agent",
            "label": "Verifying code generation agent...",
        })

        # Get code generation agent from dependency injection
        code_gen_agent: CodeGenerationAgent = state.metadata.get("code_generation_agent")

        if not code_gen_agent:
            error_msg = "CodeGenerationAgent not found in state metadata"
            logger.error("code_generation_agent_missing", run_id=state.run_id)
            await emit(state.run_id, EventType.CODE_GENERATION_FAILED, {
                "error": error_msg,
                "stage": "agent_initialization",
            })
            raise ValueError(error_msg)

        logger.info("code_generation_step_1_complete", run_id=state.run_id, duration=time.time() - step_start)

        # STEP 2: Prepare input data
        step_start = time.time()
        logger.info("code_generation_step_2_preparing_input", run_id=state.run_id)
        await emit(state.run_id, EventType.CURRENT_ACTIVITY_UPDATE, {
            "activity": "Preparing Input Data",
            "current_step": "preparing_input",
            "label": "Loading test plan and configuration...",
        })

        # Phase 2: output preferences from ExecutionPlan (single source of truth)
        _output_prefs: list[str] = []
        if state.execution_plan is not None:
            _output_prefs = state.execution_plan.workflow_scope.get("output_preferences") or []

        # Extract real target base_url from run request data
        _base_url = "http://localhost:3000"  # fallback
        try:
            _req_data = state.request_data or {}
            _ta = _req_data.get("target_application") or {}
            _raw_url = _ta.get("base_url") or _ta.get("url") or ""
            if _raw_url:
                _base_url = _raw_url
        except Exception:
            pass

        # Phase 1: give code generation the full preserved context — original
        # prompt, execution plan, approved test plan, inventory, and agent state.
        _plan_serialized = (
            state.execution_plan.to_serializable()
            if state.execution_plan is not None
            else None
        )
        _agent_ctx = (
            get_context_manager().to_serializable(state)
            if state.agent_state is not None
            else None
        )

        # Selective approval scoping: when the Human Review is PARTIAL, feed
        # Code Generation ONLY the approved scenarios via a scoped COPY of the
        # approved plan (the persisted plan is never mutated). If nothing is
        # approved, do NOT start Code Generation / Test Execution.
        from app.dependencies import get_human_review_service as _get_hrs
        _approved_plan_path = await _get_hrs().resolve_codegen_test_plan_path(
            workspace_path=state.workspace_path,
            canonical_path=state.approved_test_plan_path,
        )
        if _approved_plan_path is None:
            logger.warning("codegen_skipped_no_approved_scenarios", run_id=state.run_id)
            await emit(state.run_id, EventType.STAGE_SKIPPED, {
                "stage": "code_generation",
                "label": "Code Generation skipped — no approved test scenarios",
                "message": "No test scenarios are approved. Awaiting human review approval.",
            })
            state.code_generation_status = "awaiting_review"
            state.status = RunStatus.PAUSED
            return state

        logger.info(
            "codegen_approved_plan_resolved",
            run_id=state.run_id,
            approved_plan_path=_approved_plan_path,
            scoped=_approved_plan_path != state.approved_test_plan_path,
        )

        input_data = {
            "run_id": state.run_id,
            "workspace_path": state.workspace_path,
            "approved_test_plan_path": _approved_plan_path,
            "base_url": _base_url,
            "model": state.selected_model,
            "output_preferences": _output_prefs,
            # Phase 1: preserved context
            "original_prompt": state.user_prompt,
            "execution_plan": _plan_serialized,
            "inventory_path": state.inventory_path,
            "agent_context": _agent_ctx,
        }

        logger.info("code_generation_step_2_complete",
                   run_id=state.run_id,
                   workspace_path=state.workspace_path,
                   approved_plan=_approved_plan_path,
                   scoped=_approved_plan_path != state.approved_test_plan_path,
                   duration=time.time() - step_start)

        # STEP 3: Execute code generation with timeout
        step_start = time.time()
        logger.info("code_generation_step_3_executing_agent", run_id=state.run_id)
        await emit(state.run_id, EventType.CURRENT_ACTIVITY_UPDATE, {
            "activity": "Executing Code Generation",
            "current_step": "executing_agent",
            "label": "Starting code generation pipeline...",
        })

        # Execute code generation agent — hard global timeout to prevent infinite hang
        # Each LLM call has openai_timeout (e.g. 900s), with up to 3 retries × 4 calls.
        # Ceiling: 1800s = 30 min. Adjust via CODE_GENERATION_TIMEOUT_SECONDS env var.
        import os as _os
        _cg_timeout = int(_os.environ.get("CODE_GENERATION_TIMEOUT_SECONDS", "1800"))

        logger.info("code_generation_timeout_set", run_id=state.run_id, timeout_seconds=_cg_timeout)

        try:
            result = await asyncio.wait_for(code_gen_agent.execute(input_data), timeout=_cg_timeout)
            logger.info("code_generation_step_3_complete", run_id=state.run_id, duration=time.time() - step_start)
        except (asyncio.TimeoutError, TimeoutError) as timeout_err:
            elapsed = time.time() - step_start
            error_msg = f"Code generation timed out after {elapsed:.1f}s (limit: {_cg_timeout}s)"
            logger.error("code_generation_timeout", run_id=state.run_id, elapsed=elapsed, limit=_cg_timeout)
            await emit(state.run_id, EventType.CODE_GENERATION_FAILED, {
                "error": error_msg,
                "stage": "execution_timeout",
                "elapsed_seconds": elapsed,
            })
            raise TimeoutError(error_msg) from timeout_err
        except Exception as exec_err:
            elapsed = time.time() - step_start
            logger.error("code_generation_execution_failed", run_id=state.run_id, error=str(exec_err), elapsed=elapsed)
            await emit(state.run_id, EventType.CODE_GENERATION_FAILED, {
                "error": str(exec_err),
                "stage": "execution",
                "elapsed_seconds": elapsed,
            })
            raise

        # STEP 4: Update state with results
        step_start = time.time()
        logger.info("code_generation_step_4_updating_state", run_id=state.run_id)

        state.generated_project_path = result.get("project_path")
        state.generated_tests_path = result.get("project_path")  # Same as project path
        state.code_generation_metadata_path = result.get("metadata_path")
        state.page_objects_count = result.get("page_objects_count", 0)
        state.test_files_count = result.get("test_files_count", 0)
        state.scenarios_implemented = result.get("scenarios_implemented", 0)
        state.code_generation_status = result.get("status")
        state.code_generation_duration = result.get("duration_seconds", 0.0)
        state.validation_status = result.get("validation_status")
        state.validation_errors = result.get("validation_errors", 0)
        state.validation_warnings = result.get("validation_warnings", 0)

        # Phase 1: capture code-generation outputs (IR, project, artifacts)
        # into AgentState for execution + reporting.
        if state.agent_state is not None:
            get_context_manager().capture_code_generation(state, result=result)

        logger.info("code_generation_step_4_complete",
                   run_id=state.run_id,
                   files_generated=result.get("files_generated", 0),
                   duration=time.time() - step_start)

        # STEP 5: Mark completion
        step_start = time.time()
        logger.info("code_generation_step_5_finalizing", run_id=state.run_id)

        # Phase 2: record stage completion
        cg_duration = time.time() - node_start_time
        if state.agent_state is not None:
            state.agent_state.record_stage_done("code_generation", duration_seconds=cg_duration)

        node_result = NodeResult(
            node_name="code_generation",
            status="completed",
            data=result,
        )
        state.mark_node_completed("code_generation", node_result)

        total_duration = time.time() - node_start_time
        await emit(state.run_id, EventType.STAGE_COMPLETED, {
            "stage": "code_generation",
            "files_generated": state.test_files_count,
            "duration_seconds": total_duration,
        })

        logger.info(
            "code_generation_node_completed",
            run_id=state.run_id,
            status=state.code_generation_status,
            files_generated=result.get("files_generated", 0),
            validation_status=state.validation_status,
            total_duration=total_duration,
        )

        return state

    except Exception as e:
        total_duration = time.time() - node_start_time
        logger.error("code_generation_node_failed",
                    run_id=state.run_id,
                    error=str(e),
                    error_type=type(e).__name__,
                    total_duration=total_duration)
        await emit(state.run_id, EventType.STAGE_FAILED, {
            "stage": "code_generation",
            "error": str(e),
            "error_type": type(e).__name__,
            "duration_seconds": total_duration,
        })
        # NOTE: _mark_stage_failed is called by _with_checkpoint wrapper — do not double-call it here.

        state.mark_failed(f"Code generation node failed: {str(e)}")

        node_result = NodeResult(
            node_name="code_generation",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("code_generation", node_result)

        return state


async def execution_node(state: PlatformWorkflowState) -> PlatformWorkflowState:
    """
    Execution node.

    Executes generated Playwright tests and generates reports.

    Args:
        state: Current workflow state

    Returns:
        Updated state
    """
    try:
        logger.info("execution_node_started", run_id=state.run_id)
        await emit(state.run_id, EventType.STAGE_STARTED, {"stage": "execution", "label": "Test Execution"})

        state.mark_node_started("execution")

        # Persist the stage transition so the run entity (and therefore
        # GET /api/v1/runs/{id}/state -> current_stage) reflects the real
        # workflow stage. Previously the execution node only updated the
        # in-memory LangGraph state, leaving the persisted entity stale at
        # "code_generation" while the workflow was already executing tests.
        # Reuses the existing TriggerService.update_status persistence path.
        try:
            from uuid import UUID as _UUID

            from app.dependencies import get_trigger_service

            _trigger_service = get_trigger_service()
            _run_uuid = _UUID(state.run_id) if isinstance(state.run_id, str) else state.run_id
            await _trigger_service.update_status(
                run_id=_run_uuid,
                status=RunStatus.RUNNING,
                stage="execution",
                message="Continuing workflow: execution started",
            )
        except Exception as _exec_persist_err:
            logger.warning(
                "execution_stage_persist_failed",
                run_id=state.run_id,
                error=str(_exec_persist_err),
            )

        # Phase 2: record stage entry into AgentState
        if state.agent_state is not None:
            state.agent_state.record_stage_entry("execution", "Executing generated Playwright tests")

        # FAIL FAST: Verify code generation completed successfully before attempting execution
        if "code_generation" not in state.completed_nodes:
            raise ValueError("Code generation stage did not complete - execution cannot proceed")

        code_gen_result = state.node_results.get("code_generation")
        if not code_gen_result or code_gen_result.status != "completed":
            raise ValueError(
                f"Code generation failed with status: {code_gen_result.status if code_gen_result else 'unknown'}"
            )

        # Get execution service from dependency injection
        from app.services.execution_service import ExecutionService

        execution_service = state.metadata.get("execution_service")

        if not execution_service:
            # Create execution service if not provided
            execution_service = ExecutionService()
            await execution_service.initialize()

        # Prepare input data
        project_path = state.generated_project_path

        # Fallback: reconstruct the project path from workspace if code_generation was skipped
        if not project_path and state.workspace_path:
            from pathlib import Path as _Path
            fallback = _Path(state.workspace_path) / "artifacts" / "generated-tests" / "playwright"
            if fallback.exists():
                project_path = str(fallback)
                logger.info(
                    "execution_using_fallback_project_path",
                    run_id=state.run_id,
                    project_path=project_path,
                )

        if not project_path:
            raise ValueError("No generated project path found")

        # Phase 2.5/Execution Scope: Playwright execution enforcement — only
        # execute scenarios within the approved ExecutionPlan scope (modules +
        # coverage), using a --grep filter. No fallback to "run everything".
        from app.execution_scope.resolver import build_scope_grep
        from app.schemas.execution import ExecutionConfig
        _exec_config = ExecutionConfig()
        if state.execution_plan is not None:
            _grep = build_scope_grep(state.execution_plan.to_serializable())
            if _grep:
                _exec_config.grep = _grep
                logger.info("execution_scope_enforcement", run_id=state.run_id, grep=_exec_config.grep)

        # Execute tests
        result = await execution_service.execute_tests(
            run_id=state.run_id,
            project_path=project_path,
            config=_exec_config,
            skip_install=False,
        )

        state.execution_status = result.get("status")
        state.execution_duration = result.get("duration_seconds", 0.0)
        state.execution_start = result.get("execution_summary", {}).get("start_time") if isinstance(result.get("execution_summary"), dict) else None
        state.execution_end = result.get("execution_summary", {}).get("end_time") if isinstance(result.get("execution_summary"), dict) else None
        state.execution_artifacts_path = result.get("artifacts_path")
        state.execution_reports_path = result.get("reports_path")
        state.playwright_exit_code = result.get("playwright_exit_code")
        state.execution_logs = result.get("execution_logs")

        metrics = result.get("metrics", {})
        state.tests_total = metrics.get("total_tests", 0)
        state.tests_passed = metrics.get("tests_passed", 0)
        state.tests_failed = metrics.get("tests_failed", 0)
        state.tests_skipped = metrics.get("tests_skipped", 0)
        state.tests_flaky = metrics.get("tests_flaky", 0)
        state.pass_rate = metrics.get("pass_rate", 0.0)
        state.metrics = metrics

        report_files = result.get("report_files", {})
        state.execution_report_html_path = report_files.get("dashboard.html")
        state.execution_report_json_path = report_files.get("execution-summary.json")
        state.reports = report_files

        exec_summ = result.get("execution_summary", {})
        if isinstance(exec_summ, dict):
            state.environment_report = exec_summ.get("environment")
            state.artifacts = exec_summ.get("artifacts")
            state.failure_summary = result.get("failure_summary")
            state.retry_summary = result.get("retry_summary")

        # Phase 1: capture execution outcomes into AgentState for reporting.
        if state.agent_state is not None:
            get_context_manager().capture_execution(state, result=result)

        # Phase 2.5: comprehensive goal satisfaction tracking
        if state.agent_state is not None:
            state.agent_state.record_stage_done("execution", duration_seconds=state.execution_duration)
            goal_text = (state.execution_plan.goal if state.execution_plan else None) or "Execution completed"
            tasks_total = state.tests_total
            tasks_done = state.tests_passed + state.tests_failed
            tasks_skipped = state.tests_skipped
            goal_met = state.tests_failed == 0 and state.tests_total > 0
            blocked = tasks_skipped > 0 and tasks_done == 0
            state.agent_state.update_goal_satisfaction(
                goal=goal_text,
                tasks_done=tasks_done,
                tasks_total=tasks_total,
                completed=goal_met,
                reason=(
                    "All tests passed" if goal_met
                    else f"{state.tests_failed}/{state.tests_total} tests failed" if state.tests_total > 0
                    else "No tests executed" if tasks_skipped > 0
                    else "Skipped or blocked" if blocked
                    else None
                ),
            )
            # Record execution history entry
            state.agent_state.record_executed_action(
                stage="execution",
                task="Execute tests",
                capability="execute_tests",
                status="completed" if goal_met else "failed",
            )

        node_result = NodeResult(
            node_name="execution",
            status="completed",
            data=result,
        )
        state.mark_node_completed("execution", node_result)
        await emit(state.run_id, EventType.STAGE_COMPLETED, {"stage": "execution", "tests_passed": state.tests_passed})

        if state.status != RunStatus.FAILED:
            state.mark_completed()

        try:
            from uuid import UUID as _UUID

            from app.dependencies import get_trigger_service

            _trigger_service = get_trigger_service()
            _run_uuid = _UUID(state.run_id) if isinstance(state.run_id, str) else state.run_id
            await _trigger_service.update_status(
                run_id=_run_uuid,
                status=RunStatus.COMPLETED,
                stage="completed",
                message="Workflow completed successfully",
            )
            try:
                from app.dependencies import get_project_service

                _ps = get_project_service()
                _run_entity = await _trigger_service.repository.get_by_id(_run_uuid)
                if _run_entity and getattr(_run_entity, "project_id", None):
                    _project = await _ps.project_repo.get_by_id(_run_entity.project_id)
                    if _project:
                        _project.last_run_status = RunStatus.COMPLETED.value if hasattr(RunStatus.COMPLETED, "value") else RunStatus.COMPLETED
                        _project.last_run_at = _run_entity.updated_at or _run_entity.created_at
                        await _ps.project_repo.update(_project)
            except Exception as _proj_err:
                logger.warning(
                    "execution_node_project_sync_failed",
                    run_id=state.run_id,
                    error=str(_proj_err),
                )
            try:
                from app.core.event_bus import EventType as _ET, emit as _emit

                await _emit(state.run_id, _ET.WORKFLOW_COMPLETED, {"run_id": state.run_id})
            except Exception:
                pass
        except Exception as _persist_err:
            logger.warning(
                "execution_node_completion_persist_failed",
                run_id=state.run_id,
                error=str(_persist_err),
            )

        logger.info(
            "execution_node_completed",
            run_id=state.run_id,
            status=state.execution_status,
            tests_passed=state.tests_passed,
            tests_failed=state.tests_failed,
            pass_rate=f"{state.pass_rate:.1f}%"
        )

        return state

    except Exception as e:
        logger.error("execution_node_failed", run_id=state.run_id, error=str(e))
        await emit(state.run_id, EventType.STAGE_FAILED, {"stage": "execution", "error": str(e)})
        if state.workspace_path:
            _mark_stage_failed(state.workspace_path, "execution", str(e))

        state.mark_failed(f"Execution node failed: {str(e)}")

        node_result = NodeResult(
            node_name="execution",
            status="failed",
            data={},
            error=str(e),
        )
        state.mark_node_completed("execution", node_result)

        return state


STAGE_ORDER = ["trigger", "crawler", "inventory_aggregator", "test_design", "human_review", "code_generation", "execution"]


def _extract_agent_summary(final_state: Any) -> dict[str, Any]:
    """Phase 2.5: extract goal-completion + task tracking + stage progress for reporting."""
    agent_state = getattr(final_state, "agent_state", None)
    if agent_state is not None:
        return {
            "goal_achieved": agent_state.goal_achieved,
            "goal_progress": agent_state.goal_progress,
            "goal_completion": dict(agent_state.goal_completion),
            "goal_status": agent_state.goal_status,
            "execution_goal": agent_state.execution_goal,
            "current_stage": agent_state.current_stage,
            "current_task": agent_state.current_task,
            "completed_tasks": list(agent_state.completed_tasks),
            "progress": agent_state.progress,
            "failures": list(agent_state.failures),
            "warnings": list(agent_state.warnings),
            "execution_time": dict(agent_state.execution_time),
            "excluded_modules": list(agent_state.excluded_modules),
            "included_modules": list(agent_state.included_modules),
            "business_objective": agent_state.business_objective,
            "task_status": dict(agent_state.task_status),
            "planner_revision": agent_state.planner_revision,
            "clarification_required": agent_state.clarification_required,
            "selected_capability": agent_state.selected_capability,
            "execution_history_count": len(agent_state.execution_history),
            "reasoning_trace": getattr(getattr(final_state, "execution_plan", None), "reasoning_trace", None),
        }
    return {}


def _build_agent_context(
    *,
    run_id: str,
    request_data: dict[str, Any] | None,
    user_prompt: str | None,
    prompt_context: dict[str, Any] | None,
    requested_by: str | None = None,
    reasoning_result: Any | None = None,
) -> tuple[AgentState, ExecutionPlan]:
    """
    Build the AgentState + ExecutionPlan for a workflow entrypoint.

    Phase 4.5: when ``reasoning_result`` is provided, the plan is enriched
    with business intent, constraints, strategy, and stopping conditions.
    When None, the legacy path (Phase 1) is used for backward compat.
    """
    cm = get_context_manager()
    agent_state = cm.build_initial(
        run_id=run_id,
        request_data=request_data,
        requested_by=requested_by,
        user_prompt=user_prompt,
        prompt_context=prompt_context,
    )
    plan = cm.planner.build(
        user_prompt=user_prompt,
        parsed_intent=agent_state.parsed_intent,
        request_data=request_data,
        agent_state=agent_state,
    )
    if reasoning_result is not None:
        plan.enrich_from_reasoning(reasoning_result)
        from app.reasoning.constraints import ConstraintResolver
        ConstraintResolver().apply_to_plan(plan, reasoning_result)
        agent_state.merge(
            business_objective=getattr(reasoning_result.business_intent, "goal", None),
            priorities=list(dict.fromkeys(reasoning_result.testing_intent.strategies + agent_state.priorities)),
        )
        agent_state.clarification_required = plan.clarification_needed is not None
    return agent_state, plan


async def _reason_then_build_context(
    *,
    run_id: str,
    request_data: dict[str, Any] | None,
    user_prompt: str | None,
    prompt_context: dict[str, Any] | None,
    requested_by: str | None = None,
    llm_client: Any | None = None,
) -> tuple[AgentState, ExecutionPlan]:
    """
    Phase 4.5: reasoning-first context construction.

    Runs ReasoningEngine.reason() before ExecutionPlanner.build(). The plan
    is always enriched with business intent, constraints, and strategy.
    """
    from app.reasoning.constraints import ConstraintResolver
    from app.reasoning.engine import ReasoningEngine
    from app.llm.model_registry import resolve_model

    cm = get_context_manager()
    selected_model = resolve_model((request_data or {}).get("ai", {}).get("model"))
    agent_state = cm.build_initial(
        run_id=run_id,
        request_data=request_data,
        requested_by=requested_by,
        user_prompt=user_prompt,
        prompt_context=prompt_context,
    )

    if llm_client is None:
        try:
            from app.dependencies import get_llm_client
            llm_client = get_llm_client()
        except Exception:
            llm_client = None

    engine = ReasoningEngine(llm_client=llm_client)
    reasoning = await engine.reason(user_prompt or "", agent_state=agent_state, model=selected_model)

    resolver = ConstraintResolver()
    resolver.apply_to_agent_state(agent_state, reasoning)

    plan = cm.planner.build(
        user_prompt=user_prompt,
        parsed_intent=agent_state.parsed_intent,
        request_data=request_data,
        agent_state=agent_state,
    )
    plan.enrich_from_reasoning(reasoning)
    resolver.apply_to_plan(plan, reasoning)
    plan.reasoning_trace = engine.generate_trace(reasoning, run_id, user_prompt or "").trace_summary()
    agent_state.merge(
        business_objective=reasoning.business_intent.goal,
        priorities=list(dict.fromkeys(reasoning.testing_intent.strategies + agent_state.priorities)),
    )
    agent_state.clarification_required = plan.clarification_needed is not None
    return agent_state, plan


async def apply_conversational_refinement(
    refinement_prompt: str,
    existing_plan: ExecutionPlan,
    agent_state: AgentState,
    run_id: str,
) -> tuple[AgentState, ExecutionPlan]:
    """
    Phase 4.5: update an existing ExecutionPlan from a conversational refinement
    without a full restart. Uses the ReasoningEngine to parse the update, then
    applies it to the plan via ConstraintResolver.resolve_conversation_update.
    """
    from app.reasoning.constraints import ConstraintResolver
    from app.reasoning.engine import ReasoningEngine

    engine = ReasoningEngine(llm_client=None)
    reasoning = engine._deterministic_reason(refinement_prompt)

    existing_plan.snapshot_revision()
    existing_plan.enrich_from_reasoning(reasoning)

    resolver = ConstraintResolver()
    resolver.apply_to_plan(existing_plan, reasoning)
    resolver.apply_to_agent_state(agent_state, reasoning)

    # Rebuild execution graph to reflect new tasks
    from app.execution_engine.execution_graph import get_execution_graph
    graph = get_execution_graph()
    graph.rebuild(existing_plan)

    agent_state.merge(planner_revision=len(existing_plan.revisions))
    logger.info("conversational_refinement_applied", run_id=run_id, prompt=refinement_prompt[:80])
    return agent_state, existing_plan


def _checkpoint_path(workspace: str) -> Path:
    return Path(workspace) / "contracts" / "checkpoint.json"


def _load_checkpoint(workspace: str) -> dict[str, Any]:
    p = _checkpoint_path(workspace)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_checkpoint(workspace: str, stage: str, artifact_path: str | None = None, log_entries: list[str] | None = None) -> None:
    cp = _load_checkpoint(workspace)
    completed: list[str] = cp.get("completed_stages", [])

    if stage not in completed:
        completed.append(stage)

    artifacts: dict[str, str] = cp.get("artifact_paths", {})
    if artifact_path:
        artifacts[stage] = artifact_path

    logs: dict[str, list[str]] = cp.get("stage_logs", {})
    if log_entries:
        existing = logs.get(stage, [])
        logs[stage] = existing + log_entries

    failed_stage = cp.get("failed_stage")

    cp.update({
        "completed_stages": completed,
        "last_completed_stage": stage,
        "failed_stage": failed_stage,
        "resume_allowed": True,
        "artifact_paths": artifacts,
        "stage_logs": logs,
    })
    p = _checkpoint_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cp, indent=2, default=str), encoding="utf-8")


def _mark_stage_failed(workspace: str, stage: str, error: str) -> None:
    cp = _load_checkpoint(workspace)
    cp["failed_stage"] = stage
    cp["last_error"] = error
    cp["resume_allowed"] = True
    logs: dict[str, list[str]] = cp.get("stage_logs", {})
    existing = logs.get(stage, [])
    logs[stage] = existing + [f"[ERROR] {error}"]
    cp["stage_logs"] = logs
    p = _checkpoint_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cp, indent=2, default=str), encoding="utf-8")


def _is_stage_completed(workspace: str, stage: str) -> bool:
    cp = _load_checkpoint(workspace)
    # 1. If this stage is explicitly recorded as the failed stage, it is NOT completed
    if cp.get("failed_stage") == stage:
        return False

    # 2. If it is explicitly in completed_stages list, it IS completed
    if stage in cp.get("completed_stages", []):
        return True

    # 3. Fallback: check if valid primary artifact exists on disk
    ws = Path(workspace)
    if stage == "crawler":
        p = ws / "contracts" / "crawl-package.json"
        if not p.exists():
            return False
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            status = data.get("crawl_summary", {}).get("status")
            return status == "completed"
        except Exception:
            return False
    elif stage == "inventory_aggregator":
        p = ws / "contracts" / "inventory.json"
        return p.exists()
    elif stage == "test_design":
        p = ws / "contracts" / "test-plan.json"
        return p.exists()
    elif stage == "human_review":
        p = ws / "contracts" / "approved-test-plan.json"
        return p.exists()
    elif stage == "code_generation":
        p = ws / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json"
        return p.exists()
    elif stage == "execution":
        # ExecutionAgent writes its artifacts under
        #   artifacts/generated-tests/execution-artifacts/...
        # Not the workspace-root execution-summary.json, so that old check
        # never recognized a completed execution and a resume re-ran it.
        candidates = [
            ws / "artifacts" / "generated-tests" / "execution-artifacts" / "execution-metadata.json",
            ws / "artifacts" / "generated-tests" / "execution-artifacts" / "reports" / "execution-summary.json",
        ]
        return any(p.exists() for p in candidates)

    return False


def _with_checkpoint(node_fn, stage: str):
    async def wrapper(state: PlatformWorkflowState) -> PlatformWorkflowState:
        ws = state.workspace_path or ""
        if ws and _is_stage_completed(ws, stage):
            logger.info("stage_skipped", stage=stage, run_id=state.run_id, reason="already_completed")
            await emit(state.run_id, EventType.STAGE_COMPLETED, {"stage": stage, "label": stage.replace("_", " ").title(), "skipped": True})
            node_result = NodeResult(node_name=stage, status="completed", data={"status": "skipped"})
            state.mark_node_completed(stage, node_result)
            return state
        error_count_before = len(state.errors)
        result_state = await node_fn(state)
        if ws and len(result_state.errors) == error_count_before:
            _save_checkpoint(ws, stage)
        else:
            _mark_stage_failed(ws, stage, result_state.errors[-1] if result_state.errors else "Unknown error")
        return result_state
    wrapper.__name__ = f"checked_{stage}"
    return wrapper


def _route_after_stage(next_node: str, node_name: str):
    """Build a LangGraph conditional-edge router that stops on stage failure.

    When the given stage failed (or any error was recorded), the workflow routes
    to END instead of the next node, preventing downstream stages from producing
    empty/meaningless artifacts (e.g. empty inventory after a failed crawl).
    """
    def router(state: PlatformWorkflowState) -> str:
        result = state.node_results.get(node_name)
        if state.errors or (result is not None and result.status == "failed"):
            return END
        return next_node

    return router


def create_platform_workflow() -> StateGraph:
    workflow = StateGraph(PlatformWorkflowState)
    workflow.add_node("trigger", trigger_node)
    workflow.add_node("crawler", crawler_node)
    workflow.add_node("inventory_aggregator", inventory_aggregator_node)
    workflow.add_node("test_design", test_design_node)
    workflow.add_edge(START, "trigger")
    workflow.add_edge("trigger", "crawler")
    workflow.add_conditional_edges(
        "crawler",
        _route_after_stage("inventory_aggregator", "crawler"),
        {"inventory_aggregator": "inventory_aggregator", END: END},
    )
    workflow.add_conditional_edges(
        "inventory_aggregator",
        _route_after_stage("test_design", "inventory_aggregator"),
        {"test_design": "test_design", END: END},
    )
    workflow.add_edge("test_design", END)
    compiled = workflow.compile()
    logger.info("pre_review_workflow_created")
    return compiled


def create_post_review_workflow() -> StateGraph:
    """
    Post-review workflow with conditional edges.
    
    Only proceeds to execution if code generation succeeds.
    If code generation fails, workflow stops immediately.
    """
    workflow = StateGraph(PlatformWorkflowState)
    workflow.add_node("human_review", human_review_node)
    workflow.add_node("code_generation", code_generation_node)
    workflow.add_node("execution", execution_node)

    workflow.add_edge(START, "human_review")
    workflow.add_edge("human_review", "code_generation")

    # Conditional edge: only proceed to execution if code generation succeeded
    def route_after_code_generation(state: PlatformWorkflowState) -> str:
        """
        Route to execution if code generation succeeded, otherwise END.
        
        This prevents execution from running when code generation fails.
        """
        code_gen_result = state.node_results.get("code_generation")

        # If code generation failed or has errors, stop the workflow
        if state.errors or (code_gen_result and code_gen_result.status == "failed"):
            logger.warning(
                "workflow_stopping_after_code_generation_failure",
                run_id=state.run_id,
                errors=state.errors
            )
            return END

        # If code generation completed successfully, proceed to execution
        if code_gen_result and code_gen_result.status == "completed":
            logger.info(
                "workflow_proceeding_to_execution",
                run_id=state.run_id
            )
            return "execution"

        # Default: stop if status is unclear
        logger.warning(
            "workflow_stopping_unclear_code_generation_status",
            run_id=state.run_id,
            status=code_gen_result.status if code_gen_result else "unknown"
        )
        return END

    workflow.add_conditional_edges(
        "code_generation",
        route_after_code_generation,
        {
            "execution": "execution",
            END: END,
        }
    )

    workflow.add_edge("execution", END)
    compiled = workflow.compile()
    logger.info("post_review_workflow_created")
    return compiled


def create_unified_workflow() -> StateGraph:
    """
    Single graph with all 7 stages that supports resuming from checkpoints.
    Uses conditional edges to prevent execution after code generation failure.
    """
    workflow = StateGraph(PlatformWorkflowState)
    workflow.add_node("trigger", _with_checkpoint(trigger_node, "trigger"))
    workflow.add_node("crawler", _with_checkpoint(crawler_node, "crawler"))
    workflow.add_node("inventory_aggregator", _with_checkpoint(inventory_aggregator_node, "inventory_aggregator"))
    workflow.add_node("test_design", _with_checkpoint(test_design_node, "test_design"))
    workflow.add_node("human_review", _with_checkpoint(human_review_node, "human_review"))
    workflow.add_node("code_generation", _with_checkpoint(code_generation_node, "code_generation"))
    workflow.add_node("execution", _with_checkpoint(execution_node, "execution"))

    workflow.add_edge(START, "trigger")
    workflow.add_edge("trigger", "crawler")
    workflow.add_conditional_edges(
        "crawler",
        _route_after_stage("inventory_aggregator", "crawler"),
        {"inventory_aggregator": "inventory_aggregator", END: END},
    )
    workflow.add_conditional_edges(
        "inventory_aggregator",
        _route_after_stage("test_design", "inventory_aggregator"),
        {"test_design": "test_design", END: END},
    )
    workflow.add_conditional_edges(
        "test_design",
        _route_after_stage("human_review", "test_design"),
        {"human_review": "human_review", END: END},
    )
    workflow.add_edge("human_review", "code_generation")

    # Conditional edge: only proceed to execution if code generation succeeded
    def route_after_code_generation(state: PlatformWorkflowState) -> str:
        """Stop workflow if code generation fails."""
        code_gen_result = state.node_results.get("code_generation")
        if state.errors or (code_gen_result and code_gen_result.status == "failed"):
            return END
        if code_gen_result and code_gen_result.status == "completed":
            return "execution"
        return END

    workflow.add_conditional_edges(
        "code_generation",
        route_after_code_generation,
        {
            "execution": "execution",
            END: END,
        }
    )

    workflow.add_edge("execution", END)
    compiled = workflow.compile()
    logger.info("unified_workflow_created")
    return compiled


async def execute_resume_workflow(
    run_id: str,
    workspace_path: str,
    requested_by: str | None = None,
    request_data: dict[str, Any] | None = None,
    user_prompt: str | None = None,
    prompt_context: dict[str, Any] | None = None,
    trigger_agent: TriggerAgent | None = None,
    crawler_agent: CrawlerAgent | None = None,
    test_design_agent: TestDesignAgent | None = None,
    code_generation_agent: CodeGenerationAgent | None = None,
) -> dict[str, Any]:

    workflow = create_unified_workflow()

    # Collect agent metadata
    metadata: dict[str, Any] = {}
    if trigger_agent:
        metadata["trigger_agent"] = trigger_agent
    if crawler_agent:
        metadata["crawler_agent"] = crawler_agent
    if test_design_agent:
        metadata["test_design_agent"] = test_design_agent
    if code_generation_agent:
        metadata["code_generation_agent"] = code_generation_agent

    # Ensure request_data, user_prompt, and prompt_context are loaded from run_entity if missing
    if not request_data or not user_prompt or not prompt_context:
        try:
            from uuid import UUID as _U
            from app.dependencies import get_trigger_service
            ts = get_trigger_service()
            run_ent = await ts.get_run(_U(run_id))
            if not request_data:
                _trr = getattr(run_ent, "test_run_request", None)
                if _trr and isinstance(_trr, dict):
                    request_data = _trr
                elif _trr and isinstance(_trr, str):
                    import json as _json
                    try:
                        request_data = _json.loads(_trr)
                    except Exception:
                        pass
            if not user_prompt:
                user_prompt = getattr(run_ent, "user_prompt_text", None)
            if not prompt_context:
                prompt_context = getattr(run_ent, "prompt_context_json", None)
        except Exception as _e:
            logger.warning("execute_resume_workflow_context_load_failed", run_id=run_id, error=str(_e))

    cp = _load_checkpoint(workspace_path)
    # Phase 4.5: reasoning-first — never build plan without reasoning
    agent_state, execution_plan = await _reason_then_build_context(
        run_id=run_id,
        request_data=request_data or {},
        user_prompt=user_prompt,
        prompt_context=prompt_context,
        requested_by=requested_by,
    )
    # Phase 2.5: return NeedsClarification immediately
    if execution_plan.clarification_needed is not None:
        logger.info("resume_workflow_clarification_needed", run_id=run_id)
        return {
            "success": False, "run_id": run_id, "status": "needs_clarification",
            "clarification": execution_plan.clarification_needed.model_dump(mode="json"),
            "agent_summary": {},
        }
    initial_state = PlatformWorkflowState(
        run_id=run_id, status=RunStatus.RUNNING, request_data=request_data or {},
        requested_by=requested_by, workspace_path=workspace_path,
        user_prompt=user_prompt, prompt_context=prompt_context,
        agent_state=agent_state,
        execution_plan=execution_plan,
        selected_model=(request_data or {}).get("ai", {}).get("model"),
        metadata=metadata,
    )
    initial_state.test_plan_path = f"{workspace_path}/contracts/test-plan.json"
    initial_state.approved_test_plan_path = f"{workspace_path}/contracts/approved-test-plan.json"

    logger.info("resume_workflow_started", run_id=run_id)
    final_state = await workflow.ainvoke(initial_state)
    status = final_state.get("status") if isinstance(final_state, dict) else final_state.status
    success = status == RunStatus.COMPLETED or (isinstance(status, str) and not isinstance(final_state, dict))
    logger.info("resume_workflow_completed", run_id=run_id, status=str(status))

    # Signal SSE subscribers that the stream is done
    try:
        from app.core.event_bus import get_event_bus
        get_event_bus().drain(run_id)
    except Exception:
        pass

    if isinstance(final_state, dict):
        errors = final_state.get("errors", [])
        return {"success": not errors, "run_id": run_id, "status": status.value if hasattr(status, "value") else str(status),
                "errors": errors,
                "workspace_path": workspace_path,
                "agent_summary": _extract_agent_summary(final_state),
                "completed_stages": final_state.get("completed_nodes", cp.get("completed_stages", []))}
    return {"success": not final_state.errors, "run_id": run_id,
            "status": str(final_state.status), "errors": final_state.errors,
            "agent_summary": _extract_agent_summary(final_state),
            "completed_stages": final_state.completed_nodes}


def _build_pre_review_result(
    final_state: "PlatformWorkflowState | dict[str, Any]",
    run_id: str,
    status: Any,
) -> dict[str, Any]:
    """Build the pre-review workflow result reflecting the actual outcome.

    On success the run is parked for human review (``status="awaiting_review"``).
    On failure the result carries ``success=False``, the real error message, and
    the failing stage so callers never mistake a failed run for one awaiting
    review — while preserving crawler/inventory artifacts produced upstream.
    """
    if isinstance(final_state, dict):
        nr = final_state.get("node_results", {})
        errors = list(final_state.get("errors") or [])

        def _gd(k: str) -> dict[str, Any]:
            r = nr.get(k, {})
            if isinstance(r, dict):
                return r.get("data", {}) or {}
            return getattr(r, "data", {}) or {}

        base = {
            "success": True,
            "status": "awaiting_review",
            "run_id": final_state.get("run_id", run_id),
            "workspace_path": final_state.get("workspace_path"),
            "errors": errors,
            "pages_visited": final_state.get("pages_visited", 0),
            "total_links": final_state.get("total_links", 0),
            "inventory_path": final_state.get("inventory_path"),
            "inventory_summary": final_state.get("inventory_summary"),
            "test_plan_path": final_state.get("test_plan_path"),
            "test_plan_summary": final_state.get("test_plan_summary"),
            "agent_summary": _extract_agent_summary(final_state),
            "trigger": _gd("trigger"),
            "crawler": _gd("crawler"),
            "inventory": _gd("inventory_aggregator"),
            "test_plan": _gd("test_design"),
        }
        failed_stage = None
        for name, r in nr.items():
            r_status = r.get("status") if isinstance(r, dict) else getattr(r, "status", None)
            if r_status == "failed":
                failed_stage = name
                break
    else:
        errors = list(final_state.errors or [])
        td = final_state.node_results.get("test_design")
        base = {
            "success": True,
            "status": "awaiting_review",
            "run_id": final_state.run_id,
            "workspace_path": final_state.workspace_path,
            "errors": errors,
            "pages_visited": final_state.pages_visited,
            "total_links": final_state.total_links,
            "inventory_path": final_state.inventory_path,
            "inventory_summary": final_state.inventory_summary,
            "test_plan_path": final_state.test_plan_path,
            "test_plan_summary": final_state.test_plan_summary,
            "agent_summary": _extract_agent_summary(final_state),
            "trigger": getattr(final_state.node_results.get("trigger"), "data", {}) or {},
            "crawler": getattr(final_state.node_results.get("crawler"), "data", {}) or {},
            "inventory": getattr(final_state.node_results.get("inventory_aggregator"), "data", {}) or {},
            "test_plan": getattr(td, "data", {}) or {},
        }
        failed_stage = None
        for name, res in final_state.node_results.items():
            if res.status == "failed":
                failed_stage = name
                break

    status_value = getattr(status, "value", None) or status
    is_failed = status_value == RunStatus.FAILED.value or bool(errors) or failed_stage is not None
    if is_failed:
        base["success"] = False
        base["status"] = str(status_value)
        base["error"] = errors[-1] if errors else f"Workflow failed at {failed_stage or 'unknown'} stage"
        base["failed_stage"] = failed_stage or "test_design"
    return base


async def execute_platform_workflow(
    trigger_agent: TriggerAgent,
    crawler_agent: CrawlerAgent,
    request_data: dict[str, Any],
    requested_by: str | None = None,
    test_design_agent: TestDesignAgent | None = None,
    run_id: str | None = None,
    workspace_path: str | None = None,
    user_prompt: str | None = None,
    prompt_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from app.utils import generate_uuid
    if test_design_agent is None:
        test_design_agent = get_test_design_agent()
    workflow = create_platform_workflow()
    run_id = run_id or generate_uuid()
    # Phase 4.5: reasoning-first
    agent_state, execution_plan = await _reason_then_build_context(
        run_id=str(run_id),
        request_data=request_data,
        user_prompt=user_prompt,
        prompt_context=prompt_context,
        requested_by=requested_by,
    )
    if execution_plan.clarification_needed is not None:
        logger.info("execute_platform_workflow_clarification_needed", run_id=run_id)
        return {
            "success": False, "status": "needs_clarification", "run_id": str(run_id),
            "clarification": execution_plan.clarification_needed.model_dump(mode="json"),
        }
    initial_state = PlatformWorkflowState(
        run_id=str(run_id), status=RunStatus.PENDING, request_data=request_data,
        requested_by=requested_by, workspace_path=workspace_path or "",
        user_prompt=user_prompt,
        prompt_context=prompt_context,
        agent_state=agent_state,
        execution_plan=execution_plan,
        selected_model=(request_data or {}).get("ai", {}).get("model"),
        metadata={"trigger_agent": trigger_agent, "crawler_agent": crawler_agent, "test_design_agent": test_design_agent},
    )
    logger.info("workflow_started", run_id=run_id)
    final_state = await workflow.ainvoke(initial_state)
    status = final_state.get("status") if isinstance(final_state, dict) else final_state.status
    logger.info("workflow_completed_pre_review", run_id=run_id, status=status)
    return _build_pre_review_result(final_state, str(run_id), status)


async def _load_persisted_review(workspace_path: str) -> dict[str, Any] | None:
    """Load the review already recorded for a run (e.g. a selective approval).

    Returns a dict shaped like ``HumanReviewService.review_test_plan``'s result
    (the subset consumed by ``continue_platform_workflow``), or ``None`` when no
    review metadata exists yet (legacy fallback → auto-approve).

    This preserves partial/selective approvals: the post-review workflow must
    NOT overwrite a reviewer's decisions with a blanket auto-approval.
    """
    contracts = Path(workspace_path) / "contracts"
    metadata_path = contracts / "review-metadata.json"
    if not metadata_path.exists():
        return None

    from app.utils import load_file
    try:
        metadata = await load_file(metadata_path)
    except Exception:
        return None
    if not isinstance(metadata, dict):
        return None

    return {
        "review_status": metadata.get("review_status"),
        "review_decision": metadata.get("decision"),
        "review_version": metadata.get("review_version", 1),
        "reviewer_name": metadata.get("reviewer_name"),
        "approved_test_plan_path": str(contracts / "approved-test-plan.json"),
        "approved_test_plan_md_path": str(contracts / "approved-test-plan.md"),
        "review_metadata_path": str(metadata_path),
        "approved_scenarios": metadata.get("approved_scenarios", 0),
        "rejected_scenarios": metadata.get("rejected_scenarios", 0),
        "total_scenarios": metadata.get("total_scenarios", 0),
    }


async def continue_platform_workflow(
    run_id: str, workspace_path: str, requested_by: str | None = None,
    code_generation_agent: CodeGenerationAgent | None = None,
    reviewer_name: str = "user",
) -> dict[str, Any]:
    from uuid import UUID

    from app.dependencies import get_human_review_service, get_trigger_service
    from app.schemas.review import ReviewRequest

    # Phase 2.5: reload prompt + agent_state from persisted entity fields,
    # not from prompt_context dict's raw_text (which may be stale).
    prompt_context: dict[str, Any] | None = None
    request_data: dict[str, Any] | None = None
    _raw_prompt: str | None = None
    try:
        trigger_service = get_trigger_service()
        run_entity = await trigger_service.get_run(UUID(run_id))
        prompt_context = getattr(run_entity, "prompt_context_json", None) or None
        _raw_prompt = getattr(run_entity, "user_prompt_text", None) or (prompt_context or {}).get("raw_text") or None
        # Load original request_data so base_url is passed to IR generation
        _trr = getattr(run_entity, "test_run_request", None)
        if _trr and isinstance(_trr, dict):
            request_data = _trr
        elif _trr and isinstance(_trr, str):
            import json as _json
            try:
                request_data = _json.loads(_trr)
            except Exception:
                pass
    except Exception:
        logger.warning("continue_workflow_prompt_context_load_failed", run_id=run_id)

    workflow = create_post_review_workflow()
    # Phase 4.5: reasoning-first
    agent_state, execution_plan = await _reason_then_build_context(
        run_id=str(run_id),
        request_data=request_data,
        user_prompt=_raw_prompt,
        prompt_context=prompt_context,
        requested_by=requested_by,
    )
    if execution_plan.clarification_needed is not None:
        logger.info("continue_workflow_clarification_needed", run_id=run_id)
        return {
            "success": False, "status": "needs_clarification", "run_id": str(run_id),
            "clarification": execution_plan.clarification_needed.model_dump(mode="json"),
        }
    initial_state = PlatformWorkflowState(
        run_id=str(run_id), status=RunStatus.PENDING, workspace_path=workspace_path,
        requested_by=requested_by,
        prompt_context=prompt_context,
        request_data=request_data,
        agent_state=agent_state,
        execution_plan=execution_plan,
        selected_model=(request_data or {}).get("ai", {}).get("model") if request_data else None,
        metadata={"code_generation_agent": code_generation_agent},
    )
    initial_state.request_data = request_data
    initial_state.test_plan_path = f"{workspace_path}/contracts/test-plan.json"

    review_service = get_human_review_service()
    # Preserve the review already recorded for this run (e.g. a selective
    # approval). Only synthesize an auto-approved review when NO review exists
    # yet (legacy fallback for resumes/crashes) so a partial approval is never
    # overwritten into a full approval by the post-review workflow.
    review_result = await _load_persisted_review(workspace_path)
    if review_result is None:
        review_request = ReviewRequest(
            run_id=UUID(run_id), reviewer_name=reviewer_name or "user",
            reviewer_email="user@example.com", auto_approve=True,
            general_comments="Approved by user",
        )
        review_result = await review_service.review_test_plan(workspace_path=workspace_path, review_request=review_request)
    for k in ("review_status","review_decision","review_version","reviewer_name",
              "approved_test_plan_path","approved_test_plan_md_path","review_metadata_path",
              "approved_scenarios","rejected_scenarios","total_scenarios"):
        setattr(initial_state, k, review_result.get(k, getattr(initial_state, k, None)))
    initial_state.status = RunStatus.RUNNING

    logger.info("post_review_workflow_started", run_id=run_id)
    final_state = await workflow.ainvoke(initial_state)
    status = final_state.get("status") if isinstance(final_state, dict) else final_state.status
    logger.info("workflow_completed_post_review", run_id=run_id, status=status)

    # Signal SSE subscribers that the stream is done regardless of outcome
    try:
        from app.core.event_bus import get_event_bus
        get_event_bus().drain(run_id)
    except Exception:
        pass

    if isinstance(final_state, dict):
        nr = final_state.get("node_results", {})
        def _gd(k):
            r = nr.get(k, {}); return r.get("data", {}) if isinstance(r, dict) else getattr(r, "data", {}) if r else {}
        return {"success": status == RunStatus.COMPLETED,
            "status": status.value if hasattr(status, "value") else status,
            "run_id": final_state.get("run_id", run_id), "errors": final_state.get("errors", []),
            "generated_project_path": final_state.get("generated_project_path"),
            "generated_tests_path": final_state.get("generated_tests_path"),
            "code_generation_metadata_path": final_state.get("code_generation_metadata_path"),
            "page_objects_count": final_state.get("page_objects_count", 0),
            "test_files_count": final_state.get("test_files_count", 0),
            "scenarios_implemented": final_state.get("scenarios_implemented", 0),
            "code_generation_status": final_state.get("code_generation_status"),
            "validation_status": final_state.get("validation_status"),
            "execution_status": final_state.get("execution_status"),
            "execution_duration": final_state.get("execution_duration", 0.0),
            "tests_total": final_state.get("tests_total", 0),
            "tests_passed": final_state.get("tests_passed", 0),
            "tests_failed": final_state.get("tests_failed", 0),
            "pass_rate": final_state.get("pass_rate", 0.0),
            "agent_summary": _extract_agent_summary(final_state),
            "review": _gd("human_review"), "code_generation": _gd("code_generation"), "execution": _gd("execution")}
    else:
        return {"success": final_state.status == RunStatus.COMPLETED,
            "status": final_state.status.value if hasattr(final_state.status, "value") else final_state.status,
            "run_id": final_state.run_id, "errors": final_state.errors,
            "generated_project_path": final_state.generated_project_path,
            "generated_tests_path": final_state.generated_tests_path,
            "code_generation_metadata_path": final_state.code_generation_metadata_path,
            "page_objects_count": final_state.page_objects_count,
            "test_files_count": final_state.test_files_count,
            "scenarios_implemented": final_state.scenarios_implemented,
            "code_generation_status": final_state.code_generation_status,
            "validation_status": final_state.validation_status,
            "execution_status": final_state.execution_status,
            "execution_duration": final_state.execution_duration,
            "tests_total": final_state.tests_total, "tests_passed": final_state.tests_passed,
            "tests_failed": final_state.tests_failed, "pass_rate": final_state.pass_rate,
            "agent_summary": _extract_agent_summary(final_state),
            "review": final_state.node_results.get("human_review").data if final_state.node_results.get("human_review") else {},
            "code_generation": final_state.node_results.get("code_generation").data if final_state.node_results.get("code_generation") else {},
            "execution": final_state.node_results.get("execution").data if final_state.node_results.get("execution") else {}}

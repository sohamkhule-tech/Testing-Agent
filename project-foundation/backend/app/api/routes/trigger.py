import asyncio
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.agents import CrawlerAgent, TriggerAgent
from app.dependencies import get_code_generation_agent, get_crawler_agent, get_project_service, get_test_design_agent, get_trigger_agent, get_trigger_service
from app.exceptions import NotFoundError, ValidationError
from app.llm.model_registry import UnsupportedModelError, resolve_model
from app.logging import get_logger
from app.schemas import CreateRunRequest, RunResponse, RunStatusResponse
from app.schemas.project import RunListResponse, TestRunResponse
from app.services import ProjectService, TriggerService
from app.workflows import execute_platform_workflow

logger = get_logger("api.trigger")

router = APIRouter(prefix="/runs", tags=["Test Runs"])


async def _run_pre_review_workflow(
    run_id_str: str,
    workspace_path: str,
    project_id: UUID | None,
    request_data: dict,
    requested_by: str | None,
    user_prompt: str | None = None,
    prompt_context: dict | None = None,
):
    from app.dependencies import get_crawler_agent as _gca, get_trigger_agent as _gta
    from uuid import UUID as _U
    try:
        ts = await _get_ts(run_id_str)
        trigger_agent = _gta()
        crawler_agent = _gca()
        result = await execute_platform_workflow(
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            request_data=request_data,
            requested_by=requested_by,
            run_id=run_id_str,
            workspace_path=workspace_path,
            user_prompt=user_prompt,
            prompt_context=prompt_context,
        )
        run_id = _U(run_id_str)
        entity = await ts.get_run(run_id)
        if project_id:
            entity.project_id = project_id
            await ts.repository.update(entity)

        # A failed/needs-clarification workflow result must NOT be parked as
        # awaiting review. Surface the real error (e.g. Test Design LLM 500) and
        # preserve the crawler/inventory results produced before the failure.
        if not result.get("success") or result.get("status") in ("failed", "needs_clarification"):
            failed_stage = result.get("failed_stage") or "failed"
            error = (
                result.get("error")
                or (result.get("errors") or [""])[-1]
                or "Workflow failed"
            )
            await ts.update_status(run_id, RS.FAILED, stage=failed_stage, error=error)
            from app.core.event_bus import EventType, emit
            await emit(run_id_str, EventType.WORKFLOW_FAILED, {
                "run_id": run_id_str,
                "error": error,
                "stage": failed_stage,
                "status": result.get("status", "failed"),
            })
            if project_id:
                await _mark_project_run_failed(project_id)
            logger.error("run_pre_review_failed", run_id=run_id_str, stage=failed_stage, error=error)
            return

        await ts.update_status(run_id, RS.PAUSED, stage="awaiting_review", message="Test design completed. Please review.")
        from app.core.event_bus import EventType, emit
        test_plan_summary = result.get("test_plan_summary") or {}
        await emit(run_id_str, EventType.HUMAN_REVIEW_REQUIRED, {
            "message": "Test plan is ready for human review.",
            "test_plan_path": result.get("test_plan_path", ""),
            "scenario_count": test_plan_summary.get("scenario_count", 0),
            "modules": test_plan_summary.get("modules", 0),
        })
        logger.info("run_awaiting_review", run_id=run_id_str)
    except BaseException as e:
        logger.error("background_workflow_failed", run_id=run_id_str, error=str(e))
        try:
            ts = await _get_ts(run_id_str)
            await ts.update_status(_U(run_id_str), RS.FAILED, stage="failed", error=str(e))
            from app.core.event_bus import EventType, emit
            await emit(run_id_str, EventType.WORKFLOW_FAILED, {"run_id": run_id_str, "error": str(e)})
            if project_id:
                await _mark_project_run_failed(project_id)
        except Exception:
            pass


async def _get_ts(run_id_str):
    """Get trigger service helper."""
    from app.dependencies import get_trigger_service as _gts
    return _gts()


async def _mark_project_run_failed(project_id: UUID) -> None:
    """Best-effort update of the parent project's last run status."""
    try:
        from app.dependencies import get_project_service
        ps = get_project_service()
        project = await ps.project_repo.get_by_id(project_id)
        if project:
            project.last_run_status = RS.FAILED
            project.last_run_at = datetime.utcnow()
            await ps.project_repo.update(project)
    except Exception:
        pass


from app.constants import RunStatus as RS


@router.post(
    "",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Create new test run",
    description="Returns immediately. Workflow runs in background: Trigger → Crawler → Inventory → Test Design → pauses for review.",
    responses={
        202: {"description": "Run created and queued for execution"},
        400: {"description": "Invalid request"},
    },
)
async def create_run(
    body: dict = Body(...),
    service: TriggerService = Depends(get_trigger_service),
    project_service: ProjectService = Depends(get_project_service),
) -> dict:
    from app.config import get_settings as _gs
    _s = _gs()
    if not _s.llm.openai_api_key and not _s.llm.openai_base_url:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No LLM configured. Set OPENAI_API_KEY or OPENAI_BASE_URL in .env.")

    import asyncio
    from app.utils import generate_uuid, generate_correlation_id
    from datetime import datetime
    from app.domain import RunContext
    from app.infrastructure import WorkspaceManager

    project_id = None
    raw_prompt = body.get("user_prompt") or body.get("test_instructions") or ""
    try:
        # --- Phase 1/2: resolve prompt (run-level overrides project default) ---
        if "project_id" in body and body["project_id"]:
            project_id = UUID(body["project_id"])
            project = await project_service.get_project(project_id)
            # Fall back to project default when caller sends no prompt
            if not raw_prompt and getattr(project, "default_prompt_text", None):
                raw_prompt = project.default_prompt_text or ""
            request = CreateRunRequest(
                target_application={"base_url": str(project.application_url)},
                scope={"max_pages": 50, "max_depth": 5},
                authentication=(body.get("authentication") if isinstance(body.get("authentication"), dict) else {}),
                ai=(body.get("ai") if isinstance(body.get("ai"), dict) else {}),
            )
        else:
            request = CreateRunRequest(**body)

        selected_model = resolve_model(request.ai.model)
        request.ai.model = selected_model

        # --- Phase 4/5: parse prompt → intent + credentials ---
        from app.services.prompt_builder import get_prompt_parser, get_credential_store
        parser = get_prompt_parser()
        parsed_intent, auth_context = parser.parse(raw_prompt)

        # Structured `authentication` payload takes priority over anything
        # parsed from the prompt text. This is the reliable SSO entry point:
        # a login URL can be supplied even without form credentials.
        _auth_payload = getattr(request, "authentication", None)
        if _auth_payload is not None:
            _login_url = getattr(_auth_payload, "login_url", None)
            _strategy = getattr(_auth_payload, "login_strategy", None)
            if _login_url:
                auth_context.login_url = str(_login_url)
            if _strategy and _strategy != "none":
                auth_context.auth_strategy = _strategy

        # --- Phase 1: enrich intent with the Hybrid Intent Parser (LLM) when enabled ---
        from app.agent.config import get_agent_config as _get_agent_config
        from app.context import get_hybrid_intent_parser
        _prompt_context = parsed_intent.to_dict()
        if _get_agent_config().intent_engine_enabled and raw_prompt:
            from app.dependencies import get_llm_client
            _hybrid = get_hybrid_intent_parser(llm_client=get_llm_client())
            _hybrid_result = await _hybrid.parse(raw_prompt, model=selected_model)
            if _hybrid_result.source == "hybrid":
                _prompt_context = dict(_hybrid_result.prompt_context)
                _prompt_context.update({
                    "goal": _hybrid_result.goal,
                    "priorities": _hybrid_result.priorities,
                    "business_objective": _hybrid_result.business_objective,
                    "success_criteria": _hybrid_result.success_criteria,
                    "environment": _hybrid_result.environment,
                    "browser": _hybrid_result.browser,
                })
                # Persist the richer prompt_context so post-review/resume can
                # rebuild the AgentState with full intent.
                _parsed_intent_serialized = _prompt_context
            else:
                _parsed_intent_serialized = _prompt_context
        else:
            _parsed_intent_serialized = _prompt_context

        run_id = UUID(generate_uuid())
        request_id = request.request_id or UUID(generate_uuid())
        principal = request.requested_by or "system"
        now = datetime.utcnow()

        ws_manager = WorkspaceManager()
        context = await ws_manager.create_workspace(
            run_id=run_id,
            request_id=request_id,
            correlation_id=generate_correlation_id(),
        )
        ws_path = str(context.workspace_root)

        # Persist encrypted credentials to workspace (never to logs)
        if auth_context.has_auth_config():
            cred_store = get_credential_store()
            cred_store.save(ws_path, auth_context)

        from app.domain import RunEntity
        entity = RunEntity(
            run_id=run_id,
            request_id=request_id,
            project_id=project_id,
            requested_by=principal,
            workspace_path=ws_path,
            status=RS.RUNNING,
            current_stage="initialization",
            progress_percent=0,
            message="Run created. Starting workflow...",
            test_run_request=request.model_dump(mode="json"),
            # Phase 1: persist prompt (credentials already redacted by parser)
            user_prompt_text=parsed_intent.raw_text or None,
            user_prompt_redacted_text=parsed_intent.raw_text or None,
            prompt_context_json=_parsed_intent_serialized,
            prompt_version="v1",
            created_at=now,
            updated_at=now,
        )
        await service.repository.create(entity)

        if project_id:
            try:
                project_entity = await project_service.project_repo.get_by_id(project_id)
                if project_entity:
                    project_entity.total_runs += 1
                    project_entity.last_run_at = now
                    await project_service.project_repo.update(project_entity)
            except Exception as _e:
                logger.warning("project_stats_update_failed", project_id=str(project_id), error=str(_e))

        await service.update_status(run_id, RS.RUNNING, stage="trigger", message="Workflow started.")

        task = asyncio.create_task(_run_pre_review_workflow(
            str(run_id), ws_path, project_id, request.model_dump(mode="json"), principal,
            parsed_intent.raw_text or raw_prompt, _parsed_intent_serialized
        ))

        return {
            "run_id": str(run_id),
            "request_id": str(request_id),
            "status": "running",
            "requested_by": principal,
            "ai_model": selected_model,
            "message": "Workflow started. Poll status endpoint for updates.",
        }
    except UnsupportedModelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    except Exception as e:
        logger.error("run_creation_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to create run: {str(e)}")


@router.get(
    "",
    response_model=RunListResponse,
    summary="List all runs",
    description="Returns paginated list of all runs, sorted by creation time descending.",
)
async def list_runs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    service: TriggerService = Depends(get_trigger_service),
) -> RunListResponse:
    try:
        all_runs = await service.repository.list_all()
        total = len(all_runs)
        start = (page - 1) * page_size
        end = start + page_size
        from app.services.project_service import determine_run_stage
        page_runs = all_runs[start:end]
        runs = []
        for r in page_runs:
            ws_path = getattr(r, 'workspace_path', None)
            real_stage = determine_run_stage(ws_path, getattr(r, 'current_stage', None))
            test_run_request = getattr(r, "test_run_request", {}) or {}
            ai_model = (test_run_request.get("ai") or {}).get("model") if isinstance(test_run_request, dict) else None
            runs.append(TestRunResponse(
                run_id=r.run_id,
                request_id=r.request_id,
                project_id=getattr(r, 'project_id', None),
                status=r.status,
                current_phase=real_stage,
                started_at=r.created_at,
                completed_at=None,
                duration_seconds=None,
                requested_by=r.requested_by,
                workspace_path=r.workspace_path,
                error_message=r.error,
                ai_model=ai_model,
            ))
        return RunListResponse(runs=runs, total=total, page=page, page_size=page_size)
    except Exception as e:
        logger.error("list_runs_failed", error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to list runs")


@router.get(
    "/{run_id}",
    summary="Get run details",
    description="Retrieve complete details for a test run.",
)
async def get_run(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    try:
        from app.services.project_service import determine_run_stage
        entity = await service.get_run(run_id)
        test_run_request = getattr(entity, 'test_run_request', {}) or {}
        ws_path = getattr(entity, 'workspace_path', None)
        real_stage = determine_run_stage(ws_path, getattr(entity, 'current_stage', None))
        return {
            "run_id": str(entity.run_id),
            "request_id": str(entity.request_id),
            "project_id": str(entity.project_id) if getattr(entity, 'project_id', None) else None,
            "status": entity.status.value if hasattr(entity.status, 'value') else entity.status,
            "current_phase": real_stage,
            "started_at": entity.created_at.isoformat() if hasattr(entity.created_at, 'isoformat') else str(entity.created_at),
            "completed_at": None,
            "duration_seconds": None,
            "requested_by": entity.requested_by,
            "workspace_path": entity.workspace_path,
            "pages_visited": None,
            "scenarios_generated": None,
            "review_status": None,
            "error_message": entity.error,
            "ai_model": (test_run_request.get("ai") or {}).get("model") if isinstance(test_run_request, dict) else None,
        }
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except Exception as e:
        logger.error("get_run_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve run")


@router.get(
    "/{run_id}/prompt",
    summary="Get prompt used for a run",
    description="Returns the redacted prompt and parsed intent for the run. Credentials are never returned.",
)
async def get_run_prompt(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    try:
        entity = await service.get_run(run_id)
        return {
            "run_id": str(run_id),
            "user_prompt_redacted_text": getattr(entity, "user_prompt_redacted_text", None),
            "prompt_context": getattr(entity, "prompt_context_json", None) or {},
            "prompt_version": getattr(entity, "prompt_version", "v1"),
        }
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except Exception as e:
        logger.error("get_run_prompt_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve prompt")


@router.get(
    "/{run_id}/status",
    response_model=RunStatusResponse,
    summary="Get run status",
    description="Retrieve current execution status for a test run.",
)
async def get_run_status(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> RunStatusResponse:
    try:
        metadata = await service.get_metadata(run_id)
        return RunStatusResponse(
            run_id=metadata.run_id,
            status=metadata.status,
            created_at=metadata.created_at,
            updated_at=metadata.updated_at,
            current_stage=metadata.current_stage,
            progress_percent=metadata.progress_percent,
            message=metadata.message,
        )
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except Exception as e:
        logger.error("get_status_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to retrieve status")


@router.get(
    "/{run_id}/timeline",
    summary="Get run workflow timeline",
    description="Returns workflow phase statuses for a run.",
)
async def get_run_timeline(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    from pathlib import Path
    try:
        entity = await service.get_run(run_id)
        workspace = Path(entity.workspace_path)
        metadata = await service.get_metadata(run_id)
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")

    stages = [
        ("trigger", "contracts/test-run-request.json"),
        ("crawler", "contracts/crawl-package.json"),
        ("inventory", "contracts/inventory.json"),
        ("test_design", "contracts/test-plan.json"),
        ("human_review", "contracts/approved-test-plan.json"),
        ("code_generation", "artifacts/generated-tests/playwright/code-generation-metadata.json"),
        ("execution", "artifacts"),
    ]

    phases = []
    for stage_name, rel_path in stages:
        file_path = workspace / rel_path
        exists = file_path.exists()
        is_current = metadata.current_stage == stage_name

        if stage_name == "trigger":
            phases.append({"phase": stage_name, "status": "completed", "started_at": metadata.created_at.isoformat(), "completed_at": metadata.updated_at.isoformat()})
        elif exists:
            phases.append({"phase": stage_name, "status": "completed"})
        elif metadata.status == "failed" and is_current:
            phases.append({"phase": stage_name, "status": "failed", "error": metadata.error})
        elif is_current:
            phases.append({"phase": stage_name, "status": "running"})
        else:
            phases.append({"phase": stage_name, "status": "pending"})

    return {"run_id": str(run_id), "phases": phases, "overall_status": metadata.status.value if hasattr(metadata.status, 'value') else metadata.status}


async def _run_post_review_workflow(
    run_id_str: str,
    workspace_path: str,
    requested_by: str | None,
    reviewer_name: str,
    code_gen_agent,
) -> None:
    """Background task: runs code generation + execution after human review approval.

    Mirrors the pattern used by _run_pre_review_workflow. Returns 202 immediately;
    the workflow completes asynchronously. Never blocks the HTTP handler, so proxy
    timeouts and client disconnects cannot cancel the workflow mid-flight.
    """
    from uuid import UUID as _U
    from app.constants import RunStatus as RS
    from app.core.event_bus import EventType, emit as _emit
    from app.workflows import continue_platform_workflow

    async def _finalize_project_stats(run_id: _U, status: str) -> None:
        try:
            from app.dependencies import get_project_service
            ps = get_project_service()
            entity = await ts.repository.get_by_id(run_id)
            if entity and entity.project_id:
                project = await ps.project_repo.get_by_id(entity.project_id)
                if project:
                    project.last_run_status = status
                    project.last_run_at = entity.updated_at or entity.created_at
                    await ps.project_repo.update(project)
        except Exception:
            pass

    try:
        ts = await _get_ts(run_id_str)
        run_id = _U(run_id_str)
        await ts.update_status(run_id, RS.RUNNING, stage="code_generation", message="Continuing workflow: code generation started")
        result = await continue_platform_workflow(
            run_id=run_id_str,
            workspace_path=workspace_path,
            requested_by=requested_by,
            code_generation_agent=code_gen_agent,
            reviewer_name=reviewer_name,
        )
        if result.get("success"):
            await ts.update_status(run_id, RS.COMPLETED, stage="completed", message="Workflow completed successfully")
            await _emit(run_id_str, EventType.WORKFLOW_COMPLETED, {"run_id": run_id_str})
            await _finalize_project_stats(run_id, "completed")
        elif result.get("status") == "paused" or result.get("code_generation_status") == "awaiting_review":
            # No approved test scenarios under the persisted review — park the
            # run for another human review instead of reporting a failure.
            await ts.update_status(
                run_id, RS.PAUSED, stage="human_review",
                message="Awaiting human review approval — no approved test scenarios.",
            )
            await _emit(run_id_str, EventType.WORKFLOW_PAUSED, {
                "run_id": run_id_str, "stage": "human_review",
            })
        else:
            errors = "; ".join(result.get("errors", []))
            await ts.update_status(run_id, RS.FAILED, stage="failed", message=errors)
            await _emit(run_id_str, EventType.WORKFLOW_FAILED, {"run_id": run_id_str, "error": errors})
            await _finalize_project_stats(run_id, "failed")
    except BaseException as e:  # catch CancelledError and all other exceptions
        logger.error("post_review_workflow_failed", run_id=run_id_str, error=str(e))
        try:
            from uuid import UUID as _U
            ts = await _get_ts(run_id_str)
            from app.constants import RunStatus as RS
            run_id = _U(run_id_str)
            await ts.update_status(run_id, RS.FAILED, stage="failed", error=str(e))
            await _finalize_project_stats(run_id, "failed")
            from app.core.event_bus import EventType, emit as _emit
            await _emit(run_id_str, EventType.WORKFLOW_FAILED, {"run_id": run_id_str, "error": str(e)})
        except Exception:
            pass


# Guard against duplicate post-review workflows (double approve / retried
# POST) for the SAME run: only one background post-review task may be in
# flight per run_id at a time. Prevents two execution_node -> two Playwright
# subprocesses running concurrently on the same project directory.
_post_review_busy: set[str] = set()


def _acquire_post_review(run_id: str) -> bool:
    """Atomically mark a run as having a post-review workflow in flight."""
    if run_id in _post_review_busy:
        return False
    _post_review_busy.add(run_id)
    return True


def _release_post_review(run_id: str) -> None:
    """Release the in-flight marker for a run (idempotent)."""
    _post_review_busy.discard(run_id)


class _ApproveRunRequest(BaseModel):
    """Optional body for POST /runs/{run_id}/approve.

    When ``test_case_ids`` is provided, ONLY those test cases are approved;
    every other scenario in the run's test plan stays pending (partial review).
    Omitting the body (or sending no ``test_case_ids``) preserves the legacy
    approve-the-entire-plan behaviour.
    """

    test_case_ids: list[str] | None = Field(
        default=None,
        description="Scenario/test-case IDs to approve. None = approve all.",
    )


@router.post(
    "/{run_id}/approve",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Approve test plan (optionally a subset) and continue workflow",
    description=(
        "Approves the test plan and kicks off Code Generation in a background "
        "task. Returns 202 immediately. When the body contains test_case_ids, "
        "ONLY those test cases are approved and every other scenario remains "
        "pending (partial approval); an empty body approves the whole plan."
    ),
)
async def approve_run(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
    payload: _ApproveRunRequest | None = None,
) -> dict:
    from app.constants import RunStatus as RS
    try:
        entity = await service.get_run(run_id)
        if entity.status == RS.COMPLETED:
            return {
                "run_id": str(run_id),
                "status": "completed",
                "message": "Workflow has already completed code generation and execution."
            }

        if entity.status not in (RS.PAUSED, RS.PENDING, RS.RUNNING):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Run status is '{entity.status}'. Workflow is not awaiting review."
            )

        # ── Selective approval: approve ONLY the requested test-case IDs ─────
        requested_ids = payload.test_case_ids if (payload and payload.test_case_ids is not None) else None
        review_summary: dict | None = None
        if requested_ids is not None:
            if len(requested_ids) == 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No test cases selected for approval.",
                )
            from app.dependencies import get_human_review_service
            human_review_service = get_human_review_service()
            try:
                review_summary = await human_review_service.approve_selected_scenarios(
                    workspace_path=entity.workspace_path,
                    run_id=run_id,
                    reviewer_name=entity.requested_by or "user",
                    scenario_ids=requested_ids,
                )
            except ValidationError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc

        # Idempotency: if a post-review task is already in flight for this
        # run (e.g. double-click Approve or a retried HTTP POST), do not spawn
        # a second code-generation + execution pipeline.
        run_key = str(run_id)
        if not _acquire_post_review(run_key):
            logger.info("approve_duplicate_ignored", run_id=str(run_id))
            return {
                "run_id": run_key,
                "status": "running",
                "message": "Code generation is already in progress for this run."
            }

        message = "Review approved. Code generation starting in background."
        if review_summary is not None:
            approved_count = len(review_summary.get("approved_test_case_ids") or [])
            total_count = review_summary.get("total_scenarios") or 0
            message = (
                f"Approved {approved_count} of {total_count} test cases. "
                "Code generation starting in background."
            )
        await service.update_status(run_id, RS.RUNNING, stage="human_review", message=message)
        code_gen_agent = get_code_generation_agent()

        import asyncio
        task = asyncio.create_task(_run_post_review_workflow(
            str(run_id), entity.workspace_path, entity.requested_by,
            entity.requested_by or "user", code_gen_agent,
        ))
        # Log unhandled task exceptions without swallowing them
        def _on_task_done(t: asyncio.Task) -> None:
            _release_post_review(run_key)
            exc = t.exception() if not t.cancelled() else None
            if exc:
                logger.error("post_review_task_unhandled_exception", run_id=str(run_id), error=str(exc))
        task.add_done_callback(_on_task_done)

        response: dict = {
            "run_id": str(run_id),
            "status": "running",
            "message": message,
        }
        if review_summary is not None:
            response.update({
                "approved_test_case_ids": review_summary.get("approved_test_case_ids") or [],
                "review_status": review_summary.get("review_status"),
                "review_decision": review_summary.get("review_decision"),
                "approved_scenarios": review_summary.get("approved_scenarios"),
                "total_scenarios": review_summary.get("total_scenarios"),
            })
        return response
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("approve_run_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to approve run: {str(e)}")


@router.post(
    "/{run_id}/reject",
    status_code=status.HTTP_200_OK,
    summary="Reject test plan with feedback",
    description="Rejects the test plan, stores feedback, and marks run as needing changes.",
)
async def reject_run(
    run_id: UUID,
    body: dict = Body(...),
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    from app.constants import RunStatus as RS
    try:
        entity = await service.get_run(run_id)
        if entity.status not in (RS.PAUSED, RS.PENDING):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run is not awaiting review")

        feedback = body.get("feedback", "")
        await service.update_status(
            run_id, RS.FAILED,
            stage="changes_requested",
            message=f"Test plan rejected. Feedback: {feedback[:200]}",
        )

        from app.core.event_bus import EventType, emit
        import asyncio
        asyncio.create_task(emit(run_id, EventType.HUMAN_REVIEW_REJECTED, {
            "message": "Test plan was rejected.",
            "feedback": feedback,
        }))

        logger.info("run_rejected", run_id=str(run_id))
        return {"success": True, "status": "rejected", "message": "Feedback recorded. You may re-run with the feedback to regenerate.", "feedback": feedback}
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("reject_run_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to reject run: {str(e)}")


@router.get(
    "/{run_id}/failure",
    summary="Get failure details for a run",
    description="Returns detailed failure information: failed stage, reason, stacktrace, retry count, and recovery suggestions.",
)
async def get_run_failure(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    try:
        entity = await service.get_run(run_id)
        ws = entity.workspace_path
        from pathlib import Path as _Path
        import json as _json
        cp_raw: dict = {}
        cp_path = _Path(ws) / "contracts" / "checkpoint.json"
        if cp_path.exists():
            cp_raw = _json.loads(cp_path.read_text(encoding="utf-8"))

        failed_stage = cp_raw.get("failed_stage")
        last_error = cp_raw.get("last_error") or entity.error
        completed = cp_raw.get("completed_stages", [])
        logs = cp_raw.get("stage_logs", {}).get(failed_stage or "", [])

        # Infer from entity if no checkpoint
        if not failed_stage:
            status_str = entity.status.value if hasattr(entity.status, "value") else entity.status
            if status_str in ("failed", "paused") and entity.current_stage:
                failed_stage = entity.current_stage
            last_error = last_error or entity.error

        # Format stacktrace from logs
        error_lines = [l for l in logs if "[ERROR]" in l] if logs else [last_error] if last_error else []
        info_lines = [l for l in logs if "[INFO]" in l] if logs else []

        return {
            "run_id": str(run_id),
            "failed_stage": failed_stage,
            "failure_reason": last_error,
            "failure_stacktrace": error_lines,
            "stage_logs": info_lines,
            "retry_count": cp_raw.get("retry_count", 0),
            "resume_allowed": cp_raw.get("resume_allowed", bool(failed_stage)),
            "completed_stages": completed,
            "status": entity.status.value if hasattr(entity.status, "value") else entity.status,
        }
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except Exception as e:
        logger.error("get_run_failure_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{run_id}/state",
    summary="Get run checkpoint state",
    description="Returns the current checkpoint state: completed stages, failed stage, artifact paths, resume eligibility.",
)
async def get_run_state(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    try:
        entity = await service.get_run(run_id)
        ws = entity.workspace_path
        from pathlib import Path as _Path
        cp_raw = {}
        cp_path = _Path(ws) / "contracts" / "checkpoint.json"
        if cp_path.exists():
            import json as _json
            cp_raw = _json.loads(cp_path.read_text(encoding="utf-8"))

        completed = cp_raw.get("completed_stages", [])
        failed = cp_raw.get("failed_stage")
        resume_allowed = cp_raw.get("resume_allowed", False) or bool(failed)
        artifacts = cp_raw.get("artifact_paths", {})
        logs = cp_raw.get("stage_logs", {})
        last_error = cp_raw.get("last_error") or getattr(entity, "error", None)

        # `completed_stages` is authoritative for the frontend's reconstruction.
        # It is derived from BOTH the persisted checkpoint list AND reliable
        # filesystem/workflow evidence. This guarantees that a partial or stale
        # checkpoint can never omit an actually-completed stage (e.g.
        # `test_design`), which would otherwise cause the frontend to leave a
        # completed stage shown as `running` or to double-run stages.
        workspace_path = _Path(ws)

        def _has_valid_execution_results() -> bool:
            results_path = workspace_path / "artifacts" / "generated-tests" / "playwright" / "test-results" / "results.json"
            if not results_path.exists():
                return False
            try:
                import json as _json

                data = _json.loads(results_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    return False
                stats = data.get("stats", {})
                suites = data.get("suites", [])
                if isinstance(stats, dict) and (stats.get("expected", 0) > 0 or stats.get("unexpected", 0) > 0 or stats.get("flaky", 0) > 0 or stats.get("skipped", 0) > 0):
                    return True
                if suites:
                    return True
                return False
            except Exception:
                return False

        def _execution_summary_indicates_completion() -> bool:
            candidates = [
                workspace_path / "artifacts" / "generated-tests" / "execution-artifacts" / "reports" / "execution-summary.json",
                workspace_path / "artifacts" / "generated-tests" / "execution-artifacts" / "execution-metadata.json",
            ]
            for p in candidates:
                if p.exists():
                    try:
                        import json as _json

                        data = _json.loads(p.read_text(encoding="utf-8"))
                        if isinstance(data, dict):
                            status = str(data.get("status", "")).lower()
                            if status in ("completed", "completed_with_failures", "passed"):
                                return True
                            if data.get("classification") in ("test_execution_completed_with_failures", "passed"):
                                return True
                    except Exception:
                        continue
            return False

        def _infer_completed_from_files() -> list[str]:
            inferred: list[str] = ["trigger"]
            if (workspace_path / "contracts" / "crawl-package.json").exists():
                inferred.append("crawler")
            if (workspace_path / "contracts" / "inventory.json").exists():
                inferred.append("inventory")
                inferred.append("inventory_aggregator")
            if (workspace_path / "contracts" / "test-plan.json").exists():
                inferred.append("test_design")
            if (workspace_path / "contracts" / "approved-test-plan.json").exists():
                inferred.append("human_review")
            if (workspace_path / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json").exists():
                inferred.append("code_generation")
            if _has_valid_execution_results() or _execution_summary_indicates_completion():
                inferred.append("execution")
                inferred.append("report")
            return inferred

        # Union checkpoint list + filesystem inference, deduplicated, and never
        # marking the recorded failed stage as completed.
        completed_union: list[str] = []
        for s in list(completed) + _infer_completed_from_files():
            if s in completed_union:
                continue
            if failed and s == failed:
                continue
            completed_union.append(s)
        completed = completed_union

        # If the run is failed/paused but no checkpoint captured a failed stage,
        # infer it from the entity stage so the response is never a bare failure.
        status_value = entity.status.value if hasattr(entity.status, "value") else entity.status
        if not failed and status_value in ("failed", "paused"):
            stage = entity.current_stage
            if stage and stage not in ("completed", "failed", "initialization", "awaiting_review", "changes_requested"):
                failed = stage
                resume_allowed = True
            elif stage in ("failed", "changes_requested"):
                resume_allowed = True
            elif failed is None and not last_error:
                last_error = "Workflow failed"

        # Determine next stage
        STAGE_ORDER = ["trigger", "crawler", "inventory_aggregator", "test_design", "human_review", "code_generation", "execution"]
        next_stage = None
        for s in STAGE_ORDER:
            if s not in completed:
                next_stage = s
                break

        status_value_raw = entity.status.value if hasattr(entity.status, "value") else entity.status
        normalized_status = str(status_value_raw).lower() if status_value_raw else ""
        if normalized_status == "running" and "execution" in completed and next_stage is None:
            try:
                from app.constants import RunStatus as _RS

                has_genuine_failure = False
                try:
                    exec_meta_path = workspace_path / "artifacts" / "generated-tests" / "execution-artifacts" / "execution-metadata.json"
                    if exec_meta_path.exists():
                        import json as _jm

                        _meta = _jm.loads(exec_meta_path.read_text(encoding="utf-8"))
                        _cls = str(_meta.get("classification", "")).lower()
                        if _cls in ("execution_timeout", "infrastructure_failure", "command_failure"):
                            has_genuine_failure = True
                except Exception:
                    pass
                if not has_genuine_failure:
                    await service.update_status(run_id, _RS.COMPLETED, stage="completed", message="Workflow completed successfully")
                    try:
                        updated = await service.get_run(run_id)
                        entity = updated
                        status_value_raw = entity.status.value if hasattr(entity.status, "value") else entity.status
                    except Exception:
                        pass
                    try:
                        from app.dependencies import get_project_service

                        _ps2 = get_project_service()
                        _run_for_proj = await service.repository.get_by_id(run_id)
                        if _run_for_proj and getattr(_run_for_proj, "project_id", None):
                            _proj = await _ps2.project_repo.get_by_id(_run_for_proj.project_id)
                            if _proj:
                                _proj.last_run_status = _RS.COMPLETED.value if hasattr(_RS.COMPLETED, "value") else _RS.COMPLETED
                                _proj.last_run_at = entity.updated_at or entity.created_at
                                await _ps2.project_repo.update(_proj)
                    except Exception:
                        pass
            except Exception:
                pass
            status_value_raw = entity.status.value if hasattr(entity.status, "value") else entity.status

        return {
            "run_id": str(run_id),
            "status": status_value_raw,
            "current_stage": entity.current_stage,
            "completed_stages": completed,
            "last_completed_stage": cp_raw.get("last_completed_stage"),
            "failed_stage": failed,
            "next_stage": next_stage,
            "resume_allowed": resume_allowed,
            "artifact_paths": artifacts,
            "stage_logs": logs,
            "last_error": last_error,
            "elapsed_time": None,
        }
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except Exception as e:
        logger.error("get_run_state_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get(
    "/{run_id}/logs",
    summary="Get run stage logs",
    description="Returns per-stage log lines captured during workflow execution.",
)
async def get_run_logs(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    try:
        entity = await service.get_run(run_id)
        ws = entity.workspace_path
        from pathlib import Path as _Path
        import json as _json

        workspace_path = _Path(ws)
        cp_path = workspace_path / "contracts" / "checkpoint.json"

        # 1. Try checkpoint.json first (exists if run completed normally)
        stage_logs: dict = {}
        if cp_path.exists():
            cp_raw = _json.loads(cp_path.read_text(encoding="utf-8"))
            stage_logs = cp_raw.get("stage_logs", {})

        # 2. Try event bus replay buffer (exists if backend hasn't been restarted)
        from app.core.event_bus import get_event_bus
        bus_history = get_event_bus().get_history(str(run_id))

        # 3. Reconstruct activity log from on-disk artifacts (restart-proof)
        reconstructed_events: list[dict] = []

        def _add_event(ts: str, stage: str, msg: str, level: str = "info"):
            reconstructed_events.append({
                "timestamp": ts,
                "stage": stage,
                "message": msg,
                "level": level,
            })

        # --- Trigger / workspace setup ---
        meta_file = _Path("storage") / "runs" / "metadata" / f"{run_id}.json"
        if meta_file.exists():
            try:
                meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                ts = meta.get("created_at", "")
                # URL is in test_run_request.target_application.base_url
                tr = meta.get("test_run_request", {})
                url = ""
                if isinstance(tr, dict):
                    ta = tr.get("target_application", {})
                    url = ta.get("base_url", ta.get("url", "")) if isinstance(ta, dict) else ""
                if not url:
                    url = meta.get("url", meta.get("target_url", "(unknown)"))
                _add_event(ts, "trigger", f"✅ Run initialized — target: {url}")
                _add_event(ts, "trigger", f"📁 Workspace created at: {ws}")
            except Exception:
                pass

        # --- Crawler ---
        crawl_file = workspace_path / "contracts" / "crawl-package.json"
        if crawl_file.exists():
            try:
                crawl = _json.loads(crawl_file.read_text(encoding="utf-8"))
                crawl_summary = crawl.get("crawl_summary", {})
                ts_start = crawl_summary.get("start_time", "")
                ts_end = crawl_summary.get("end_time", "")
                total_pages = crawl_summary.get("pages_visited", 0)
                visited_pages = crawl.get("visited_pages", [])
                # Get start URL from inventory or first visited page
                start_url = ""
                inv_f2 = workspace_path / "contracts" / "inventory.json"
                if inv_f2.exists():
                    try:
                        inv2 = _json.loads(inv_f2.read_text(encoding="utf-8"))
                        pages2 = inv2.get("pages", [])
                        if pages2:
                            start_url = pages2[0].get("url", "") if isinstance(pages2[0], dict) else ""
                    except Exception:
                        pass
                if not start_url and visited_pages:
                    start_url = visited_pages[0].get("url", "") if isinstance(visited_pages[0], dict) else ""
                duration_ms = crawl_summary.get("duration", 0)
                _add_event(ts_start, "crawler", f"🌐 Crawler started — target: {start_url}")
                _add_event(ts_start, "crawler", f"🖥️ Launching Chromium browser...")
                _add_event(ts_start, "crawler", f"✅ Browser initialized and context created")
                for i, page in enumerate(visited_pages[:5]):
                    p_url = page.get("url", "") if isinstance(page, dict) else str(page)
                    p_ts = page.get("discovered_at", ts_start) if isinstance(page, dict) else ts_start
                    p_title = page.get("title", "") if isinstance(page, dict) else ""
                    _add_event(p_ts, "crawler", f"📄 [{i+1}/{total_pages}] {p_title or p_url}")
                if total_pages > 5:
                    _add_event(ts_end, "crawler", f"📄 ... and {total_pages - 5} more pages visited")
                # Element stats from crawl package
                forms = len(crawl.get("forms", []))
                inputs = len(crawl.get("inputs", []))
                buttons = len(crawl.get("buttons", []))
                _add_event(ts_end, "crawler", f"🔍 Detected: {forms} forms, {inputs} inputs, {buttons} buttons")
                _add_event(ts_end, "crawler", f"✅ Crawl complete — {total_pages} pages in {duration_ms}ms")
            except Exception:
                pass

        # --- Inventory ---
        inv_file = workspace_path / "contracts" / "inventory.json"
        if inv_file.exists():
            try:
                inv = _json.loads(inv_file.read_text(encoding="utf-8"))
                inv_meta = inv.get("metadata", {})
                ts = inv_meta.get("generated_at", "")
                page_count = inv_meta.get("page_count", 0)
                button_count = inv_meta.get("button_count", 0)
                input_count = inv_meta.get("input_count", 0)
                _add_event(ts, "inventory", f"🗂️ Building UI component inventory from crawl data...")
                _add_event(ts, "inventory", f"📊 Indexed {page_count} pages, {input_count} inputs, {button_count} buttons")
                _add_event(ts, "inventory", f"✅ Inventory aggregation complete")
            except Exception:
                pass

        # --- Test Design / LLM ---
        tp_file = workspace_path / "contracts" / "test-plan.json"
        if tp_file.exists():
            try:
                tp = _json.loads(tp_file.read_text(encoding="utf-8"))
                ts = tp.get("generated_at", tp.get("created_at", ""))
                modules = tp.get("modules", tp.get("test_suites", []))
                total_scenarios = sum(len(m.get("flows", m.get("test_cases", []))) for m in modules) if isinstance(modules, list) else 0
                _add_event(ts, "test_design", f"🤖 LLM call started — analyzing UI inventory for test scenarios...")
                _add_event(ts, "test_design", f"💭 Agent reasoning: identifying testable user flows...")
                _add_event(ts, "test_design", f"📝 Generating {total_scenarios} test scenarios across {len(modules) if isinstance(modules, list) else 0} modules")
                _add_event(ts, "test_design", f"✅ Test plan generated — {total_scenarios} scenarios ready for review")
            except Exception:
                pass

        # --- Human review ---
        atp_file = workspace_path / "contracts" / "approved-test-plan.json"
        if atp_file.exists():
            try:
                atp = _json.loads(atp_file.read_text(encoding="utf-8"))
                ts = atp.get("approved_at", atp.get("reviewed_at", ""))
                _add_event(ts, "human_review", f"👤 Test plan submitted for human review")
                _add_event(ts, "human_review", f"✅ Test plan approved — proceeding to code generation")
            except Exception:
                pass

        # --- Code generation ---
        cg_meta_file = workspace_path / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json"
        if cg_meta_file.exists():
            try:
                cg = _json.loads(cg_meta_file.read_text(encoding="utf-8"))
                ts = cg.get("generated_at", "")
                files = cg.get("files_generated", 0)
                flows = cg.get("flows", 0)
                pages = cg.get("pages", 0)
                _add_event(ts, "code_generation", f"⚙️ Code generation started — IR-driven template engine")
                _add_event(ts, "code_generation", f"🤖 LLM: Building Intermediate Representation (IR) from test plan...")
                _add_event(ts, "code_generation", f"📐 IR generated — {flows} flows across {pages} pages")
                _add_event(ts, "code_generation", f"🔧 Generating Playwright TypeScript test files...")
                # List generated test files
                playwright_dir = workspace_path / "artifacts" / "generated-tests" / "playwright"
                spec_files = list(playwright_dir.glob("tests/**/*.spec.ts")) + list(playwright_dir.glob("*.spec.ts"))
                for sf in spec_files[:10]:
                    _add_event(ts, "code_generation", f"📄 Generated: {sf.name}")
                _add_event(ts, "code_generation", f"✅ Code generation complete — {files} files generated")
            except Exception:
                pass

        # --- Execution ---
        exec_summary = workspace_path / "artifacts" / "generated-tests" / "execution-artifacts" / "reports" / "execution-summary.json"
        if exec_summary.exists():
            try:
                ex = _json.loads(exec_summary.read_text(encoding="utf-8"))
                ts = ex.get("executed_at", ex.get("timestamp", ""))
                total = ex.get("total_tests", ex.get("stats", {}).get("total", 0))
                passed = ex.get("passed", ex.get("stats", {}).get("passed", 0))
                failed = ex.get("failed", ex.get("stats", {}).get("failed", 0))
                duration = ex.get("duration_ms", ex.get("stats", {}).get("duration_ms", 0))
                _add_event(ts, "execution", f"▶️ Running Playwright tests in Chromium...")
                _add_event(ts, "execution", f"🔄 Executing {total} test cases...")
                _add_event(ts, "execution", f"✅ Execution complete — {passed} passed, {failed} failed ({duration}ms)")
            except Exception:
                pass

        # Merge stage_logs dict with reconstructed events
        # Convert reconstructed to stage_logs format
        if reconstructed_events and not stage_logs:
            by_stage: dict = {}
            for ev in reconstructed_events:
                s = ev["stage"]
                by_stage.setdefault(s, []).append(ev["message"])
            stage_logs = by_stage

        # Return both formats for flexibility
        return {
            "run_id": str(run_id),
            "stage_logs": stage_logs,
            "events": [
                {
                    "type": ev.get("type", "activity"),
                    "timestamp": ev.get("timestamp", ""),
                    "stage": ev.get("stage", ""),
                    "message": ev.get("message", ""),
                    "level": ev.get("level", "info"),
                }
                for ev in (
                    # Prefer event bus history (live) then fall back to reconstructed
                    [
                        {
                            "type": e.type,
                            "timestamp": e.timestamp,
                            "stage": e.data.get("stage", ""),
                            "message": e.data.get("message", e.data.get("activity", "")),
                            "level": "info",
                        }
                        for e in bus_history
                        if e.type not in ("ping",)
                    ] if bus_history else reconstructed_events
                )
            ],
            "error": entity.error,
        }
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except Exception as e:
        logger.error("get_run_logs_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


async def _run_resume_workflow_bg(
    run_id_str: str,
    workspace_path: str,
    requested_by: str | None,
    request_data: dict,
    user_prompt: str | None,
    prompt_context: dict | None,
    trigger_agent,
    crawler_agent,
    test_design_agent,
    code_gen_agent,
) -> None:
    """Background task: resumes a failed run from its last failed stage."""
    from uuid import UUID as _U
    from app.constants import RunStatus as RS
    from app.core.event_bus import EventType, emit as _emit
    from app.workflows import execute_resume_workflow

    try:
        ts = await _get_ts(run_id_str)
        result = await execute_resume_workflow(
            run_id=run_id_str,
            workspace_path=workspace_path,
            requested_by=requested_by,
            request_data=request_data,
            user_prompt=user_prompt,
            prompt_context=prompt_context,
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            test_design_agent=test_design_agent,
            code_generation_agent=code_gen_agent,
        )
        run_id = _U(run_id_str)
        if result.get("success"):
            await ts.update_status(run_id, RS.COMPLETED, stage="completed", message="Workflow completed successfully after resume")
            await _emit(run_id_str, EventType.WORKFLOW_COMPLETED, {"run_id": run_id_str})
        else:
            errors = "; ".join(result.get("errors", []))
            failed_stage_name = result.get("failed_stage", "code_generation")
            await ts.update_status(run_id, RS.FAILED, stage=failed_stage_name, message=errors)
            # Mark entity as resumable again
            try:
                ent = await ts.repository.get_by_id(run_id) if hasattr(ts, 'repository') else None
                if ent:
                    ent.failed_stage = failed_stage_name
                    ent.resume_allowed = True
                    await ts.repository.update(ent)
            except Exception:
                pass
            await _emit(run_id_str, EventType.WORKFLOW_FAILED, {"run_id": run_id_str, "error": errors})
    except BaseException as e:
        logger.error("resume_workflow_bg_failed", run_id=run_id_str, error=str(e))
        try:
            from uuid import UUID as _U2
            run_uuid = _U2(run_id_str)
            ts = await _get_ts(run_id_str)
            from app.constants import RunStatus as RS
            await ts.update_status(run_uuid, RS.FAILED, stage="code_generation", error=str(e))
            # Mark entity as resumable again after failure
            try:
                ent = await ts.repository.get_by_id(run_uuid) if hasattr(ts, 'repository') else None
                if ent:
                    ent.failed_stage = ent.current_stage or "code_generation"
                    ent.resume_allowed = True
                    await ts.repository.update(ent)
            except Exception:
                pass
            from app.core.event_bus import EventType, emit as _emit
            await _emit(run_id_str, EventType.WORKFLOW_FAILED, {"run_id": run_id_str, "error": str(e)})
        except Exception:
            pass


@router.post(
    "/{run_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Resume a failed run from the last failed stage",
    description="Restores checkpoint and continues the workflow from the last failed stage in a background task. Returns 202 immediately.",
)
async def resume_run(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    from app.constants import RunStatus as RS
    try:
        entity = await service.get_run(run_id)
        if entity.status not in (RS.FAILED, RS.PAUSED):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Run is not in a resumable state (current: {entity.status})")

        # Guard: a run parked for human review (status=PAUSED,
        # current_stage=awaiting_review) must be approved/rejected, never
        # resumed. Resuming it would spawn a second (unified) workflow
        # execution that can run concurrently with the separate post-review
        # (approve) workflow, duplicating work for the same run.
        _review_stage = getattr(entity, "current_stage", None) or ""
        if entity.status == RS.PAUSED and _review_stage == "awaiting_review":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Run is awaiting human review. Approve or reject the test plan instead of resuming.",
            )

        # Determine failed stage cleanly
        ws = entity.workspace_path
        from pathlib import Path as _Path
        import json as _json

        failed_stage = "unknown"

        # Check if crawl-package.json exists but indicates an error
        _crawl_pkg = _Path(ws) / "contracts" / "crawl-package.json"
        if _crawl_pkg.exists():
            try:
                _pkg_data = _json.loads(_crawl_pkg.read_text(encoding="utf-8"))
                if _pkg_data.get("crawl_summary", {}).get("status") == "error":
                    failed_stage = "crawler"
            except Exception:
                pass

        cp_path = _Path(ws) / "contracts" / "checkpoint.json"
        if cp_path.exists():
            cp = _json.loads(cp_path.read_text(encoding="utf-8"))
            cp_failed = cp.get("failed_stage")
            if cp_failed:
                failed_stage = cp_failed
            elif failed_stage == "unknown":
                failed_stage = getattr(entity, "current_stage", "unknown")

            if failed_stage in ("failed", "initialization", None, "unknown"):
                _codegen_meta = _Path(ws) / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json"
                _contracts = _Path(ws) / "contracts"
                if (_contracts / "approved-test-plan.json").exists() and not _codegen_meta.exists():
                    failed_stage = "code_generation"
                elif (_contracts / "test-plan.json").exists() and not (_contracts / "approved-test-plan.json").exists():
                    failed_stage = "human_review"
                elif (_contracts / "inventory.json").exists() and not (_contracts / "test-plan.json").exists():
                    failed_stage = "test_design"
                elif (_contracts / "crawl-package.json").exists() and not (_contracts / "inventory.json").exists():
                    failed_stage = "inventory"
                else:
                    failed_stage = "crawler"

            # Remove failed stage from completed list if present
            completed = cp.get("completed_stages", [])
            if failed_stage in completed:
                completed.remove(failed_stage)
            cp["completed_stages"] = completed
            cp["failed_stage"] = None
            cp["last_error"] = None
            cp_path.write_text(_json.dumps(cp, indent=2, default=str), encoding="utf-8")
        else:
            if failed_stage == "unknown":
                failed_stage = getattr(entity, "current_stage", "unknown")
            if failed_stage in ("failed", "initialization", None, "unknown"):
                _codegen_meta = _Path(ws) / "artifacts" / "generated-tests" / "playwright" / "code-generation-metadata.json"
                _contracts = _Path(ws) / "contracts"
                if (_contracts / "approved-test-plan.json").exists() and not _codegen_meta.exists():
                    failed_stage = "code_generation"
                elif (_contracts / "test-plan.json").exists() and not (_contracts / "approved-test-plan.json").exists():
                    failed_stage = "human_review"
                elif (_contracts / "inventory.json").exists() and not (_contracts / "test-plan.json").exists():
                    failed_stage = "test_design"
                elif (_contracts / "crawl-package.json").exists() and not (_contracts / "inventory.json").exists():
                    failed_stage = "inventory"
                else:
                    failed_stage = "crawler"

        await service.update_status(run_id, RS.RUNNING, stage=f"resuming_from_{failed_stage}", message=f"Resuming from {failed_stage} in background.")

        from app.dependencies import get_crawler_agent, get_trigger_agent, get_code_generation_agent
        trigger_agent = get_trigger_agent()
        crawler_agent = get_crawler_agent()
        code_gen_agent = get_code_generation_agent()

        import asyncio
        task = asyncio.create_task(_run_resume_workflow_bg(
            run_id_str=str(run_id),
            workspace_path=entity.workspace_path,
            requested_by=entity.requested_by,
            request_data=getattr(entity, "test_run_request", {}),
            user_prompt=getattr(entity, "user_prompt_text", None),
            prompt_context=getattr(entity, "prompt_context_json", None),
            trigger_agent=trigger_agent,
            crawler_agent=crawler_agent,
            test_design_agent=get_test_design_agent(),
            code_gen_agent=code_gen_agent,
        ))

        def _on_resume_done(t: asyncio.Task) -> None:
            exc = t.exception() if not t.cancelled() else None
            if exc:
                logger.error("resume_task_unhandled_exception", run_id=str(run_id), error=str(exc))
        task.add_done_callback(_on_resume_done)

        return {"run_id": str(run_id), "status": "running", "message": f"Resuming from {failed_stage} in background. Poll /state or stream /events for progress."}
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("resume_run_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to resume run: {str(e)}")


@router.post(
    "/{run_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry a failed stage",
    description="Re-runs only the failed stage without rerunning completed stages.",
)
async def retry_run(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    """Retry is semantically identical to resume - re-run from the failed stage onward."""
    from uuid import UUID as _U
    return await resume_run(_U(str(run_id)), service)


@router.post(
    "/analyze-prompt",
    status_code=status.HTTP_200_OK,
    summary="Analyse user prompt before running",
    description=(
        "Returns a structured interpretation of the user prompt including confidence scores, "
        "execution plan, scope summary, credential status, ambiguity warnings, and quality score. "
        "No workflow is started. If the user approves, pass the returned `parsed_intent` to POST /runs."
    ),
)
async def analyze_prompt(
    body: dict = Body(...),
    project_service: ProjectService = Depends(get_project_service),
) -> dict:
    """
    Analyse a user prompt and return a transparent execution plan.

    The response includes everything needed for the AI Interpretation Panel:
    - confidence_scores per extracted item
    - execution_plan (ordered steps)
    - quality score with strengths and suggestions
    - ambiguities detected
    - credential_status (complete / partial / missing)
    - scope_summary (included / excluded modules and pages)
    - estimated stats (modules, pages, scenarios, runtime)
    - reasoning_steps for client-side live-reasoning animation
    - parsed_intent to forward verbatim to POST /runs on approval
    """
    from app.services.prompt_analyzer import get_prompt_analyzer

    raw_prompt: str = body.get("user_prompt") or body.get("test_instructions") or ""
    try:
        selected_model = resolve_model(((body.get("ai") or {}) if isinstance(body.get("ai"), dict) else {}).get("model") or body.get("model"))
    except UnsupportedModelError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    project_name = ""
    project_id_str = body.get("project_id")
    if project_id_str:
        try:
            from uuid import UUID as _UUID
            project = await project_service.get_project(_UUID(project_id_str))
            project_name = project.name or ""
            # Fall back to project default prompt when none provided
            if not raw_prompt and getattr(project, "default_prompt_text", None):
                raw_prompt = project.default_prompt_text or ""
        except Exception:
            pass

    if not raw_prompt.strip():
        return {
            "analysis_id": None,
            "raw_prompt": "",
            "interpretation": {},
            "confidence_scores": [],
            "execution_plan": [],
            "quality": {"score": 0, "strengths": [], "suggestions": ["Enter a prompt to analyse."]},
            "ambiguities": [],
            "credential_status": {"username_detected": False, "password_detected": False,
                                   "login_url_detected": False, "is_complete": False, "warnings": []},
            "scope_summary": {"included_modules": [], "excluded_modules": [],
                               "included_pages": [], "excluded_pages": []},
            "estimated": {"modules_estimate": 0, "pages_range": "unknown", "scenarios_range": "unknown",
                          "framework": "Playwright", "requires_auth": False, "estimated_runtime_minutes": 3},
            "reasoning_steps": [],
            "parsed_intent": {},
            "ai_model": selected_model,
        }

    analyzer = get_prompt_analyzer()
    result = analyzer.analyze(raw_prompt, project_name=project_name)
    response = result.to_dict()
    response["ai_model"] = selected_model
    return response


@router.post(
    "/{run_id}/cancel",
    status_code=status.HTTP_200_OK,
    summary="Cancel a run",
    description="Cancel a running or pending run.",
)
async def cancel_run(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> dict:
    from app.constants import RunStatus
    try:
        entity = await service.get_run(run_id)
        if entity.status not in (RunStatus.PENDING, RunStatus.RUNNING):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Run is not in a cancellable state")
        await service.update_status(run_id, RunStatus.CANCELLED, stage=entity.current_stage, message="Run cancelled by user")
        return {"status": "cancelled", "run_id": str(run_id)}
    except NotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Run not found: {run_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error("cancel_run_failed", run_id=str(run_id), error=str(e))
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to cancel run")

"""
Server-Sent Events (SSE) endpoint for live workflow monitoring.

GET /api/v1/runs/{run_id}/events
    Opens an SSE stream for the given run.  The frontend connects once
    and receives every workflow event in real time without polling.

GET /api/v1/runs/{run_id}/screenshots/{filename}
    Serves a screenshot file from the run's workspace.

The frontend builds its *entire* run-detail UI state from these events.
REST endpoints are used only for initial page-load metadata and artifact
downloads (JSON, Markdown, generated files).
"""

from __future__ import annotations

import asyncio
import mimetypes
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import FileResponse, StreamingResponse

from app.core.event_bus import EventType, WorkflowEvent, get_event_bus, emit
from app.dependencies import get_trigger_service
from app.exceptions import NotFoundError
from app.logging import get_logger
from app.services import TriggerService

logger = get_logger("api.events")

router = APIRouter(prefix="/runs", tags=["Live Events"])


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------

@router.get(
    "/{run_id}/events",
    summary="Live workflow event stream (SSE)",
    description=(
        "Opens a Server-Sent Events stream for the given run. "
        "Replays historical events on connect, then streams live events. "
        "Keep-alive pings are sent every 15 s to prevent proxy timeouts."
    ),
    response_class=StreamingResponse,
)
async def run_event_stream(
    run_id: UUID,
    service: TriggerService = Depends(get_trigger_service),
) -> StreamingResponse:
    """SSE stream — yields one event per SSE message, forever."""

    # Validate run exists
    try:
        await service.get_run(run_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    run_id_str = str(run_id)
    bus = get_event_bus()

    async def event_generator():
        """
        Async generator that yields SSE-formatted events.
        
        Exits when:
        - Receives None sentinel from drain() (workflow completed)
        - Client disconnects (asyncio.CancelledError)
        
        IMPORTANT: Do NOT return early on WORKFLOW_COMPLETED/FAILED events.
        Let the subscribe() method handle stream completion via the None sentinel.
        Otherwise, replaying historical completion events will close the stream immediately.
        """
        try:
            async for event in bus.subscribe(run_id_str, replay=True):
                yield event.to_sse()
        except asyncio.CancelledError:
            logger.info("sse_stream_cancelled", run_id=run_id_str)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Screenshot serving
# ---------------------------------------------------------------------------

@router.get(
    "/{run_id}/screenshots/{filename:path}",
    summary="Serve a screenshot captured during crawling",
    description=(
        "Returns the screenshot image file from the run workspace. "
        "The frontend loads these on demand after receiving "
        "screenshot_captured events."
    ),
)
async def get_screenshot(
    run_id: UUID,
    filename: str,
    service: TriggerService = Depends(get_trigger_service),
) -> FileResponse:
    """Serve screenshot PNG/JPEG from the run workspace."""
    try:
        entity = await service.get_run(run_id)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run not found: {run_id}",
        )

    workspace = Path(entity.workspace_path)
    screenshot_path = workspace / "screenshots" / filename

    if not screenshot_path.exists() or not screenshot_path.is_file():
        # Also try artifacts/screenshots/
        screenshot_path = workspace / "artifacts" / "screenshots" / filename

    if not screenshot_path.exists() or not screenshot_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Screenshot not found: {filename}",
        )

    # Security: ensure the path stays inside the workspace
    try:
        screenshot_path.resolve().relative_to(workspace.resolve())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Path traversal not allowed",
        )

    media_type = mimetypes.guess_type(str(screenshot_path))[0] or "image/png"
    return FileResponse(str(screenshot_path), media_type=media_type)

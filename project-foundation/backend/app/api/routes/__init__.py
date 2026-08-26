"""API route modules."""

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.events import router as events_router
from app.api.routes.models import router as models_router
from app.api.routes.projects import router as projects_router
from app.api.routes.prompts import router as prompts_router
from app.api.routes.trigger import router as trigger_router
from app.api.routes.workflow import router as workflow_router

__all__ = [
    "dashboard_router",
    "events_router",
    "models_router",
    "projects_router",
    "prompts_router",
    "trigger_router",
    "workflow_router",
]

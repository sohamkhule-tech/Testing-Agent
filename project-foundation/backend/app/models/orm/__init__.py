"""
SQLAlchemy ORM models — one module per domain.

Import order ensures FK target models are registered with metadata
before referencing models.
"""

# core — no cross-domain FK dependencies (User, Project, Run)
from app.models.orm.core import Project, Run, User

# discovery — FK to runs.run_id
from app.models.orm.discovery import CrawlPackage, Inventory

# design — FK to runs.run_id, users.id, test_plans.id
from app.models.orm.design import HumanReview, TestPlan, TestScenario

# generation — FK to runs.run_id, test_plans.id, ir_documents.id
from app.models.orm.generation import GeneratedProject, IRDocument

# execution — FK to runs.run_id, generated_projects.id, users.id, executions.id
from app.models.orm.execution import Execution, TestResult

# system — FK to runs.run_id, executions.id, test_results.id, users.id
from app.models.orm.system import Artifact, AuditLog

__all__ = [
    # core
    "User",
    "Project",
    "Run",
    # discovery
    "CrawlPackage",
    "Inventory",
    # design
    "TestPlan",
    "TestScenario",
    "HumanReview",
    # generation
    "IRDocument",
    "GeneratedProject",
    # execution
    "Execution",
    "TestResult",
    # system
    "Artifact",
    "AuditLog",
]

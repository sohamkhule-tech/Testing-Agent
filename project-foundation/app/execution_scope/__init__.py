"""
Execution Scope Enforcement.

Makes ExecutionPlan the single source of truth for execution scope across
crawler → inventory → test design → code generation → execution.
"""

from app.execution_scope.filtering import (
    apply_execution_scope,
    filter_approved_plan_by_scope,
    filter_scenarios_by_scope,
)
from app.execution_scope.resolver import (
    ExecutionScopeResolver,
    ScopeDecision,
    build_scope_grep,
    coerce_resolver,
    derive_url_patterns,
)

__all__ = [
    "ExecutionScopeResolver",
    "ScopeDecision",
    "build_scope_grep",
    "coerce_resolver",
    "derive_url_patterns",
    "apply_execution_scope",
    "filter_scenarios_by_scope",
    "filter_approved_plan_by_scope",
]

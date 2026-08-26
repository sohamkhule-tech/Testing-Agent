"""
Context Package — AgentState, Execution Planner, Hybrid Intent Parser, ContextManager

Phase 1 building blocks that preserve user intent end-to-end:

- ``AgentState``: canonical typed state carrying the original prompt, parsed
  intent, execution plan, and every stage's output.
- ``ExecutionPlanner`` / ``ExecutionPlan``: user prompt → goal, tasks, order,
  scope, constraints, success criteria.
- ``HybridIntentParser``: regex (URL/credentials/browser/environment) + LLM
  (goal/modules/priorities/strategy/objective/criteria) intent extraction.
- ``ContextManager``: creates, propagates, and captures AgentState between
  workflow stages.
"""

from app.context.agent_state import AGENT_STATE_FIELDS, AgentState
from app.context.context_manager import ContextManager, get_context_manager
from app.context.execution_planner import (
    STAGE_ORDER,
    ClarificationNeeded,
    ExecutionPlan,
    ExecutionPlanner,
    ExecutionTask,
    SubTask,
    get_execution_planner,
)
from app.context.intent_parser import (
    HybridIntentParser,
    LLMIntentSchema,
    ParsedIntent,
    get_hybrid_intent_parser,
)

__all__ = [
    "AGENT_STATE_FIELDS",
    "AgentState",
    "ClarificationNeeded",
    "ContextManager",
    "ExecutionPlan",
    "ExecutionPlanner",
    "ExecutionTask",
    "HybridIntentParser",
    "LLMIntentSchema",
    "ParsedIntent",
    "STAGE_ORDER",
    "SubTask",
    "get_context_manager",
    "get_execution_planner",
    "get_hybrid_intent_parser",
]

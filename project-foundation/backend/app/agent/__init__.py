"""
AI Testing Agent Package

Provides agentic capabilities layered over the existing pipeline:
- Centralized AgentState
- Feature-flagged execution
- Artifact Registry
- Intent Understanding (Phase 1)
- Execution Planner (Phase 1)
- Context Manager (Phase 1)
- Confidence Gates (Phase 1)
- Goal Satisfaction (Phase 1)
"""

from app.agent.config import get_agent_config
from app.agent.state import AgentState

__all__ = ["AgentState", "get_agent_config"]

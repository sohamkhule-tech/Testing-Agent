"""
Centralized AgentState (re-export)

The canonical AgentState lives in ``app.context.agent_state``. This module is
the ``app.agent`` package's public alias for it, satisfying the Phase 1
scaffolding (``app.agent.__init__`` imports ``AgentState`` from here) without
duplicating the model.
"""

from app.context.agent_state import AgentState

__all__ = ["AgentState"]

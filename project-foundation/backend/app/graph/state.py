"""
LangGraph State Models

Foundation state models for LangGraph workflow orchestration.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.constants import NodeStatus, RunStatus


class NodeContext(BaseModel):
    """
    Context passed to graph nodes.

    Contains execution metadata and utilities.
    """

    node_name: str = Field(..., description="Name of the current node")
    run_id: str = Field(..., description="Unique run identifier")
    correlation_id: str = Field(..., description="Request correlation ID")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )

    model_config = {"frozen": False}


class NodeResult(BaseModel):
    """
    Result from node execution.

    Standardizes node outputs.
    """

    node_name: str = Field(..., description="Name of the node")
    status: NodeStatus = Field(..., description="Execution status")
    data: dict[str, Any] = Field(
        default_factory=dict, description="Result data"
    )
    error: str | None = Field(None, description="Error message if failed")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata"
    )


class GraphState(BaseModel):
    """
    Base state model for LangGraph workflows.

    All workflow states should inherit from this.
    """

    run_id: str = Field(..., description="Unique run identifier")
    status: RunStatus = Field(default=RunStatus.PENDING, description="Overall run status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Execution tracking
    current_node: str | None = Field(None, description="Current executing node")
    completed_nodes: list[str] = Field(
        default_factory=list, description="List of completed nodes"
    )
    node_results: dict[str, NodeResult] = Field(
        default_factory=dict, description="Results from each node"
    )

    # Error handling
    errors: list[str] = Field(default_factory=list, description="Accumulated errors")

    # Metadata
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Workflow metadata"
    )

    model_config = {"frozen": False, "validate_assignment": True}

    def mark_node_started(self, node_name: str) -> None:
        """Mark a node as started."""
        self.current_node = node_name
        self.updated_at = datetime.utcnow()

    def mark_node_completed(
        self, node_name: str, result: NodeResult
    ) -> None:
        """Mark a node as completed."""
        self.completed_nodes.append(node_name)
        self.node_results[node_name] = result
        self.updated_at = datetime.utcnow()

        if result.error:
            self.errors.append(f"{node_name}: {result.error}")

    def mark_failed(self, error: str) -> None:
        """Mark the run as failed."""
        self.status = RunStatus.FAILED
        self.errors.append(error)
        self.updated_at = datetime.utcnow()

    def mark_completed(self) -> None:
        """Mark the run as completed."""
        self.status = RunStatus.COMPLETED
        self.updated_at = datetime.utcnow()


class WorkflowConfig(BaseModel):
    """
    Configuration for workflow execution.

    Provides runtime parameters for workflows.
    """

    max_retries: int = Field(default=3, description="Maximum retry attempts")
    timeout_seconds: int = Field(default=300, description="Workflow timeout")
    parallel_execution: bool = Field(
        default=False, description="Enable parallel node execution"
    )
    checkpoint_enabled: bool = Field(
        default=True, description="Enable state checkpointing"
    )
    custom_config: dict[str, Any] = Field(
        default_factory=dict, description="Custom configuration"
    )

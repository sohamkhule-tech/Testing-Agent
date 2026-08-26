"""
Dependency Graph Schemas

Represents relationships and dependencies between test components.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class NodeType(str, Enum):
    """Node types in dependency graph."""
    PAGE = "page"
    MODULE = "module"
    FLOW = "flow"
    ELEMENT = "element"
    COMPONENT = "component"


class EdgeType(str, Enum):
    """Edge types in dependency graph."""
    DEPENDS_ON = "depends_on"
    NAVIGATES_TO = "navigates_to"
    USES = "uses"
    CONTAINS = "contains"
    REQUIRES = "requires"
    PRECEDES = "precedes"


class GraphNode(BaseModel):
    """Node in dependency graph."""
    node_id: str = Field(..., description="Unique node identifier")
    node_type: NodeType = Field(..., description="Type of node")
    name: str = Field(..., description="Node name")
    description: str | None = Field(None, description="Node description")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    tags: list[str] = Field(default_factory=list, description="Node tags")


class GraphEdge(BaseModel):
    """Edge in dependency graph."""
    from_node: str = Field(..., description="Source node ID")
    to_node: str = Field(..., description="Target node ID")
    edge_type: EdgeType = Field(..., description="Type of relationship")
    weight: float = Field(1.0, description="Edge weight")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")


class DependencyPath(BaseModel):
    """Path through dependency graph."""
    nodes: list[str] = Field(..., description="Node IDs in path")
    length: int = Field(..., description="Path length")
    total_weight: float = Field(0.0, description="Total path weight")


class DependencyAnalysis(BaseModel):
    """Analysis results for dependencies."""
    circular_dependencies: list[list[str]] = Field(
        default_factory=list,
        description="Circular dependency chains"
    )
    orphaned_nodes: list[str] = Field(
        default_factory=list,
        description="Nodes with no connections"
    )
    critical_paths: list[DependencyPath] = Field(
        default_factory=list,
        description="Critical dependency paths"
    )
    bottlenecks: list[str] = Field(
        default_factory=list,
        description="Nodes that are heavily depended upon"
    )
    isolated_components: list[list[str]] = Field(
        default_factory=list,
        description="Groups of isolated components"
    )


class DependencyGraph(BaseModel):
    """Complete dependency graph."""
    nodes: list[GraphNode] = Field(..., description="All nodes in graph")
    edges: list[GraphEdge] = Field(..., description="All edges in graph")
    analysis: DependencyAnalysis | None = Field(None, description="Dependency analysis")
    
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Graph metadata"
    )
    
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Generation timestamp"
    )
    
    version: str = Field(default="1.0.0", description="Graph version")


class ImpactAnalysis(BaseModel):
    """Impact analysis for a change."""
    changed_nodes: list[str] = Field(..., description="Nodes that changed")
    directly_affected_nodes: list[str] = Field(default_factory=list, description="Directly affected nodes")
    indirectly_affected_nodes: list[str] = Field(default_factory=list, description="Transitively affected nodes")
    affected_test_count: int = Field(0, description="Number of test flows affected")
    upstream_dependencies: list[str] = Field(default_factory=list, description="Upstream dependencies")


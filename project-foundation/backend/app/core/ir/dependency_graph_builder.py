"""
Dependency Graph Builder

Builds dependency graph from IR for impact analysis and visualization.
"""

from collections import defaultdict, deque
from typing import Any

from app.logging import LoggerMixin
from app.schemas.dependency_graph import (
    DependencyAnalysis,
    DependencyGraph,
    DependencyPath,
    EdgeType,
    GraphEdge,
    GraphNode,
    ImpactAnalysis,
    NodeType,
)
from app.schemas.ir import CodeGenerationIR


class DependencyGraphBuilder(LoggerMixin):
    """
    Builds dependency graph from IR.
    
    Creates nodes for:
    - Pages
    - Modules
    - Flows
    - Elements
    
    Creates edges for:
    - Dependencies
    - Navigation
    - Usage
    - Containment
    """

    def __init__(self) -> None:
        """Initialize graph builder."""
        super().__init__()
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []

    def build_graph(self, ir: CodeGenerationIR) -> DependencyGraph:
        """
        Build complete dependency graph from IR.

        Args:
            ir: The IR to build graph from

        Returns:
            Complete dependency graph
        """
        self.logger.info("building_dependency_graph")
        self.nodes = {}
        self.edges = []

        # Build nodes
        self._build_page_nodes(ir)
        self._build_module_nodes(ir)
        self._build_flow_nodes(ir)
        self._build_element_nodes(ir)

        # Build edges
        self._build_containment_edges(ir)
        self._build_dependency_edges(ir)
        self._build_navigation_edges(ir)
        self._build_usage_edges(ir)

        # Analyze graph
        analysis = self._analyze_graph()

        graph = DependencyGraph(
            nodes=list(self.nodes.values()),
            edges=self.edges,
            analysis=analysis,
        )

        self.logger.info(
            "dependency_graph_built",
            node_count=len(self.nodes),
            edge_count=len(self.edges)
        )

        return graph

    def _build_page_nodes(self, ir: CodeGenerationIR) -> None:
        """Build nodes for pages."""
        for page in ir.pages:
            node = GraphNode(
                node_id=page.page_id,
                node_type=NodeType.PAGE,
                name=page.name,
                metadata={
                    "url_pattern": page.url_pattern,
                    "element_count": len(page.elements),
                },
            )
            self.nodes[page.page_id] = node

    def _build_module_nodes(self, ir: CodeGenerationIR) -> None:
        """Build nodes for modules."""
        for module in ir.modules:
            node = GraphNode(
                node_id=module.module_id,
                node_type=NodeType.MODULE,
                name=module.name,
                metadata={
                    "description": module.description,
                    "flow_count": len(module.flows),
                },
            )
            self.nodes[module.module_id] = node

    def _build_flow_nodes(self, ir: CodeGenerationIR) -> None:
        """Build nodes for flows."""
        for module in ir.modules:
            for flow in module.flows:
                node = GraphNode(
                    node_id=flow.flow_id,
                    node_type=NodeType.FLOW,
                    name=flow.name,
                    metadata={
                        "description": flow.description,
                        "module": module.module_id,
                        "step_count": len(flow.steps),
                        "priority": flow.priority,
                    },
                )
                self.nodes[flow.flow_id] = node

    def _build_element_nodes(self, ir: CodeGenerationIR) -> None:
        """Build nodes for elements."""
        for page in ir.pages:
            for element in page.elements:
                node = GraphNode(
                    node_id=element.id,
                    node_type=NodeType.ELEMENT,
                    name=element.name,
                    metadata={
                        "page": page.page_id,
                        "locator_strategy": element.locator_strategy.value,
                        "locator_value": element.locator_value,
                    },
                )
                self.nodes[element.id] = node

    def _build_containment_edges(self, ir: CodeGenerationIR) -> None:
        """Build containment edges (module contains flows, page contains elements)."""
        # Module contains flows
        for module in ir.modules:
            for flow in module.flows:
                edge = GraphEdge(
                    from_node=module.module_id,
                    to_node=flow.flow_id,
                    edge_type=EdgeType.CONTAINS,
                    weight=1.0,
                    metadata={"container": "module"},
                )
                self.edges.append(edge)

        # Page contains elements
        for page in ir.pages:
            for element in page.elements:
                edge = GraphEdge(
                    from_node=page.page_id,
                    to_node=element.id,
                    edge_type=EdgeType.CONTAINS,
                    weight=1.0,
                    metadata={"container": "page"},
                )
                self.edges.append(edge)

    def _build_dependency_edges(self, ir: CodeGenerationIR) -> None:
        """Build dependency edges from IR dependencies."""
        for dep in ir.dependencies:
            edge = GraphEdge(
                from_node=dep.source_id,
                to_node=dep.target_id,
                edge_type=EdgeType.DEPENDS_ON,
                weight=1.0,
                metadata={
                    "dependency_type": dep.dependency_type,
                    "description": dep.description,
                },
            )
            self.edges.append(edge)

        # Build dependency edges from flow dependencies
        for module in ir.modules:
            for flow in module.flows:
                for dep_flow_id in (flow.depends_on or []):
                    if dep_flow_id in self.nodes:
                        edge = GraphEdge(
                            from_node=flow.flow_id,
                            to_node=dep_flow_id,
                            edge_type=EdgeType.DEPENDS_ON,
                            weight=1.0,
                            metadata={"dependency_type": "flow_dependency"},
                        )
                        self.edges.append(edge)

    def _build_navigation_edges(self, ir: CodeGenerationIR) -> None:
        """Build navigation edges from flow navigation steps."""
        for module in ir.modules:
            for flow in module.flows:
                for step in flow.steps:
                    if step.navigation:
                        # Find target page by URL pattern
                        target_page = None
                        for page in ir.pages:
                            if (
                                page.url_pattern
                                and step.navigation.target
                                and page.url_pattern in step.navigation.target
                            ):
                                target_page = page.page_id
                                break

                        if target_page:
                            edge = GraphEdge(
                                from_node=flow.flow_id,
                                to_node=target_page,
                                edge_type=EdgeType.NAVIGATES_TO,
                                weight=1.0,
                                metadata={
                                    "step": step.step_order,
                                    "wait_for_load": step.navigation.wait_for_load,
                                },
                            )
                            self.edges.append(edge)

    def _build_usage_edges(self, ir: CodeGenerationIR) -> None:
        """Build usage edges (flow uses element)."""
        for module in ir.modules:
            for flow in module.flows:
                for step in flow.steps:
                    # Track used elements
                    used_elements = set()

                    # From actions
                    for action in step.actions:
                        if action.element_id and action.element_id in self.nodes:
                            used_elements.add(action.element_id)

                    # From assertions
                    for assertion in step.assertions:
                        if assertion.element_id and assertion.element_id in self.nodes:
                            used_elements.add(assertion.element_id)

                    # Create edges
                    for element_id in used_elements:
                        edge = GraphEdge(
                            from_node=flow.flow_id,
                            to_node=element_id,
                            edge_type=EdgeType.USES,
                            weight=1.0,
                            metadata={"step": step.step_order},
                        )
                        self.edges.append(edge)

    def _analyze_graph(self) -> DependencyAnalysis:
        """
        Analyze the graph for issues and patterns.

        Returns:
            Dependency analysis
        """
        # Find circular dependencies
        circular_deps = self._find_circular_dependencies()

        # Find orphaned nodes
        orphaned = self._find_orphaned_nodes()

        # Find critical paths
        critical_paths = self._find_critical_paths()

        # Find bottlenecks
        bottlenecks = self._find_bottlenecks()

        return DependencyAnalysis(
            circular_dependencies=circular_deps,
            orphaned_nodes=orphaned,
            critical_paths=critical_paths,
            bottlenecks=bottlenecks,
        )

    def _find_circular_dependencies(self) -> list[list[str]]:
        """Find circular dependency chains."""
        # Build adjacency list for DEPENDS_ON edges
        graph: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.edge_type == EdgeType.DEPENDS_ON:
                graph[edge.from_node].append(edge.to_node)

        cycles = []
        visited = set()
        path = []

        def dfs(node: str) -> None:
            """DFS to find cycles."""
            if node in path:
                # Found a cycle
                cycle_start = path.index(node)
                cycles.append(path[cycle_start:] + [node])
                return

            if node in visited:
                return

            visited.add(node)
            path.append(node)

            for neighbor in graph.get(node, []):
                dfs(neighbor)

            path.pop()

        for node_id in self.nodes:
            if node_id not in visited:
                dfs(node_id)

        return cycles

    def _find_orphaned_nodes(self) -> list[str]:
        """Find nodes with no incoming or outgoing edges."""
        connected = set()
        for edge in self.edges:
            connected.add(edge.from_node)
            connected.add(edge.to_node)

        orphaned = [
            node_id
            for node_id in self.nodes
            if node_id not in connected
        ]
        return orphaned

    def _find_critical_paths(self) -> list[DependencyPath]:
        """Find longest dependency paths (critical paths)."""
        # Build adjacency list
        graph: dict[str, list[str]] = defaultdict(list)
        for edge in self.edges:
            if edge.edge_type == EdgeType.DEPENDS_ON:
                graph[edge.from_node].append(edge.to_node)

        # Find longest paths using DFS
        longest_paths: list[DependencyPath] = []

        def dfs_path(node: str, path: list[str], visited: set[str]) -> None:
            """DFS to find longest paths."""
            if node in visited:
                return

            visited.add(node)
            path.append(node)

            neighbors = graph.get(node, [])
            if not neighbors:
                # Leaf node - record path
                if len(path) > 2:  # Only record non-trivial paths
                    longest_paths.append(
                        DependencyPath(
                            nodes=path.copy(),
                            length=len(path),
                        )
                    )
            else:
                for neighbor in neighbors:
                    dfs_path(neighbor, path, visited.copy())

            path.pop()

        for node_id in self.nodes:
            dfs_path(node_id, [], set())

        # Sort by length and return top 10
        longest_paths.sort(key=lambda p: p.length, reverse=True)
        return longest_paths[:10]

    def _find_bottlenecks(self) -> list[str]:
        """Find nodes with highest in-degree (bottlenecks)."""
        in_degree: dict[str, int] = defaultdict(int)

        for edge in self.edges:
            in_degree[edge.to_node] += 1

        # Sort by in-degree
        sorted_nodes = sorted(
            in_degree.items(),
            key=lambda x: x[1],
            reverse=True
        )

        # Return top 10 bottlenecks
        return [node_id for node_id, _ in sorted_nodes[:10]]

    def analyze_impact(
        self,
        changed_node_ids: list[str]
    ) -> ImpactAnalysis:
        """
        Analyze impact of changes to specific nodes.

        Args:
            changed_node_ids: IDs of changed nodes

        Returns:
            Impact analysis
        """
        # Build adjacency list (both directions)
        forward_graph: dict[str, list[str]] = defaultdict(list)
        backward_graph: dict[str, list[str]] = defaultdict(list)

        for edge in self.edges:
            forward_graph[edge.from_node].append(edge.to_node)
            backward_graph[edge.to_node].append(edge.from_node)

        # Find directly affected nodes (downstream dependencies)
        directly_affected = set()
        for node_id in changed_node_ids:
            directly_affected.update(forward_graph.get(node_id, []))

        # Find indirectly affected nodes (transitive closure)
        indirectly_affected = set()
        queue = deque(directly_affected)
        visited = set(directly_affected)

        while queue:
            node = queue.popleft()
            for neighbor in forward_graph.get(node, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    indirectly_affected.add(neighbor)
                    queue.append(neighbor)

        # Find upstream dependencies
        upstream = set()
        for node_id in changed_node_ids:
            queue = deque([node_id])
            node_visited = {node_id}

            while queue:
                node = queue.popleft()
                for neighbor in backward_graph.get(node, []):
                    if neighbor not in node_visited:
                        node_visited.add(neighbor)
                        upstream.add(neighbor)
                        queue.append(neighbor)

        # Find affected tests (flows)
        affected_flows = [
            node_id
            for node_id in visited
            if self.nodes.get(node_id, GraphNode(node_id="", node_type=NodeType.FLOW, name="")).node_type == NodeType.FLOW
        ]

        return ImpactAnalysis(
            changed_nodes=changed_node_ids,
            directly_affected_nodes=list(directly_affected),
            indirectly_affected_nodes=list(indirectly_affected),
            affected_test_count=len(affected_flows),
            upstream_dependencies=list(upstream),
        )

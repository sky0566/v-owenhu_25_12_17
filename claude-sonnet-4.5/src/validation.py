"""
Input validation for routing requests.
Ensures data integrity and catches errors early.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass, field
from graph import Graph


@dataclass
class ValidationError:
    """Represents a validation error."""
    field: str
    message: str
    code: str


@dataclass
class ValidationResult:
    """Result of validation checks."""
    is_valid: bool
    errors: List[ValidationError] = field(default_factory=list)
    
    def add_error(self, field: str, message: str, code: str = "VALIDATION_ERROR") -> None:
        """Add a validation error."""
        self.is_valid = False
        self.errors.append(ValidationError(field, message, code))


class GraphValidator:
    """Validates graph and routing requests."""
    
    def __init__(self, max_nodes: int = 10000, max_edges: int = 100000):
        self.max_nodes = max_nodes
        self.max_edges = max_edges
    
    def validate_graph(self, graph: Graph) -> ValidationResult:
        """
        Validate graph structure and properties.
        Returns ValidationResult with any errors found.
        """
        result = ValidationResult(is_valid=True)
        metadata = graph.get_metadata()
        
        # Check size limits
        if metadata.node_count > self.max_nodes:
            result.add_error(
                "graph",
                f"Graph has {metadata.node_count} nodes, exceeds limit of {self.max_nodes}",
                "GRAPH_TOO_LARGE"
            )
        
        if metadata.edge_count > self.max_edges:
            result.add_error(
                "graph",
                f"Graph has {metadata.edge_count} edges, exceeds limit of {self.max_edges}",
                "GRAPH_TOO_LARGE"
            )
        
        # Check for empty graph
        if metadata.node_count == 0:
            result.add_error(
                "graph",
                "Graph has no nodes",
                "EMPTY_GRAPH"
            )
        
        # Check for negative cycle (this is fatal)
        if metadata.has_negative_cycle:
            result.add_error(
                "graph",
                "Graph contains negative weight cycle; shortest path is undefined",
                "NEGATIVE_CYCLE"
            )
        
        return result
    
    def validate_route_request(
        self,
        graph: Graph,
        start: str,
        goal: str
    ) -> ValidationResult:
        """
        Validate a route request.
        Checks node existence and graph validity.
        """
        result = ValidationResult(is_valid=True)
        
        # First validate the graph itself
        graph_validation = self.validate_graph(graph)
        if not graph_validation.is_valid:
            result.is_valid = False
            result.errors.extend(graph_validation.errors)
            return result
        
        # Check node existence
        if not graph.has_node(start):
            result.add_error(
                "start",
                f"Start node '{start}' not found in graph",
                "NODE_NOT_FOUND"
            )
        
        if not graph.has_node(goal):
            result.add_error(
                "goal",
                f"Goal node '{goal}' not found in graph",
                "NODE_NOT_FOUND"
            )
        
        # Check for self-loop (trivial case)
        if start == goal:
            # Not an error, just note it
            pass
        
        return result

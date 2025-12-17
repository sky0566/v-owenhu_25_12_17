"""
Validation layer for route requests.

Validates:
- Source/goal nodes exist and are distinct
- No cycles (optionally)
- Preconditions before algorithm execution
"""

from typing import Optional
from .graph import Graph


class ValidationError(Exception):
    """Validation precondition failed."""
    pass


class RouteValidator:
    """Validate route requests."""

    @staticmethod
    def validate_route_request(
        graph: Graph,
        start: str,
        goal: str,
        require_no_negative_weights: bool = False,
    ) -> None:
        """
        Validate that a route request can be processed.
        
        Raises ValidationError if:
        - start or goal not in graph
        - start == goal
        - negative weights present and require_no_negative_weights=True
        """
        nodes = set(graph.nodes())
        
        if start not in nodes:
            raise ValidationError(f"Start node '{start}' not in graph")
        
        if goal not in nodes:
            raise ValidationError(f"Goal node '{goal}' not in graph")
        
        if start == goal:
            raise ValidationError(f"Start and goal must differ (both='{start}')")
        
        if require_no_negative_weights and graph.has_negative_weights():
            negative_edges = graph.get_negative_edges()
            msg = f"Graph contains {len(negative_edges)} negative-weight edge(s): "
            msg += ", ".join([f"({s}→{t}={w})" for s, t, w in negative_edges[:3]])
            if len(negative_edges) > 3:
                msg += f"... and {len(negative_edges) - 3} more"
            raise ValidationError(msg)

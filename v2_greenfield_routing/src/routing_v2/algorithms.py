"""
Shortest-path algorithms.

Core improvements over legacy:
- Abstract interface for algorithm selection
- Bellman-Ford for negative-weight graphs
- Explicit precondition validation
- Comprehensive error messages with causal chains
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Tuple, Optional, Set
import heapq
from datetime import datetime

from .graph import Graph
from .validation import ValidationError


class RouteAlgorithm(ABC):
    """Base interface for shortest-path algorithms."""

    @abstractmethod
    def compute_shortest_path(
        self, graph: Graph, start: str, goal: str
    ) -> Tuple[List[str], float]:
        """
        Compute shortest path from start to goal.
        
        Returns: (path, total_cost)
        Raises: ValueError if no path exists, ValidationError if preconditions fail
        """
        pass

    @abstractmethod
    def supports_negative_weights(self) -> bool:
        """Whether algorithm handles negative-weight edges correctly."""
        pass

    @abstractmethod
    def algorithm_name(self) -> str:
        """Human-readable algorithm name."""
        pass


class DijkstraRouter(RouteAlgorithm):
    """
    Dijkstra's algorithm (requires non-negative weights).
    
    This is the reference implementation, corrected from the legacy buggy version:
    - Nodes marked as visited when POPPED (finalized), not on discovery
    - Explicit negative-weight rejection
    """

    def algorithm_name(self) -> str:
        return "Dijkstra"

    def supports_negative_weights(self) -> bool:
        return False

    def compute_shortest_path(
        self, graph: Graph, start: str, goal: str
    ) -> Tuple[List[str], float]:
        """Compute shortest path using corrected Dijkstra."""
        # Validate preconditions
        if graph.has_negative_weights():
            raise ValidationError(
                f"Dijkstra does not support negative-weight edges. "
                f"Graph has {len(graph.get_negative_edges())} negative edge(s). "
                f"Use Bellman-Ford instead."
            )

        dist: Dict[str, float] = {start: 0.0}
        prev: Dict[str, Optional[str]] = {start: None}
        heap: List[Tuple[float, str]] = [(0.0, start)]
        visited: Set[str] = set()

        while heap:
            cost, node = heapq.heappop(heap)

            # Skip stale entries
            if node in visited:
                continue

            # FIX: Mark visited when popped (finalized), not on discovery
            visited.add(node)

            if node == goal:
                return _reconstruct_path(prev, goal), cost

            # Skip if we found a cheaper path to this node already
            if cost > dist.get(node, float("inf")):
                continue

            for neighbor, weight in graph.neighbors(node).items():
                if neighbor in visited:
                    continue

                new_cost = cost + weight
                if new_cost < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_cost
                    prev[neighbor] = node
                    heapq.heappush(heap, (new_cost, neighbor))

        raise ValueError(f"No path from {start} to {goal}")


class BellmanFordRouter(RouteAlgorithm):
    """
    Bellman-Ford algorithm (handles negative weights, detects negative cycles).
    
    Complexity: O(V*E). Suitable for routing with:
    - Negative-weight edges (e.g., discounts, rebates)
    - Reliable negative-cycle detection
    """

    def algorithm_name(self) -> str:
        return "Bellman-Ford"

    def supports_negative_weights(self) -> bool:
        return True

    def compute_shortest_path(
        self, graph: Graph, start: str, goal: str
    ) -> Tuple[List[str], float]:
        """Compute shortest path using Bellman-Ford with negative-cycle detection."""
        nodes = list(graph.nodes())

        # Initialize distances
        dist: Dict[str, float] = {node: float("inf") for node in nodes}
        prev: Dict[str, Optional[str]] = {node: None for node in nodes}
        dist[start] = 0.0

        # Relax edges |V|-1 times
        for _ in range(len(nodes) - 1):
            for src in nodes:
                if dist[src] == float("inf"):
                    continue
                for dst, weight in graph.neighbors(src).items():
                    new_cost = dist[src] + weight
                    if new_cost < dist[dst]:
                        dist[dst] = new_cost
                        prev[dst] = src

        # Check for negative cycles reachable from start
        for src in nodes:
            if dist[src] == float("inf"):
                continue
            for dst, weight in graph.neighbors(src).items():
                if dist[src] + weight < dist[dst]:
                    raise ValueError(
                        f"Negative cycle detected: reachable from {start}. "
                        f"Edge {src}→{dst}={weight} would improve distance to {dst}."
                    )

        # Reconstruct path
        if dist[goal] == float("inf"):
            raise ValueError(f"No path from {start} to {goal}")

        return _reconstruct_path(prev, goal), dist[goal]


def _reconstruct_path(prev: Dict[str, Optional[str]], goal: str) -> List[str]:
    """Reconstruct path from predecessor map."""
    path: List[str] = []
    node = goal
    while node is not None:
        path.append(node)
        node = prev.get(node)
    return list(reversed(path))


class AutoSelectRouter(RouteAlgorithm):
    """
    Automatically select algorithm based on graph properties.
    
    - If no negative weights: use Dijkstra (faster O(E log V))
    - If negative weights: use Bellman-Ford (slower but correct)
    
    This is the recommended production router.
    """

    def __init__(self, prefer_dijkstra: bool = True):
        self.prefer_dijkstra = prefer_dijkstra
        self._dijkstra = DijkstraRouter()
        self._bellman_ford = BellmanFordRouter()

    def algorithm_name(self) -> str:
        return "AutoSelect"

    def supports_negative_weights(self) -> bool:
        return True

    def compute_shortest_path(
        self, graph: Graph, start: str, goal: str
    ) -> Tuple[List[str], float]:
        """Select and run appropriate algorithm."""
        if graph.has_negative_weights():
            return self._bellman_ford.compute_shortest_path(graph, start, goal)
        else:
            return self._dijkstra.compute_shortest_path(graph, start, goal)

"""
Routing algorithms: Dijkstra and Bellman-Ford.
Auto-selects appropriate algorithm based on graph properties.
"""

from __future__ import annotations
from typing import Dict, List, Tuple, Optional, Protocol
import heapq
import time

from graph import Graph


class TimeoutError(Exception):
    """Raised when computation exceeds timeout."""
    pass


class RoutingAlgorithm(Protocol):
    """Protocol for routing algorithms."""
    
    def compute(
        self,
        graph: Graph,
        start: str,
        goal: str,
        timeout: Optional[float] = None
    ) -> Tuple[List[str], float]:
        """Compute shortest path from start to goal."""
        ...


class DijkstraAlgorithm:
    """
    Dijkstra's shortest path algorithm.
    Optimal for graphs with non-negative weights.
    Time complexity: O(E log V) with binary heap.
    """
    
    def compute(
        self,
        graph: Graph,
        start: str,
        goal: str,
        timeout: Optional[float] = None
    ) -> Tuple[List[str], float]:
        """
        Compute shortest path using Dijkstra's algorithm.
        
        Args:
            graph: The graph to search
            start: Start node
            goal: Goal node
            timeout: Maximum execution time in seconds
            
        Returns:
            Tuple of (path, cost)
            
        Raises:
            TimeoutError: If computation exceeds timeout
            ValueError: If no path exists
        """
        start_time = time.time()
        
        # Initialize
        dist: Dict[str, float] = {start: 0.0}
        prev: Dict[str, Optional[str]] = {start: None}
        heap: List[Tuple[float, str]] = [(0.0, start)]
        visited: set[str] = set()  # Mark nodes when POPPED (finalized), not when discovered
        
        while heap:
            # Check timeout
            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Computation exceeded timeout of {timeout}s")
            
            cost, node = heapq.heappop(heap)
            
            # Skip if already processed
            if node in visited:
                continue
            
            # Mark as visited only when popped (finalized)
            visited.add(node)
            
            # Found goal
            if node == goal:
                return self._reconstruct_path(prev, goal), cost
            
            # Skip if stale entry
            if cost > dist.get(node, float("inf")):
                continue
            
            # Relax neighbors
            for neighbor, weight in graph.neighbors(node).items():
                new_cost = cost + weight
                
                # Update distance if better path found
                if new_cost < dist.get(neighbor, float("inf")):
                    dist[neighbor] = new_cost
                    prev[neighbor] = node
                    heapq.heappush(heap, (new_cost, neighbor))
        
        raise ValueError(f"No path found from {start} to {goal}")
    
    @staticmethod
    def _reconstruct_path(prev: Dict[str, Optional[str]], goal: str) -> List[str]:
        """Reconstruct path from predecessor map."""
        path: List[str] = []
        node = goal
        while node is not None:
            path.append(node)
            node = prev.get(node)
        return list(reversed(path))


class BellmanFordAlgorithm:
    """
    Bellman-Ford shortest path algorithm.
    Handles negative weights but not negative cycles.
    Time complexity: O(VE)
    """
    
    def compute(
        self,
        graph: Graph,
        start: str,
        goal: str,
        timeout: Optional[float] = None
    ) -> Tuple[List[str], float]:
        """
        Compute shortest path using Bellman-Ford algorithm.
        
        Args:
            graph: The graph to search
            start: Start node
            goal: Goal node
            timeout: Maximum execution time in seconds
            
        Returns:
            Tuple of (path, cost)
            
        Raises:
            TimeoutError: If computation exceeds timeout
            ValueError: If no path exists or negative cycle detected
        """
        start_time = time.time()
        
        # Initialize distances
        dist: Dict[str, float] = {node: float('inf') for node in graph.nodes()}
        dist[start] = 0.0
        prev: Dict[str, Optional[str]] = {node: None for node in graph.nodes()}
        
        # Relax edges V-1 times
        node_count = len(list(graph.nodes()))
        for iteration in range(node_count - 1):
            # Check timeout
            if timeout is not None and (time.time() - start_time) > timeout:
                raise TimeoutError(f"Computation exceeded timeout of {timeout}s")
            
            any_update = False
            for source, target, weight in graph.edges():
                if dist[source] != float('inf'):
                    new_cost = dist[source] + weight
                    if new_cost < dist[target]:
                        dist[target] = new_cost
                        prev[target] = source
                        any_update = True
            
            # Early termination if no updates
            if not any_update:
                break
        
        # Check for negative cycles
        for source, target, weight in graph.edges():
            if dist[source] != float('inf'):
                if dist[source] + weight < dist[target]:
                    raise ValueError("Graph contains negative cycle; shortest path undefined")
        
        # Check if goal is reachable
        if dist[goal] == float('inf'):
            raise ValueError(f"No path found from {start} to {goal}")
        
        return self._reconstruct_path(prev, goal), dist[goal]
    
    @staticmethod
    def _reconstruct_path(prev: Dict[str, Optional[str]], goal: str) -> List[str]:
        """Reconstruct path from predecessor map."""
        path: List[str] = []
        node = goal
        while node is not None:
            path.append(node)
            node = prev.get(node)
        return list(reversed(path))


class AlgorithmSelector:
    """Selects appropriate routing algorithm based on graph properties."""
    
    def __init__(self):
        self.dijkstra = DijkstraAlgorithm()
        self.bellman_ford = BellmanFordAlgorithm()
    
    def select_algorithm(self, graph: Graph) -> Tuple[RoutingAlgorithm, str]:
        """
        Select appropriate algorithm based on graph metadata.
        
        Returns:
            Tuple of (algorithm instance, algorithm name)
        """
        metadata = graph.get_metadata()
        
        if metadata.has_negative_weights:
            return self.bellman_ford, "bellman_ford"
        else:
            return self.dijkstra, "dijkstra"
    
    def compute_route(
        self,
        graph: Graph,
        start: str,
        goal: str,
        timeout: Optional[float] = None
    ) -> Tuple[List[str], float, str]:
        """
        Compute route with automatic algorithm selection.
        
        Returns:
            Tuple of (path, cost, algorithm_used)
        """
        algorithm, name = self.select_algorithm(graph)
        path, cost = algorithm.compute(graph, start, goal, timeout)
        return path, cost, name

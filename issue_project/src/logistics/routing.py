from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import heapq

from .graph import Graph


def dijkstra_shortest_path(graph: Graph, start: str, goal: str) -> Tuple[List[str], float]:
    """
    Compute shortest path from start to goal using Dijkstra's algorithm.

    This implementation validates that the graph contains no negative-weight
    edges and raises ValueError (message includes the word "negative") if any
    are found. It also marks nodes as finalized (visited) when they are popped
    from the heap (correct Dijkstra behavior) so that it produces correct
    results for non-negative-weight graphs.
    """
    # Validate: Dijkstra is not suitable for negative-weight edges
    for u in graph.nodes():
        for v, w in graph.neighbors(u).items():
            if w < 0:
                raise ValueError("Graph contains negative weight edges; Dijkstra cannot be used on graphs with negative edges")

    # Distances and predecessor tracking
    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, Optional[str]] = {start: None}

    # Min-heap items: (cost, node)
    heap: List[Tuple[float, str]] = [(0.0, start)]

    # Finalized nodes (marked when popped from heap)
    visited = set()

    while heap:
        cost, node = heapq.heappop(heap)

        # If already finalized (stale entry), skip
        if node in visited:
            continue

        visited.add(node)

        if node == goal:
            return _reconstruct_path(prev, goal), cost

        for neighbor, weight in graph.neighbors(node).items():
            new_cost = cost + weight
            if new_cost < dist.get(neighbor, float("inf")):
                dist[neighbor] = new_cost
                prev[neighbor] = node
                heapq.heappush(heap, (new_cost, neighbor))

    raise ValueError(f"No path found from {start} to {goal}")


def bellman_ford_shortest_path(graph: Graph, start: str, goal: str) -> Tuple[List[str], float]:
    """
    Compute shortest path using Bellman-Ford algorithm. Supports negative
    weights and detects negative-weight cycles reachable from the start node.
    """
    # Initialize distances
    dist: Dict[str, float] = {node: float("inf") for node in graph.nodes()}
    prev: Dict[str, Optional[str]] = {node: None for node in graph.nodes()}
    if start not in dist:
        raise ValueError(f"Start node {start} not in graph")
    dist[start] = 0.0

    nodes_list = list(graph.nodes())
    n = len(nodes_list)

    # Relax edges up to n-1 times
    for _ in range(n - 1):
        updated = False
        for u in nodes_list:
            if dist[u] == float("inf"):
                continue
            for v, w in graph.neighbors(u).items():
                if dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
                    prev[v] = u
                    updated = True
        if not updated:
            break

    # Check for negative-weight cycles
    for u in nodes_list:
        if dist[u] == float("inf"):
            continue
        for v, w in graph.neighbors(u).items():
            if dist[u] + w < dist[v]:
                raise ValueError("Graph contains a negative-weight cycle")

    if dist.get(goal, float("inf")) == float("inf"):
        raise ValueError(f"No path found from {start} to {goal}")

    return _reconstruct_path(prev, goal), dist[goal]


def _reconstruct_path(prev: Dict[str, Optional[str]], goal: str) -> List[str]:
    path: List[str] = []
    node = goal
    while node is not None:
        path.append(node)
        node = prev.get(node)
    return list(reversed(path))

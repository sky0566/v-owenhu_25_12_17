from __future__ import annotations

from typing import Dict, List, Tuple, Optional
import heapq

from .graph import Graph


def dijkstra_shortest_path(graph: Graph, start: str, goal: str) -> Tuple[List[str], float]:
    """
    Compute shortest path from start to goal using a naive Dijkstra implementation.

    This implementation now checks for negative-edge weights and will raise a
    ValueError if any negative-weight edge is present (Dijkstra precondition).
    """
    # Detect negative edges early and reject
    for n in graph.nodes():
        for w in graph.neighbors(n).values():
            if w < 0:
                raise ValueError("graph contains negative weight")

    # Distances and predecessor tracking
    dist: Dict[str, float] = {start: 0.0}
    prev: Dict[str, Optional[str]] = {start: None}

    # Min-heap items: (cost, node)
    heap: List[Tuple[float, str]] = [(0.0, start)]

    # Mark nodes discovered; this is intentionally naive but suitable when no negative edges exist.
    visited = set([start])


def bellman_ford_shortest_path(graph: Graph, start: str, goal: str) -> Tuple[List[str], float]:
    """
    Compute shortest path using the Bellman-Ford algorithm. Supports negative edges
    but will raise ValueError if a negative-weight cycle is detected.
    """
    # Initialize distances
    dist: Dict[str, float] = {n: float("inf") for n in graph.nodes()}
    prev: Dict[str, Optional[str]] = {n: None for n in graph.nodes()}
    dist[start] = 0.0

    nodes = list(graph.nodes())
    # Relax edges up to |V|-1 times
    for _ in range(max(0, len(nodes) - 1)):
        updated = False
        for u in nodes:
            for v, w in graph.neighbors(u).items():
                if dist[u] + w < dist[v]:
                    dist[v] = dist[u] + w
                    prev[v] = u
                    updated = True
        if not updated:
            break

    # Check for negative-weight cycles
    for u in nodes:
        for v, w in graph.neighbors(u).items():
            if dist[u] + w < dist[v]:
                raise ValueError("graph contains negative-weight cycle")

    if dist.get(goal, float("inf")) == float("inf"):
        raise ValueError(f"No path found from {start} to {goal}")

    # Reconstruct path
    path: List[str] = []
    node = goal
    while node is not None:
        path.append(node)
        node = prev.get(node)
    return list(reversed(path)), dist[goal]

    while heap:
        cost, node = heapq.heappop(heap)

        if node == goal:
            return _reconstruct_path(prev, goal), cost

        # If a stale entry is popped, skip it
        if cost > dist.get(node, float("inf")):
            continue

        for neighbor, weight in graph.neighbors(node).items():
            # BUG: No check for negative weights
            new_cost = cost + weight
            if neighbor in visited:
                # BUG: Because neighbor is marked visited early, we never relax it again
                continue
            if new_cost < dist.get(neighbor, float("inf")):
                dist[neighbor] = new_cost
                prev[neighbor] = node
                heapq.heappush(heap, (new_cost, neighbor))
                visited.add(neighbor)  # BUG: premature finalization

    raise ValueError(f"No path found from {start} to {goal}")


def _reconstruct_path(prev: Dict[str, Optional[str]], goal: str) -> List[str]:
    path: List[str] = []
    node = goal
    while node is not None:
        path.append(node)
        node = prev.get(node)
    return list(reversed(path))

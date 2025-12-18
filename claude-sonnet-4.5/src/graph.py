"""
Greenfield Routing System v2
Graph representation with enhanced validation and metadata tracking.
"""

from __future__ import annotations
from typing import Dict, Iterable, Tuple, List, Set
import json
from dataclasses import dataclass, field


@dataclass
class GraphMetadata:
    """Metadata about graph properties for algorithm selection."""
    node_count: int = 0
    edge_count: int = 0
    has_negative_weights: bool = False
    has_negative_cycle: bool = False
    min_weight: float = float('inf')
    max_weight: float = float('-inf')
    negative_edges: List[Tuple[str, str, float]] = field(default_factory=list)
    

class Graph:
    """Directed weighted graph with validation and metadata."""

    def __init__(self) -> None:
        self._adj: Dict[str, Dict[str, float]] = {}
        self._metadata: GraphMetadata = GraphMetadata()
        self._validated: bool = False

    def add_edge(self, source: str, target: str, weight: float) -> None:
        """Add an edge to the graph and update metadata."""
        if source not in self._adj:
            self._adj[source] = {}
        self._adj[source][target] = weight
        
        # Ensure target exists in adjacency map for node iteration
        if target not in self._adj:
            self._adj[target] = {}
        
        # Update metadata
        self._metadata.edge_count += 1
        self._metadata.min_weight = min(self._metadata.min_weight, weight)
        self._metadata.max_weight = max(self._metadata.max_weight, weight)
        
        if weight < 0:
            self._metadata.has_negative_weights = True
            self._metadata.negative_edges.append((source, target, weight))
        
        self._validated = False  # Invalidate validation when graph changes

    def neighbors(self, node: str) -> Dict[str, float]:
        """Get neighbors of a node with their edge weights."""
        return self._adj.get(node, {})

    def nodes(self) -> Iterable[str]:
        """Get all nodes in the graph."""
        return self._adj.keys()
    
    def edges(self) -> Iterable[Tuple[str, str, float]]:
        """Get all edges as (source, target, weight) tuples."""
        for source, targets in self._adj.items():
            for target, weight in targets.items():
                yield (source, target, weight)

    def has_node(self, node: str) -> bool:
        """Check if a node exists in the graph."""
        return node in self._adj
    
    def get_metadata(self) -> GraphMetadata:
        """Get graph metadata (validates if needed)."""
        if not self._validated:
            self._update_metadata()
        return self._metadata
    
    def _update_metadata(self) -> None:
        """Update metadata including node count and negative cycle detection."""
        self._metadata.node_count = len(self._adj)
        
        # Detect negative cycles using Bellman-Ford-like approach
        if self._metadata.has_negative_weights:
            self._metadata.has_negative_cycle = self._detect_negative_cycle()
        
        self._validated = True
    
    def _detect_negative_cycle(self) -> bool:
        """
        Detect negative cycles using Bellman-Ford algorithm.
        Returns True if a negative cycle exists.
        """
        if not self._adj:
            return False
        
        # Initialize distances
        dist: Dict[str, float] = {node: float('inf') for node in self.nodes()}
        
        # Pick arbitrary start node
        start = next(iter(self.nodes()))
        dist[start] = 0.0
        
        # Relax edges V-1 times
        node_count = len(self._adj)
        for _ in range(node_count - 1):
            for source, target, weight in self.edges():
                if dist[source] != float('inf'):
                    if dist[source] + weight < dist[target]:
                        dist[target] = dist[source] + weight
        
        # Check for negative cycle (additional relaxation possible)
        for source, target, weight in self.edges():
            if dist[source] != float('inf'):
                if dist[source] + weight < dist[target]:
                    return True  # Negative cycle detected
        
        return False

    @staticmethod
    def from_edge_list(edges: Iterable[Tuple[str, str, float]]) -> "Graph":
        """Create graph from list of (source, target, weight) tuples."""
        g = Graph()
        for src, dst, w in edges:
            g.add_edge(src, dst, w)
        return g

    @classmethod
    def from_json_file(cls, path: str) -> "Graph":
        """
        Load graph from JSON file with structure:
        {
          "edges": [
            {"source": "A", "target": "B", "weight": 5},
            ...
          ]
        }
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        edges: List[Tuple[str, str, float]] = [
            (e["source"], e["target"], e["weight"]) for e in data["edges"]
        ]
        return cls.from_edge_list(edges)
    
    @classmethod
    def from_dict(cls, data: dict) -> "Graph":
        """Create graph from dictionary (for testing)."""
        edges: List[Tuple[str, str, float]] = [
            (e["source"], e["target"], e["weight"]) for e in data["edges"]
        ]
        return cls.from_edge_list(edges)

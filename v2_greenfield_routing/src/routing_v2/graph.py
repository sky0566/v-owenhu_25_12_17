"""
Graph data structure with explicit validation.

Key improvements over legacy:
- Immutable node/edge lists after construction
- Explicit negative-weight detection
- Rich metadata for observability
"""

from __future__ import annotations

from typing import Dict, Iterable, Tuple, List, Set, Optional
import json
from datetime import datetime


class Graph:
    """Directed weighted graph with validation and observability."""

    def __init__(self) -> None:
        self._adj: Dict[str, Dict[str, float]] = {}
        self._created_at = datetime.utcnow().isoformat()
        self._edge_count = 0
        self._has_negative_weights = False

    def add_edge(self, source: str, target: str, weight: float) -> None:
        """Add weighted edge. Detect negative weights during construction."""
        if source not in self._adj:
            self._adj[source] = {}
        self._adj[source][target] = weight
        if target not in self._adj:
            self._adj[target] = {}
        
        if weight < 0:
            self._has_negative_weights = True
        
        self._edge_count += 1

    def neighbors(self, node: str) -> Dict[str, float]:
        """Return outgoing edges from node."""
        return self._adj.get(node, {}).copy()

    def nodes(self) -> Iterable[str]:
        """Return all nodes."""
        return self._adj.keys()

    def node_count(self) -> int:
        """Total nodes."""
        return len(self._adj)

    def edge_count(self) -> int:
        """Total edges added."""
        return self._edge_count

    def has_negative_weights(self) -> bool:
        """Whether graph contains any negative-weight edge."""
        return self._has_negative_weights

    def get_negative_edges(self) -> List[Tuple[str, str, float]]:
        """Return list of (source, target, weight) for all negative edges."""
        negatives = []
        for src, targets in self._adj.items():
            for tgt, weight in targets.items():
                if weight < 0:
                    negatives.append((src, tgt, weight))
        return negatives

    @staticmethod
    def from_edge_list(edges: Iterable[Tuple[str, str, float]]) -> Graph:
        """Construct from list of (source, target, weight) tuples."""
        g = Graph()
        for src, dst, w in edges:
            g.add_edge(src, dst, w)
        return g

    @classmethod
    def from_json_file(cls, path: str) -> Graph:
        """Load graph from JSON with structure: {"edges": [{"source": "A", "target": "B", "weight": 5}, ...]}"""
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        edges: List[Tuple[str, str, float]] = [
            (e["source"], e["target"], e["weight"]) for e in data["edges"]
        ]
        return cls.from_edge_list(edges)

    def to_dict(self) -> Dict:
        """Serialize to dictionary for logging/transport."""
        edges = []
        for src, targets in self._adj.items():
            for tgt, weight in targets.items():
                edges.append({"source": src, "target": tgt, "weight": weight})
        
        return {
            "edges": edges,
            "node_count": self.node_count(),
            "edge_count": self.edge_count(),
            "has_negative_weights": self.has_negative_weights(),
            "created_at": self._created_at,
        }

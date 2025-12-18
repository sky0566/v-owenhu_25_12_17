"""
Greenfield Routing System v2.0
A complete rewrite with validation, algorithm selection, and observability.
"""

from .graph import Graph, GraphMetadata
from .validation import GraphValidator, ValidationResult, ValidationError
from .routing import (
    DijkstraAlgorithm,
    BellmanFordAlgorithm,
    AlgorithmSelector,
    TimeoutError
)
from .service import (
    RoutingService,
    RouteRequest,
    RouteResponse,
    RouteStatus
)
from .logging_utils import StructuredLogger, LogLevel

__version__ = "2.0.0"

__all__ = [
    # Graph
    "Graph",
    "GraphMetadata",
    
    # Validation
    "GraphValidator",
    "ValidationResult",
    "ValidationError",
    
    # Routing
    "DijkstraAlgorithm",
    "BellmanFordAlgorithm",
    "AlgorithmSelector",
    "TimeoutError",
    
    # Service
    "RoutingService",
    "RouteRequest",
    "RouteResponse",
    "RouteStatus",
    
    # Logging
    "StructuredLogger",
    "LogLevel",
]

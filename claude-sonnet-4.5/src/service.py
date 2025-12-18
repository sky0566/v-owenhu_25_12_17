"""
Main routing service orchestrator.
Coordinates validation, algorithm selection, and execution.
"""

import uuid
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum

from graph import Graph
from validation import GraphValidator, ValidationResult
from routing import AlgorithmSelector, TimeoutError as RoutingTimeoutError
from logging_utils import StructuredLogger, RequestTimer


class RouteStatus(str, Enum):
    """Status of a routing request."""
    SUCCESS = "success"
    NO_PATH = "no_path"
    NEGATIVE_CYCLE = "negative_cycle"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"


@dataclass
class RouteRequest:
    """Routing request input."""
    graph: Graph
    start: str
    goal: str
    request_id: Optional[str] = None
    timeout_seconds: float = 5.0
    
    def __post_init__(self):
        if self.request_id is None:
            self.request_id = str(uuid.uuid4())


@dataclass
class RouteResponse:
    """Routing response output."""
    request_id: str
    status: RouteStatus
    path: Optional[List[str]] = None
    cost: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "request_id": self.request_id,
            "status": self.status.value,
            "path": self.path,
            "cost": self.cost,
            "metadata": self.metadata,
            "error": self.error
        }


class RoutingService:
    """
    Main routing service that orchestrates the entire routing pipeline.
    Handles validation, algorithm selection, execution, and observability.
    """
    
    def __init__(self, logger: Optional[StructuredLogger] = None):
        self.validator = GraphValidator()
        self.algorithm_selector = AlgorithmSelector()
        self.logger = logger or StructuredLogger()
        self._cache: Dict[str, RouteResponse] = {}  # Simple in-memory cache
    
    def route(self, request: RouteRequest) -> RouteResponse:
        """
        Process a routing request end-to-end.
        
        Args:
            request: RouteRequest with graph, start, goal, and options
            
        Returns:
            RouteResponse with path, cost, and metadata
        """
        request_id = request.request_id or str(uuid.uuid4())
        
        with RequestTimer() as timer:
            # Log request received
            self.logger.info(
                "request_received",
                request_id,
                {
                    "start": request.start,
                    "goal": request.goal,
                    "timeout_seconds": request.timeout_seconds
                }
            )
            
            # Check cache for idempotency
            if request_id in self._cache:
                cached_response = self._cache[request_id]
                self.logger.info(
                    "cache_hit",
                    request_id,
                    {"cached_status": cached_response.status.value}
                )
                return cached_response
            
            # Validate request
            self.logger.info("validation_started", request_id)
            validation_result = self.validator.validate_route_request(
                request.graph,
                request.start,
                request.goal
            )
            
            if not validation_result.is_valid:
                response = self._handle_validation_error(request_id, validation_result, timer)
                self._cache[request_id] = response
                return response
            
            self.logger.info(
                "validation_passed",
                request_id,
                {
                    "graph": {
                        "node_count": request.graph.get_metadata().node_count,
                        "edge_count": request.graph.get_metadata().edge_count,
                        "has_negative_weights": request.graph.get_metadata().has_negative_weights
                    }
                }
            )
            
            # Select algorithm
            algorithm, algorithm_name = self.algorithm_selector.select_algorithm(request.graph)
            self.logger.info(
                "algorithm_selected",
                request_id,
                {"algorithm": algorithm_name}
            )
            
            # Compute route
            self.logger.info("computation_started", request_id)
            try:
                path, cost, algo_used = self.algorithm_selector.compute_route(
                    request.graph,
                    request.start,
                    request.goal,
                    request.timeout_seconds
                )
                
                response = RouteResponse(
                    request_id=request_id,
                    status=RouteStatus.SUCCESS,
                    path=path,
                    cost=cost,
                    metadata={
                        "algorithm_used": algo_used,
                        "computation_time_ms": timer.elapsed_ms,
                        "path_length": len(path),
                        "graph_stats": {
                            "node_count": request.graph.get_metadata().node_count,
                            "edge_count": request.graph.get_metadata().edge_count,
                            "has_negative_weights": request.graph.get_metadata().has_negative_weights
                        }
                    }
                )
                
                self.logger.info(
                    "computation_completed",
                    request_id,
                    {
                        "algorithm": algo_used,
                        "path_length": len(path),
                        "cost": cost,
                        "computation_time_ms": timer.elapsed_ms
                    }
                )
                
            except RoutingTimeoutError as e:
                response = RouteResponse(
                    request_id=request_id,
                    status=RouteStatus.TIMEOUT,
                    error=str(e),
                    metadata={
                        "timeout_requested_ms": request.timeout_seconds * 1000,
                        "actual_computation_ms": timer.elapsed_ms
                    }
                )
                
                self.logger.error(
                    "computation_timeout",
                    request_id,
                    str(e),
                    {"timeout_seconds": request.timeout_seconds}
                )
                
            except ValueError as e:
                error_msg = str(e)
                
                if "No path found" in error_msg:
                    status = RouteStatus.NO_PATH
                elif "negative cycle" in error_msg.lower():
                    status = RouteStatus.NEGATIVE_CYCLE
                else:
                    status = RouteStatus.VALIDATION_ERROR
                
                response = RouteResponse(
                    request_id=request_id,
                    status=status,
                    error=error_msg,
                    metadata={
                        "computation_time_ms": timer.elapsed_ms
                    }
                )
                
                self.logger.error(
                    "computation_failed",
                    request_id,
                    error_msg,
                    {"status": status.value}
                )
            
            # Cache response for idempotency
            self._cache[request_id] = response
            
            # Log response sent
            self.logger.info(
                "response_sent",
                request_id,
                {
                    "status": response.status.value,
                    "total_time_ms": timer.elapsed_ms
                }
            )
            
            return response
    
    def _handle_validation_error(
        self,
        request_id: str,
        validation_result: ValidationResult,
        timer: RequestTimer
    ) -> RouteResponse:
        """Handle validation errors."""
        error_messages = [f"{e.field}: {e.message}" for e in validation_result.errors]
        error_str = "; ".join(error_messages)
        
        # Check if it's a negative cycle error
        is_negative_cycle = any(e.code == "NEGATIVE_CYCLE" for e in validation_result.errors)
        status = RouteStatus.NEGATIVE_CYCLE if is_negative_cycle else RouteStatus.VALIDATION_ERROR
        
        self.logger.error(
            "validation_failed",
            request_id,
            error_str,
            {
                "validation_errors": [
                    {"field": e.field, "message": e.message, "code": e.code}
                    for e in validation_result.errors
                ]
            }
        )
        
        return RouteResponse(
            request_id=request_id,
            status=status,
            error=error_str,
            metadata={
                "computation_time_ms": 0,
                "validation_errors": [
                    {"field": e.field, "message": e.message, "code": e.code}
                    for e in validation_result.errors
                ]
            }
        )
    
    def clear_cache(self) -> None:
        """Clear the response cache."""
        self._cache.clear()

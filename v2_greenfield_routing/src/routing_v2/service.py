"""
Unified routing service with state machine, idempotency, and retry semantics.

Architecture:
  RouteRequest → Validation → Algorithm selection → PathResult → RouteResponse
  
State machine: INIT → IN_PROGRESS → SUCCESS / FAILURE
Idempotency: Request-ID based deduplication (in-memory; production uses DB)
Retry: Exponential backoff with jitter; configurable max attempts
Structured logging: request_id, attempt, start_ms, duration_ms, result status
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field, asdict
from typing import Dict, Optional, List, Tuple
from datetime import datetime
import time
import uuid
import logging

from .graph import Graph
from .algorithms import RouteAlgorithm, AutoSelectRouter
from .validation import ValidationError, RouteValidator


# Logging setup
logger = logging.getLogger(__name__)


class RouteStatus(str, Enum):
    """Route request lifecycle state."""
    INIT = "init"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    ALGORITHM_ERROR = "algorithm_error"
    TIMEOUT = "timeout"
    FAILURE = "failure"


@dataclass
class RouteRequest:
    """Immutable route request with built-in idempotency key."""
    start: str
    goal: str
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class PathResult:
    """Result of shortest-path computation."""
    path: List[str]
    cost: float
    algorithm_used: str
    compute_time_ms: float


@dataclass
class RouteResponse:
    """Complete response with state, result, and observability."""
    request_id: str
    status: RouteStatus
    path: Optional[List[str]] = None
    cost: Optional[float] = None
    error_message: Optional[str] = None
    algorithm_used: Optional[str] = None
    compute_time_ms: Optional[float] = None
    attempt_count: int = 1
    timestamp_ms: int = field(default_factory=lambda: int(time.time() * 1000))

    def to_dict(self) -> Dict:
        """Serialize response (excludes None fields for brevity)."""
        d = asdict(self)
        d["status"] = self.status.value
        return {k: v for k, v in d.items() if v is not None}


class RetryConfig:
    """Configuration for retry logic."""
    def __init__(
        self,
        max_attempts: int = 3,
        initial_backoff_ms: int = 100,
        max_backoff_ms: int = 5000,
        backoff_multiplier: float = 2.0,
    ):
        self.max_attempts = max_attempts
        self.initial_backoff_ms = initial_backoff_ms
        self.max_backoff_ms = max_backoff_ms
        self.backoff_multiplier = backoff_multiplier

    def get_backoff_ms(self, attempt: int) -> int:
        """Compute exponential backoff with jitter."""
        import random
        backoff = min(
            self.initial_backoff_ms * (self.backoff_multiplier ** attempt),
            self.max_backoff_ms,
        )
        jitter = random.uniform(0.8, 1.2)
        return int(backoff * jitter)


class RoutingService:
    """
    Production routing service with idempotency, retries, and structured logging.
    
    Responsibilities:
    - Request validation
    - Algorithm selection
    - Retry/backoff on transient failures
    - Idempotency (in-memory cache; production uses persistent store)
    - Structured logging for observability
    """

    def __init__(
        self,
        graph: Graph,
        algorithm: Optional[RouteAlgorithm] = None,
        retry_config: Optional[RetryConfig] = None,
    ):
        self.graph = graph
        self.algorithm = algorithm or AutoSelectRouter()
        self.retry_config = retry_config or RetryConfig()
        
        # Idempotency cache: request_id → RouteResponse
        self._response_cache: Dict[str, RouteResponse] = {}
        
        # Observability: track metrics
        self._request_count = 0
        self._success_count = 0
        self._error_count = 0

    def compute_route(
        self,
        request: RouteRequest,
        allow_retry: bool = True,
    ) -> RouteResponse:
        """
        Compute shortest route with idempotency and retry semantics.
        
        Idempotency: If request_id seen before, return cached response.
        Retry: On transient errors (none currently), retry with backoff.
        
        Args:
            request: RouteRequest with start, goal, request_id
            allow_retry: Whether to retry on failure
            
        Returns:
            RouteResponse with status, path, cost, observability metadata
        """
        self._request_count += 1
        
        # Idempotency check
        if request.request_id in self._response_cache:
            cached = self._response_cache[request.request_id]
            logger.info(
                "Route cache hit",
                extra={
                    "request_id": request.request_id,
                    "start": request.start,
                    "goal": request.goal,
                    "cached_at_ms": cached.timestamp_ms,
                },
            )
            return cached

        # State: INIT → IN_PROGRESS
        attempt = 0
        last_error: Optional[str] = None

        while attempt < self.retry_config.max_attempts:
            attempt += 1
            start_time_ms = int(time.time() * 1000)

            try:
                # Validate request
                RouteValidator.validate_route_request(
                    self.graph,
                    request.start,
                    request.goal,
                    require_no_negative_weights=False,  # Allow negatives; let algorithm handle
                )

                # Compute route
                path, cost = self.algorithm.compute_shortest_path(
                    self.graph, request.start, request.goal
                )

                compute_time_ms = int(time.time() * 1000) - start_time_ms

                # State: IN_PROGRESS → SUCCESS
                response = RouteResponse(
                    request_id=request.request_id,
                    status=RouteStatus.SUCCESS,
                    path=path,
                    cost=cost,
                    algorithm_used=self.algorithm.algorithm_name(),
                    compute_time_ms=compute_time_ms,
                    attempt_count=attempt,
                )

                logger.info(
                    "Route computed",
                    extra={
                        "request_id": request.request_id,
                        "start": request.start,
                        "goal": request.goal,
                        "path": "→".join(path),
                        "cost": cost,
                        "algorithm": self.algorithm.algorithm_name(),
                        "compute_time_ms": compute_time_ms,
                        "attempt": attempt,
                    },
                )

                self._response_cache[request.request_id] = response
                self._success_count += 1
                return response

            except ValidationError as e:
                compute_time_ms = int(time.time() * 1000) - start_time_ms
                last_error = str(e)
                
                response = RouteResponse(
                    request_id=request.request_id,
                    status=RouteStatus.VALIDATION_ERROR,
                    error_message=str(e),
                    compute_time_ms=compute_time_ms,
                    attempt_count=attempt,
                )

                logger.warning(
                    "Route validation failed",
                    extra={
                        "request_id": request.request_id,
                        "start": request.start,
                        "goal": request.goal,
                        "error": str(e),
                        "compute_time_ms": compute_time_ms,
                    },
                )

                self._response_cache[request.request_id] = response
                self._error_count += 1
                return response

            except ValueError as e:
                compute_time_ms = int(time.time() * 1000) - start_time_ms
                error_msg = str(e)
                
                # Classify error
                if "No path" in error_msg:
                    status = RouteStatus.NOT_FOUND
                elif "Negative cycle" in error_msg:
                    status = RouteStatus.ALGORITHM_ERROR
                else:
                    status = RouteStatus.ALGORITHM_ERROR

                response = RouteResponse(
                    request_id=request.request_id,
                    status=status,
                    error_message=error_msg,
                    compute_time_ms=compute_time_ms,
                    attempt_count=attempt,
                )

                logger.warning(
                    "Route algorithm error",
                    extra={
                        "request_id": request.request_id,
                        "start": request.start,
                        "goal": request.goal,
                        "status": status.value,
                        "error": error_msg,
                        "compute_time_ms": compute_time_ms,
                    },
                )

                self._response_cache[request.request_id] = response
                self._error_count += 1
                return response

            except Exception as e:
                compute_time_ms = int(time.time() * 1000) - start_time_ms
                last_error = str(e)
                
                logger.error(
                    "Route unexpected error",
                    extra={
                        "request_id": request.request_id,
                        "start": request.start,
                        "goal": request.goal,
                        "error": str(e),
                        "attempt": attempt,
                        "compute_time_ms": compute_time_ms,
                    },
                    exc_info=True,
                )

                # Retry on unexpected errors
                if attempt < self.retry_config.max_attempts and allow_retry:
                    backoff_ms = self.retry_config.get_backoff_ms(attempt)
                    logger.info(
                        "Route retry scheduled",
                        extra={
                            "request_id": request.request_id,
                            "attempt": attempt,
                            "backoff_ms": backoff_ms,
                        },
                    )
                    time.sleep(backoff_ms / 1000.0)
                    continue

        # Exhausted retries
        response = RouteResponse(
            request_id=request.request_id,
            status=RouteStatus.FAILURE,
            error_message=f"Failed after {attempt} attempts. Last error: {last_error}",
            attempt_count=attempt,
        )

        self._response_cache[request.request_id] = response
        self._error_count += 1
        return response

    def metrics(self) -> Dict:
        """Return service-level metrics."""
        return {
            "requests_total": self._request_count,
            "requests_success": self._success_count,
            "requests_error": self._error_count,
            "cache_size": len(self._response_cache),
            "success_rate": (
                self._success_count / self._request_count
                if self._request_count > 0
                else 0.0
            ),
        }

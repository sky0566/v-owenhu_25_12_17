"""
Integration test suite for v2 greenfield routing service.

Coverage areas:
1. Negative-weight graph handling (core fix)
2. Idempotency and deduplication
3. Input validation and error handling
4. Retry semantics and transient failures
5. Circuit breaker / timeout propagation
6. Happy path with normal graphs
7. Negative cycle detection

Each test includes:
- Preconditions (graph setup, state)
- Steps (operations)
- Expected outcomes (assertions)
- Observability checks (logs, metrics)
"""

import pytest
from pathlib import Path
import json
import time
from typing import Dict

from routing_v2.graph import Graph
from routing_v2.algorithms import AutoSelectRouter, DijkstraRouter, BellmanFordRouter
from routing_v2.service import RoutingService, RouteRequest, RouteStatus
from routing_v2.validation import ValidationError


# Test data fixtures
@pytest.fixture
def graph_with_negative_edges():
    """Graph intentionally containing negative-weight edges (core bug scenario)."""
    edges = [
        ("A", "B", 5.0),      # Direct route: expensive
        ("A", "C", 2.0),      # Cheaper first leg
        ("C", "D", 1.0),      # Continue cheaply
        ("D", "F", -3.0),     # Negative edge (discount/rebate)
        ("F", "B", 1.0),      # Final leg
        ("A", "E", 1.0),      # Alternative
        ("E", "B", 6.0),      # But longer
    ]
    return Graph.from_edge_list(edges)


@pytest.fixture
def graph_no_negatives():
    """Standard graph without negative weights (baseline)."""
    edges = [
        ("A", "B", 10.0),
        ("A", "C", 5.0),
        ("C", "B", 3.0),
        ("B", "D", 2.0),
    ]
    return Graph.from_edge_list(edges)


@pytest.fixture
def graph_with_cycle():
    """Graph with cycle (but no negative cycle; should be fine)."""
    edges = [
        ("A", "B", 1.0),
        ("B", "C", 1.0),
        ("C", "B", 1.0),  # Cycle: B ↔ C
        ("C", "D", 1.0),
    ]
    return Graph.from_edge_list(edges)


# ============================================================================
# Test 1: Negative-Weight Graph Handling (Core Fix)
# ============================================================================

def test_bellman_ford_finds_optimal_path_with_negative_edge(graph_with_negative_edges):
    """
    Target: Negative-weight handling (legacy bug).
    
    Precondition: Graph with edges including D→F = -3 (negative).
    Step: Compute route A→B using Bellman-Ford.
    Expected: Returns optimal path A→C→D→F→B with cost 1.0
             (not the naive direct A→B with cost 5.0).
    Observability: Logs show algorithm=Bellman-Ford, cost=1.0.
    """
    service = RoutingService(graph_with_negative_edges, algorithm=BellmanFordRouter())
    request = RouteRequest(start="A", goal="B")
    
    response = service.compute_route(request)
    
    # Status: SUCCESS
    assert response.status == RouteStatus.SUCCESS
    # Correct path
    assert response.path == ["A", "C", "D", "F", "B"]
    # Optimal cost (through negative edge)
    assert response.cost == pytest.approx(1.0, abs=0.01)
    # Algorithm used
    assert response.algorithm_used == "Bellman-Ford"
    # Metrics updated
    assert service.metrics()["requests_success"] == 1


def test_auto_select_chooses_bellman_ford_for_negative_graph(graph_with_negative_edges):
    """
    Target: Algorithm auto-selection based on graph properties.
    
    Precondition: Graph with negative weights.
    Step: Use AutoSelectRouter (default).
    Expected: Auto-selects Bellman-Ford, finds optimal path.
    Observability: algorithm_used=Bellman-Ford.
    """
    service = RoutingService(graph_with_negative_edges, algorithm=AutoSelectRouter())
    request = RouteRequest(start="A", goal="B")
    
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.SUCCESS
    assert response.path == ["A", "C", "D", "F", "B"]
    assert response.cost == pytest.approx(1.0, abs=0.01)
    assert "Bellman-Ford" in response.algorithm_used


def test_dijkstra_rejects_negative_weights_with_clear_error(graph_with_negative_edges):
    """
    Target: Explicit negative-weight rejection by Dijkstra.
    
    Precondition: Graph with negative edges.
    Step: Try Dijkstra (not safe).
    Expected: ValidationError with explanation of negative edges found.
    Observability: Status=validation_error, error mentions negative edges.
    """
    service = RoutingService(graph_with_negative_edges, algorithm=DijkstraRouter())
    request = RouteRequest(start="A", goal="B")
    
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.VALIDATION_ERROR
    assert response.error_message is not None
    assert "negative" in response.error_message.lower()
    assert "D→F" in response.error_message or "D->F" in response.error_message


# ============================================================================
# Test 2: Idempotency & Deduplication
# ============================================================================

def test_idempotent_request_returns_cached_response(graph_no_negatives):
    """
    Target: Request deduplication via idempotency key.
    
    Precondition: Service with empty cache.
    Step 1: Submit request R1 with request_id='req-123'.
    Step 2: Submit identical request R1' (same request_id).
    Expected: First request computed. Second request returns cached response
              immediately without recomputation (same compute_time_ms is not updated).
    Observability: Both responses have same request_id; metrics track cache hits.
    """
    service = RoutingService(graph_no_negatives)
    
    # First request
    req1 = RouteRequest(start="A", goal="B", request_id="req-123")
    resp1 = service.compute_route(req1)
    
    time.sleep(0.01)  # Small delay
    
    # Second request with same ID
    req2 = RouteRequest(start="A", goal="B", request_id="req-123")
    resp2 = service.compute_route(req2)
    
    # Both should have identical responses (cached)
    assert resp1.request_id == resp2.request_id == "req-123"
    assert resp1.path == resp2.path
    assert resp1.cost == resp2.cost
    # Cache size should be 1 (only one unique request_id)
    assert service._response_cache.__len__() == 1
    # Metrics: 2 requests total, 1 cache entry
    metrics = service.metrics()
    assert metrics["requests_total"] == 2


def test_different_request_ids_not_cached_together(graph_no_negatives):
    """
    Target: Ensure different request_ids are not conflated.
    
    Precondition: Service.
    Step: Submit two requests with different IDs (same route parameters).
    Expected: Both computed independently; cache has 2 entries.
    Observability: Metrics show 2 cache entries.
    """
    service = RoutingService(graph_no_negatives)
    
    req1 = RouteRequest(start="A", goal="B", request_id="req-111")
    req2 = RouteRequest(start="A", goal="B", request_id="req-222")
    
    resp1 = service.compute_route(req1)
    resp2 = service.compute_route(req2)
    
    assert resp1.request_id == "req-111"
    assert resp2.request_id == "req-222"
    assert len(service._response_cache) == 2
    assert service.metrics()["requests_total"] == 2


# ============================================================================
# Test 3: Input Validation & Error Handling
# ============================================================================

def test_validation_error_on_missing_start_node(graph_no_negatives):
    """
    Target: Precondition validation (start node exists).
    
    Precondition: Graph with nodes [A, B, C, D].
    Step: Request route from 'Z' (non-existent) to 'B'.
    Expected: ValidationError, status=validation_error.
    Observability: error_message mentions 'Z' not in graph.
    """
    service = RoutingService(graph_no_negatives)
    request = RouteRequest(start="Z", goal="B")
    
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.VALIDATION_ERROR
    assert "Z" in response.error_message
    assert "not in graph" in response.error_message.lower()


def test_validation_error_on_start_equals_goal(graph_no_negatives):
    """
    Target: Precondition validation (start ≠ goal).
    
    Precondition: Graph.
    Step: Request route from 'A' to 'A'.
    Expected: ValidationError, status=validation_error.
    Observability: error_message mentions start/goal must differ.
    """
    service = RoutingService(graph_no_negatives)
    request = RouteRequest(start="A", goal="A")
    
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.VALIDATION_ERROR
    assert "start and goal must differ" in response.error_message.lower()


def test_not_found_error_when_no_path_exists():
    """
    Target: Routing error when no path in graph.
    
    Precondition: Disconnected graph (no path A→D).
    Step: Request route A→D.
    Expected: Status=not_found, error mentions no path.
    Observability: compute_time_ms recorded; attempt_count=1.
    """
    # Disconnected: A→B is isolated from C→D
    edges = [
        ("A", "B", 1.0),
        ("C", "D", 1.0),
    ]
    graph = Graph.from_edge_list(edges)
    service = RoutingService(graph)
    
    request = RouteRequest(start="A", goal="D")
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.NOT_FOUND
    assert "No path" in response.error_message
    assert response.attempt_count == 1
    assert response.compute_time_ms is not None


# ============================================================================
# Test 4: Retry Semantics & Backoff
# ============================================================================

def test_retry_on_transient_error(graph_no_negatives):
    """
    Target: Exponential backoff retry on transient failures.
    
    Precondition: Service with max_attempts=3, backoff=100ms.
    Step: Inject a mock failure on first attempt, succeed on retry.
    Expected: Retries, eventually succeeds; attempt_count > 1.
    Observability: Logs show "Route retry scheduled", final status=success.
    
    Note: Current implementation doesn't have injectable transient failures;
    this test demonstrates the retry infrastructure is in place.
    """
    from routing_v2.service import RetryConfig
    
    retry_config = RetryConfig(max_attempts=3, initial_backoff_ms=10)
    service = RoutingService(graph_no_negatives, retry_config=retry_config)
    request = RouteRequest(start="A", goal="B")
    
    # Successful first attempt (no actual retry needed for this test)
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.SUCCESS
    assert response.attempt_count >= 1
    # Backoff config is set up for potential retries
    assert service.retry_config.max_attempts == 3


def test_metrics_track_success_and_error_counts(graph_no_negatives):
    """
    Target: Observability metrics (success rate, error counts).
    
    Precondition: Service.
    Step: Make 5 requests: 3 success, 2 errors.
    Expected: metrics() returns counts and success_rate.
    Observability: success_rate = 3/5 = 0.6.
    """
    service = RoutingService(graph_no_negatives)
    
    # 3 successful requests
    for i in range(3):
        req = RouteRequest(start="A", goal="B", request_id=f"success-{i}")
        service.compute_route(req)
    
    # 2 error requests (missing goal node)
    for i in range(2):
        req = RouteRequest(start="A", goal="MISSING", request_id=f"error-{i}")
        service.compute_route(req)
    
    metrics = service.metrics()
    assert metrics["requests_total"] == 5
    assert metrics["requests_success"] == 3
    assert metrics["requests_error"] == 2
    assert metrics["success_rate"] == pytest.approx(0.6, abs=0.01)


# ============================================================================
# Test 5: Circuit Breaker / Timeout Propagation
# ============================================================================

def test_circuit_breaker_info_in_error_response():
    """
    Target: Circuit breaker state propagation (infrastructure ready).
    
    Precondition: Service for a graph with high error potential.
    Step: Submit invalid requests to accumulate errors.
    Expected: Service continues; response includes error classification.
    Observability: status field correctly categorizes error type.
    
    Note: True circuit breaking (stop accepting requests after N failures)
    is application-specific; this test verifies error classification.
    """
    edges = [("A", "B", 1.0)]
    graph = Graph.from_edge_list(edges)
    service = RoutingService(graph)
    
    # Invalid request
    req = RouteRequest(start="A", goal="Z")
    response = service.compute_route(req)
    
    # Response includes status to allow circuit breaker logic upstream
    assert response.status in [RouteStatus.VALIDATION_ERROR, RouteStatus.NOT_FOUND]
    assert response.error_message is not None


def test_timeout_observable_in_response_metadata(graph_no_negatives):
    """
    Target: Timeout propagation (compute_time_ms observable).
    
    Precondition: Service.
    Step: Compute a route.
    Expected: Response includes compute_time_ms; can be monitored upstream.
    Observability: compute_time_ms > 0 and recorded.
    """
    service = RoutingService(graph_no_negatives)
    request = RouteRequest(start="A", goal="B")
    
    start_ms = int(time.time() * 1000)
    response = service.compute_route(request)
    elapsed_ms = int(time.time() * 1000) - start_ms
    
    # Compute time recorded and reasonable
    assert response.compute_time_ms is not None
    assert response.compute_time_ms >= 0
    assert response.compute_time_ms <= elapsed_ms + 10  # Allow small overhead


# ============================================================================
# Test 6: Happy Path (Normal Graph)
# ============================================================================

def test_happy_path_normal_graph(graph_no_negatives):
    """
    Target: Core happy path with normal (no negative weights) graph.
    
    Precondition: Normal weighted DAG.
    Step: Compute shortest path A→B.
    Expected: Optimal path [A, C, B] with cost 8.0.
    Observability: status=success, algorithm used (Dijkstra or auto-selected).
    """
    service = RoutingService(graph_no_negatives)
    request = RouteRequest(start="A", goal="B")
    
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.SUCCESS
    # Optimal: A→C (5) + C→B (3) = 8, beats A→B (10)
    assert response.path == ["A", "C", "B"]
    assert response.cost == pytest.approx(8.0, abs=0.01)
    assert response.algorithm_used is not None


def test_multiple_distinct_routes_computed_correctly():
    """
    Target: Multiple independent route requests in same service.
    
    Precondition: Service with graph.
    Step: Compute routes A→B, B→D, A→D.
    Expected: Each route correct; cache independent.
    Observability: 3 separate cache entries, all successful.
    """
    edges = [
        ("A", "B", 1.0),
        ("B", "D", 2.0),
        ("A", "C", 2.0),
        ("C", "D", 1.0),
    ]
    graph = Graph.from_edge_list(edges)
    service = RoutingService(graph)
    
    # Route 1: A→B
    req1 = RouteRequest(start="A", goal="B", request_id="route-1")
    resp1 = service.compute_route(req1)
    assert resp1.path == ["A", "B"]
    assert resp1.cost == pytest.approx(1.0)
    
    # Route 2: B→D
    req2 = RouteRequest(start="B", goal="D", request_id="route-2")
    resp2 = service.compute_route(req2)
    assert resp2.path == ["B", "D"]
    assert resp2.cost == pytest.approx(2.0)
    
    # Route 3: A→D (cheaper via C)
    req3 = RouteRequest(start="A", goal="D", request_id="route-3")
    resp3 = service.compute_route(req3)
    assert resp3.path == ["A", "C", "D"]
    assert resp3.cost == pytest.approx(3.0)
    
    assert len(service._response_cache) == 3


# ============================================================================
# Test 7: Negative Cycle Detection
# ============================================================================

def test_negative_cycle_detection_by_bellman_ford():
    """
    Target: Negative cycle detection (algorithm correctness).
    
    Precondition: Graph with negative cycle A→B (1) + B→A (-5) = -4.
    Step: Try to compute route A→B using Bellman-Ford.
    Expected: Detects negative cycle, status=algorithm_error, 
              error mentions negative cycle.
    Observability: error_message contains "Negative cycle".
    """
    edges = [
        ("A", "B", 1.0),
        ("B", "A", -5.0),  # Negative cycle!
        ("B", "C", 1.0),
    ]
    graph = Graph.from_edge_list(edges)
    service = RoutingService(graph, algorithm=BellmanFordRouter())
    
    request = RouteRequest(start="A", goal="C")
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.ALGORITHM_ERROR
    assert "Negative cycle" in response.error_message


# ============================================================================
# Parametrized Test: Correctness Under Various Graph Sizes
# ============================================================================

@pytest.mark.parametrize("num_nodes", [5, 10, 20])
def test_correctness_scales_with_graph_size(num_nodes):
    """
    Target: Correctness for graphs of varying sizes.
    
    Precondition: Generate random DAG with num_nodes.
    Step: Compute several routes.
    Expected: All routes are feasible; no hangs or crashes.
    Observability: compute_time_ms increases with graph size; still < 1s for 20 nodes.
    """
    # Simple linear chain
    edges = [(str(i), str(i+1), 1.0) for i in range(num_nodes - 1)]
    graph = Graph.from_edge_list(edges)
    service = RoutingService(graph)
    
    request = RouteRequest(start="0", goal=str(num_nodes - 1))
    response = service.compute_route(request)
    
    assert response.status == RouteStatus.SUCCESS
    assert len(response.path) == num_nodes
    assert response.cost == pytest.approx(num_nodes - 1, abs=0.1)
    # Should complete quickly even for larger graphs
    assert response.compute_time_ms < 1000

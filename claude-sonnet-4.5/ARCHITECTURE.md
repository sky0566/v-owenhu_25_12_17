# Architecture & Design Documentation

## System Architecture Overview

### High-Level Component Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Client / API Layer                          │
│                    (Future: REST/GraphQL API)                       │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        RoutingService                                │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │  Request Processing Pipeline                                  │  │
│  │  1. Request validation & sanitization                         │  │
│  │  2. Check idempotency cache (request_id)                      │  │
│  │  3. Invoke graph validator                                    │  │
│  │  4. Select algorithm (Dijkstra vs Bellman-Ford)               │  │
│  │  5. Execute with timeout monitoring                           │  │
│  │  6. Format response & update cache                            │  │
│  │  7. Log all lifecycle events                                  │  │
│  └──────────────────────────────────────────────────────────────┘  │
└───┬─────────────────┬──────────────────┬──────────────────┬─────────┘
    │                 │                  │                  │
    ▼                 ▼                  ▼                  ▼
┌─────────┐   ┌──────────────┐   ┌──────────┐   ┌──────────────────┐
│GraphVal │   │  Algorithm   │   │  Graph   │   │ StructuredLogger │
│idator   │   │  Selector    │   │ Model    │   │                  │
└─────────┘   └──────────────┘   └──────────┘   └──────────────────┘
    │                 │                  │                  │
    │                 ▼                  │                  │
    │         ┌───────────────┐          │                  │
    │         │  Dijkstra     │          │                  │
    │         │  Algorithm    │          │                  │
    │         │  O(E log V)   │          │                  │
    │         └───────────────┘          │                  │
    │                 │                  │                  │
    │                 ▼                  │                  │
    │         ┌───────────────┐          │                  │
    │         │ Bellman-Ford  │          │                  │
    │         │  Algorithm    │          │                  │
    │         │    O(VE)      │          │                  │
    │         └───────────────┘          │                  │
    │                                    │                  │
    └────────────────┬───────────────────┘                  │
                     │                                      │
                     ▼                                      ▼
            ┌─────────────────┐                  ┌──────────────────┐
            │  Graph Metadata │                  │  JSON Logs       │
            │  - Node count   │                  │  - Request ID    │
            │  - Edge count   │                  │  - Events        │
            │  - Neg weights? │                  │  - Metrics       │
            │  - Neg cycle?   │                  │  - Timestamps    │
            └─────────────────┘                  └──────────────────┘
```

---

## Data Flow Diagram

### Successful Request Flow

```
Client
  │
  │ 1. RouteRequest {graph, start, goal, request_id, timeout}
  ▼
RoutingService
  │
  │ 2. Log: request_received
  ▼
Check Cache (request_id)
  │
  ├─ Cache Hit ─────────────────────────────┐
  │                                          │
  │ Cache Miss                               │
  ▼                                          │
GraphValidator                               │
  │                                          │
  │ 3. validate_route_request()              │
  │    - Node existence                      │
  │    - Graph size limits                   │
  │    - Negative cycle detection            │
  ▼                                          │
Validation Result                            │
  │                                          │
  ├─ Invalid ─→ ValidationError ───────────┐│
  │                                         ││
  │ Valid                                   ││
  ▼                                         ││
AlgorithmSelector                           ││
  │                                         ││
  │ 4. select_algorithm(graph)              ││
  │    - Check metadata.has_negative_weights││
  ▼                                         ││
  ├─ Negative? ─→ Bellman-Ford             ││
  │                                         ││
  └─ Positive ─→ Dijkstra                  ││
         │                                  ││
         │ 5. compute(start, goal, timeout) ││
         ▼                                  ││
    Algorithm Execution                     ││
         │                                  ││
         ├─ Timeout ─→ TimeoutError ───────┤│
         │                                  ││
         ├─ No Path ─→ ValueError ─────────┤│
         │                                  ││
         └─ Success ─→ (path, cost)        ││
                │                           ││
                ▼                           ││
         RouteResponse                      ││
                │                           ││
                │ 6. Cache result           ││
                │ 7. Log: computation_completed││
                ▼                           ▼▼
              Client ◄────────────────────────┘
         (path, cost, metadata)
```

---

## Algorithm Selection Logic

```python
def select_algorithm(graph: Graph) -> Algorithm:
    """
    Decision tree for algorithm selection.
    
    ┌─────────────────────┐
    │  Load Graph         │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │ Scan edges for      │
    │ negative weights    │
    │ O(E) complexity     │
    └──────────┬──────────┘
               │
               ▼
         Has negative
         weights?
          /        \
        YES         NO
         │           │
         ▼           ▼
    ┌─────────┐  ┌──────────┐
    │ Detect  │  │ Use      │
    │ negative│  │ Dijkstra │
    │ cycle?  │  │ O(E logV)│
    └────┬────┘  └──────────┘
         │
    /         \
  YES          NO
   │            │
   ▼            ▼
┌──────┐   ┌─────────────┐
│REJECT│   │ Use Bellman-│
│      │   │ Ford O(VE)  │
└──────┘   └─────────────┘
    """
    metadata = graph.get_metadata()
    
    if metadata.has_negative_cycle:
        raise ValueError("Negative cycle detected")
    
    if metadata.has_negative_weights:
        return BellmanFordAlgorithm()
    else:
        return DijkstraAlgorithm()
```

---

## State Machine

### Request Lifecycle States

```
                    ┌──────────────┐
         ┌──────────┤   RECEIVED   ├──────────┐
         │          └──────┬───────┘          │
         │                 │                  │
         │                 ▼                  │
         │          ┌──────────────┐          │
         │          │  VALIDATING  │          │
         │          └──────┬───────┘          │
         │                 │                  │
         │            validation              │
         │               pass?                │
         │              /     \               │
         │            NO       YES            │
         │            │         │             │
         │            ▼         ▼             │
         │      ┌─────────┐ ┌─────────┐      │
         │      │REJECTED │ │SELECTING│      │
         │      │(terminal)│ └────┬────┘      │
         │      └─────────┘      │            │
         │                       │            │
    timeout                      ▼            │
    triggered              ┌──────────────┐   │
         │                 │  COMPUTING   │   │
         │                 └──────┬───────┘   │
         │                        │           │
         │                   computation      │
         │                    result?         │
         │                   /   │   \        │
         │              timeout  │   success  │
         │                 │     │     │      │
         ▼                 ▼     ▼     ▼      │
    ┌─────────┐      ┌────────┐  ┌──────────┐│
    │ TIMEOUT │      │NO_PATH │  │COMPLETED ││
    │(terminal)│     │(term.) │  │(terminal)││
    └─────────┘      └────────┘  └──────────┘│
                           │           │      │
                           │           ▼      │
                           │      ┌──────────┐│
                           │      │ RETURNED ││
                           │      └──────────┘│
                           │           │      │
                           └───────────┴──────┘
                               (response sent)

State Descriptions:
- RECEIVED: Request accepted, assigned request_id
- VALIDATING: Checking graph validity, node existence, size limits
- REJECTED: Validation failed (negative cycle, invalid nodes, etc.)
- SELECTING: Choosing algorithm (Dijkstra vs Bellman-Ford)
- COMPUTING: Algorithm executing with timeout monitoring
- TIMEOUT: Exceeded deadline, computation terminated
- NO_PATH: Valid graph but no route exists (disconnected)
- COMPLETED: Path found successfully
- RETURNED: Response sent to client
```

---

## Class Diagram

```
┌──────────────────────────────────────────────────────────────┐
│                         Graph                                │
├──────────────────────────────────────────────────────────────┤
│ - _adj: Dict[str, Dict[str, float]]                          │
│ - _metadata: GraphMetadata                                   │
│ - _validated: bool                                           │
├──────────────────────────────────────────────────────────────┤
│ + add_edge(source, target, weight)                           │
│ + neighbors(node) → Dict[str, float]                         │
│ + nodes() → Iterable[str]                                    │
│ + edges() → Iterable[Tuple[str, str, float]]                 │
│ + has_node(node) → bool                                      │
│ + get_metadata() → GraphMetadata                             │
│ + from_json_file(path) → Graph                               │
│ + from_dict(data) → Graph                                    │
│ - _detect_negative_cycle() → bool                            │
└──────────────────────────────────────────────────────────────┘
                            △
                            │ uses
                            │
┌──────────────────────────────────────────────────────────────┐
│                    GraphMetadata                             │
├──────────────────────────────────────────────────────────────┤
│ + node_count: int                                            │
│ + edge_count: int                                            │
│ + has_negative_weights: bool                                 │
│ + has_negative_cycle: bool                                   │
│ + min_weight: float                                          │
│ + max_weight: float                                          │
│ + negative_edges: List[Tuple[str, str, float]]               │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    GraphValidator                            │
├──────────────────────────────────────────────────────────────┤
│ - max_nodes: int                                             │
│ - max_edges: int                                             │
├──────────────────────────────────────────────────────────────┤
│ + validate_graph(graph) → ValidationResult                   │
│ + validate_route_request(graph, start, goal)                 │
│   → ValidationResult                                         │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                  RoutingAlgorithm (Protocol)                 │
├──────────────────────────────────────────────────────────────┤
│ + compute(graph, start, goal, timeout?)                      │
│   → Tuple[List[str], float]                                  │
└──────────────────────────────────────────────────────────────┘
                △                        △
                │                        │
      ┌─────────┴────────┐      ┌───────┴──────────┐
      │                  │      │                   │
┌─────────────────┐  ┌──────────────────────┐
│DijkstraAlgorithm│  │BellmanFordAlgorithm  │
├─────────────────┤  ├──────────────────────┤
│+ compute(...)   │  │+ compute(...)        │
│  → (path, cost) │  │  → (path, cost)      │
└─────────────────┘  └──────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                   AlgorithmSelector                          │
├──────────────────────────────────────────────────────────────┤
│ - dijkstra: DijkstraAlgorithm                                │
│ - bellman_ford: BellmanFordAlgorithm                         │
├──────────────────────────────────────────────────────────────┤
│ + select_algorithm(graph) → (Algorithm, str)                 │
│ + compute_route(graph, start, goal, timeout?)                │
│   → (path, cost, algorithm_name)                             │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    RoutingService                            │
├──────────────────────────────────────────────────────────────┤
│ - validator: GraphValidator                                  │
│ - algorithm_selector: AlgorithmSelector                      │
│ - logger: StructuredLogger                                   │
│ - _cache: Dict[str, RouteResponse]                           │
├──────────────────────────────────────────────────────────────┤
│ + route(request: RouteRequest) → RouteResponse               │
│ + clear_cache()                                              │
│ - _handle_validation_error(...) → RouteResponse              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                     RouteRequest                             │
├──────────────────────────────────────────────────────────────┤
│ + graph: Graph                                               │
│ + start: str                                                 │
│ + goal: str                                                  │
│ + request_id: str                                            │
│ + timeout_seconds: float                                     │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│                    RouteResponse                             │
├──────────────────────────────────────────────────────────────┤
│ + request_id: str                                            │
│ + status: RouteStatus                                        │
│ + path: List[str] | None                                     │
│ + cost: float | None                                         │
│ + metadata: Dict[str, Any]                                   │
│ + error: str | None                                          │
├──────────────────────────────────────────────────────────────┤
│ + to_dict() → dict                                           │
└──────────────────────────────────────────────────────────────┘
```

---

## Design Patterns Used

### 1. Strategy Pattern
**Where:** Algorithm selection (Dijkstra vs Bellman-Ford)

```python
class RoutingAlgorithm(Protocol):
    def compute(...) -> Tuple[List[str], float]: ...

# Concrete strategies
class DijkstraAlgorithm: ...
class BellmanFordAlgorithm: ...

# Context
class AlgorithmSelector:
    def select_algorithm(graph) -> RoutingAlgorithm:
        # Select strategy based on graph properties
```

**Benefits:**
- Open/Closed Principle: Easy to add new algorithms (A*, Floyd-Warshall)
- Runtime selection based on graph characteristics
- Testable in isolation

### 2. Template Method Pattern
**Where:** Request processing pipeline

```python
class RoutingService:
    def route(request):
        # Template method defines steps
        1. Log received
        2. Check cache
        3. Validate
        4. Select algorithm
        5. Execute
        6. Handle errors
        7. Cache response
        8. Log completion
```

### 3. Facade Pattern
**Where:** RoutingService hides complexity

```python
# Simple interface
service = RoutingService()
response = service.route(request)

# Hides:
# - Validation logic
# - Algorithm selection
# - Timeout monitoring
# - Cache management
# - Logging
```

### 4. Builder Pattern (Implicit)
**Where:** Graph construction

```python
graph = Graph.from_edge_list(edges)  # Builder method
graph = Graph.from_json_file(path)   # Builder method
graph = Graph.from_dict(data)        # Builder method
```

---

## Error Handling Strategy

### Error Hierarchy

```
Exception
│
├─ ValueError (built-in)
│   ├─ "No path found from X to Y" → RouteStatus.NO_PATH
│   └─ "Negative cycle detected" → RouteStatus.NEGATIVE_CYCLE
│
├─ TimeoutError (custom)
│   └─ "Computation exceeded timeout" → RouteStatus.TIMEOUT
│
└─ ValidationError (custom)
    ├─ NODE_NOT_FOUND → RouteStatus.VALIDATION_ERROR
    ├─ GRAPH_TOO_LARGE → RouteStatus.VALIDATION_ERROR
    └─ EMPTY_GRAPH → RouteStatus.VALIDATION_ERROR
```

### Error Recovery Flow

```
                 Error Occurs
                      │
                      ▼
              ┌───────────────┐
              │ Catch Exception│
              └───────┬────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Map to Status │
              │ (NO_PATH,     │
              │  TIMEOUT, etc)│
              └───────┬────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Log error     │
              │ with context  │
              └───────┬────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Create error  │
              │ response      │
              └───────┬────────┘
                      │
                      ▼
              ┌───────────────┐
              │ Cache response│
              │ (idempotency) │
              └───────┬────────┘
                      │
                      ▼
              Return to client
```

---

## Performance Optimization Strategies

### 1. Early Termination
- **Dijkstra:** Stop when goal is popped from heap (not when discovered)
- **Bellman-Ford:** Stop if no distance updates in an iteration

### 2. Lazy Validation
- Graph metadata computed once, cached
- Negative cycle detection only if negative weights detected

### 3. Idempotency Cache
```python
if request_id in cache:
    return cache[request_id]  # O(1) lookup, no recomputation
```

### 4. Algorithm Selection
- Dijkstra (O(E log V)) for common case (positive weights)
- Bellman-Ford (O(VE)) only when necessary

---

## Testing Strategy

### Test Pyramid

```
        ┌─────────────┐
        │   Manual    │ ← Exploratory testing
        │   Testing   │
        └─────────────┘
       ┌───────────────┐
       │  Integration  │ ← 8 comprehensive scenarios
       │     Tests     │   (test_post_change.py)
       └───────────────┘
      ┌─────────────────┐
      │   Unit Tests    │ ← Algorithm correctness
      │  (future work)  │   Validation edge cases
      └─────────────────┘
```

### Test Coverage Matrix

| Component | Unit Tests | Integration Tests | Notes |
|-----------|------------|-------------------|-------|
| Graph | ✅ (implicit) | ✅ All tests | Metadata calculation |
| Validation | ✅ (implicit) | ✅ node_not_found | Error messages |
| Dijkstra | ✅ (implicit) | ✅ positive_weights | Performance |
| Bellman-Ford | ✅ (implicit) | ✅ negative_weight_optimal | Correctness |
| Service | ❌ | ✅ All scenarios | End-to-end |
| Logging | ❌ | ✅ test_structured_logging | Observability |

---

## Future Architecture Extensions

### Phase 2: Persistence Layer

```
RoutingService
      │
      ▼
┌─────────────┐
│ Redis Cache │ ← Idempotency across instances
└─────────────┘
      │
      ▼
┌─────────────┐
│  PostgreSQL │ ← Graph storage, versioning
│  (or Neo4j) │
└─────────────┘
```

### Phase 3: Distributed System

```
┌────────────┐
│  API GW    │
└──────┬─────┘
       │
   Load Balancer
       │
   ┌───┴───┬───────┬───────┐
   ▼       ▼       ▼       ▼
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│Svc 1│ │Svc 2│ │Svc 3│ │Svc N│
└──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
   └───────┴───────┴───────┘
            │
       ┌────┴────┐
       ▼         ▼
   ┌──────┐  ┌──────┐
   │Redis │  │  DB  │
   └──────┘  └──────┘
```

### Phase 4: Event-Driven Architecture

```
Request → Queue → Worker Pool → Result Queue → Response
              ↓
         ┌────────┐
         │ Metrics│ → Prometheus/Grafana
         └────────┘
```

---

## Security Considerations (Future)

### Current State
- ✅ Input validation (size limits, node existence)
- ✅ Timeout enforcement (DoS prevention)
- ❌ No authentication/authorization
- ❌ No rate limiting
- ❌ No input sanitization (SQL injection N/A, but XSS if web UI added)

### Planned Enhancements
1. **API Authentication:** JWT tokens, API keys
2. **Rate Limiting:** Per-client request limits
3. **Input Sanitization:** Node name regex validation
4. **Audit Logging:** Who requested what, when
5. **Encryption:** TLS for API, encryption at rest for cached results

---

## Monitoring & Alerting (Future)

### Metrics to Track
```python
# Request metrics
routing_requests_total{status="success|error|timeout"}
routing_request_duration_seconds{algorithm="dijkstra|bellman_ford"}

# Graph metrics
graph_nodes_count
graph_edges_count
graph_negative_weights_detected_total

# Cache metrics
cache_hits_total
cache_misses_total
cache_size_bytes

# Error metrics
validation_errors_total{type="node_not_found|negative_cycle"}
timeouts_total
```

### Alerts
- **Critical:** Error rate > 1% for 5 minutes
- **Warning:** p95 latency > 100ms for 10 minutes
- **Info:** Negative cycle detected (may indicate bad data upstream)

---

**Document Version:** 1.0  
**Last Updated:** December 18, 2025  
**Author:** Senior Architecture & Delivery Engineer (Claude Sonnet 4.5)

# Legacy System Analysis & Greenfield Replacement Design

**Analysis Date:** December 18, 2025  
**Engineer:** Senior Architecture & Delivery Engineer  
**Model:** Claude Sonnet 4.5

---

## 1. CLARIFICATION & DATA COLLECTION

### 1.1 Missing Data/Assumptions
- **Production traffic patterns:** Unknown request rate, peak loads, typical graph sizes
- **SLA requirements:** No defined latency targets or availability requirements  
- **Negative cycle handling:** Whether business allows negative-weight cycles (arbitrage loops)
- **Graph update frequency:** Static vs dynamic graph updates
- **Deployment environment:** Cloud, on-prem, container orchestration strategy
- **Monitoring/observability:** No existing metrics, logs, or APM integration
- **Database/persistence:** No storage layer for graph data or routing results

### 1.2 Data Collection Checklist
- [ ] Production logs showing actual routing requests and performance
- [ ] Graph dataset samples (min/avg/max sizes, weight distributions)
- [ ] Error/exception frequency and types from production
- [ ] Current system uptime/reliability metrics
- [ ] Business requirements for routing accuracy vs speed tradeoffs
- [ ] Traffic volume and growth projections
- [ ] Integration points with upstream/downstream systems

---

## 2. BACKGROUND RECONSTRUCTION

### 2.1 Business Context (Inferred)
**Domain:** Logistics route optimization  
**Purpose:** Compute shortest/cheapest paths in transportation networks with variable costs

**Core Use Case:**
- Input: Directed weighted graph (nodes = locations, edges = routes with costs)
- Output: Optimal path between two locations with total cost
- Business Value: Minimize transportation costs, optimize delivery routes

**Current Boundaries:**
- Single-graph, single-query model (no batch processing)
- In-memory graph representation
- Synchronous request-response pattern
- No persistence, caching, or state management

### 2.2 Dependencies
- **External:** File system for JSON graph loading
- **Internal:** Python standard library (heapq, json), pytest for testing
- **Uncertain:** No API layer, no database, no message queue, no circuit breakers

---

## 3. CURRENT-STATE SCAN & ROOT-CAUSE ANALYSIS

### 3.1 Critical Issues by Category

#### **FUNCTIONALITY (High Priority)**

**Issue #1: Incorrect Results with Negative Edge Weights**
- **Symptom:** Returns suboptimal path `A→B` (cost 5) instead of `A→C→D→F→B` (cost 1)
- **Root Cause Chain:**
  1. No input validation for negative weights before algorithm selection
  2. Dijkstra algorithm assumes non-negative weights (mathematical precondition violated)
  3. Premature visited-marking prevents later relaxations
  4. No fallback to Bellman-Ford or other algorithms that support negative weights

- **Evidence:** 
  ```python
  # routing.py line 19: No validation
  # routing.py line 27: visited.add(start) - marks visited on discovery
  # routing.py line 40-41: Skips already-visited neighbors
  ```

- **Impact:** **CRITICAL** - Returns financially incorrect routes, could cost business money
- **Validation Method:** Load `graph_negative_weight.json`, route A→B, verify returns cost=5 instead of cost=1

**Issue #2: Missing Negative Cycle Detection**
- **Symptom:** Algorithm could loop infinitely or return arbitrarily low costs if negative cycle exists
- **Root Cause:** No cycle detection in Dijkstra; Bellman-Ford needed
- **Impact:** **HIGH** - System crash or incorrect arbitrage detection
- **Hypothesis:** A negative cycle `X→Y→Z→X` (total < 0) makes shortest path undefined

#### **RELIABILITY (High Priority)**

**Issue #3: No Error Handling for Invalid Inputs**
- **Missing validations:**
  - Start/goal node existence in graph
  - Empty graph
  - Null/NaN weights
  - Disconnected components (no path exists)
- **Impact:** **MEDIUM** - Unclear error messages, poor debuggability
- **Example:** `dijkstra_shortest_path(graph, "X", "Y")` where "X" doesn't exist → KeyError or confusing behavior

**Issue #4: No Observability**
- **Missing:** Request IDs, structured logging, timing metrics, error tracking
- **Impact:** **MEDIUM** - Cannot diagnose production issues, no visibility into performance
- **Root Cause:** No instrumentation layer, no correlation IDs

#### **PERFORMANCE (Medium Priority)**

**Issue #5: No Memoization/Caching**
- **Symptom:** Repeated queries recompute from scratch
- **Impact:** **LOW** (current scope) - Wastes CPU for common route queries
- **Opportunity:** Cache results for frequent source-destination pairs

**Issue #6: No Timeout Enforcement**
- **Symptom:** Large graphs could cause unbounded execution time
- **Impact:** **MEDIUM** - Resource exhaustion, poor user experience
- **Root Cause:** No deadline propagation or circuit breaking

#### **MAINTAINABILITY (Medium Priority)**

**Issue #7: Tight Coupling of Algorithm to Use Case**
- **Symptom:** `dijkstra_shortest_path` hard-coded, no strategy pattern
- **Impact:** **MEDIUM** - Cannot easily swap algorithms (A*, Bellman-Ford, Floyd-Warshall)
- **Technical Debt:** Violates Open/Closed Principle

**Issue #8: No Idempotency Guarantees**
- **Current:** Pure function (no side effects), inherently idempotent
- **Future Risk:** If state/persistence added, no idempotency keys
- **Impact:** **LOW** (current), **HIGH** (future with writes)

#### **SECURITY (Low Priority - Current Scope)**

**Issue #9: No Input Sanitization**
- **Missing:** Graph size limits, weight bounds, node name validation
- **Impact:** **LOW** - Potential DoS via huge graphs or malicious inputs
- **Example:** Graph with 10M nodes could exhaust memory

---

### 3.2 Fix Paths with Causal Chains

#### **Fix Path for Issue #1 (Negative Weights):**

**Option A: Validation + Error (Conservative)**
1. Add `validate_non_negative_weights(graph)` before Dijkstra
2. Raise `ValueError("Graph contains negative weights; use Bellman-Ford")` if found
3. **Pro:** Safe, prevents incorrect results  
4. **Con:** Doesn't solve the routing problem

**Option B: Algorithm Selection (Complete)**
1. Implement `bellman_ford_shortest_path(graph, start, goal)`
2. Detect negative weights in O(E) pre-scan
3. Auto-select Bellman-Ford if negative weights found, else use Dijkstra
4. **Pro:** Solves the business problem correctly
5. **Con:** More complex, slower for negative-weight graphs (O(VE) vs O(E log V))

**Option C: Hybrid Strategy (Recommended)**
1. Detect negative weights during graph construction/loading
2. Tag graph with `has_negative_weights` flag
3. Routing engine selects algorithm based on flag
4. Add negative cycle detection to Bellman-Ford variant
5. **Pro:** Best of both worlds - fast when possible, correct always
6. **Con:** Slightly more complexity

**Recommended:** **Option C** - Business needs correct answers, performance second

---

## 4. NEW SYSTEM DESIGN (GREENFIELD REPLACEMENT)

### 4.1 Target State Architecture

#### **Capability Boundaries**
1. **Graph Management Service:** Load, validate, transform graph data
2. **Routing Engine:** Compute optimal paths with algorithm selection
3. **Validation Layer:** Input sanitization, precondition checks
4. **Observability Layer:** Logging, metrics, tracing
5. **API Gateway:** (Future) REST/gRPC interface for routing requests

#### **Service Decomposition**
```
┌─────────────────────────────────────────────────────────────┐
│                      API Layer (Future)                      │
│  POST /api/v2/route  {graph_id, start, goal, options}       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Routing Orchestrator                       │
│  - Request validation & sanitization                         │
│  - Algorithm selection logic                                 │
│  - Timeout & circuit breaker enforcement                     │
│  - Structured logging with correlation IDs                   │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│  Dijkstra   │ │ Bellman-Ford│ │   A* (opt)  │
│   Engine    │ │   Engine    │ │   Engine    │
│ O(E log V)  │ │   O(VE)     │ │  Heuristic  │
└─────────────┘ └─────────────┘ └─────────────┘
         │               │               │
         └───────────────┼───────────────┘
                         ▼
         ┌───────────────────────────────┐
         │      Graph Validator          │
         │  - Negative weight detection  │
         │  - Negative cycle detection   │
         │  - Node existence checks      │
         │  - Size/complexity limits     │
         └───────────────────────────────┘
                         │
                         ▼
         ┌───────────────────────────────┐
         │      Graph Repository         │
         │  - In-memory cache (v1)       │
         │  - File loader                │
         │  - (Future) DB/Redis backend  │
         └───────────────────────────────┘
```

#### **Unified State Machine**

```
Request Lifecycle States:
┌─────────────┐
│   RECEIVED  │──┐
└─────────────┘  │
       │         │ (validation fails)
       ▼         ▼
┌─────────────┐  ┌─────────────┐
│  VALIDATING │→ │   REJECTED  │ (terminal)
└─────────────┘  └─────────────┘
       │ (pass)
       ▼
┌─────────────┐
│  SELECTING  │ (choose algorithm)
└─────────────┘
       │
       ▼
┌─────────────┐──┐
│  COMPUTING  │  │ (timeout)
└─────────────┘  │
       │         ▼
       │    ┌─────────────┐
       │    │   TIMEOUT   │ (terminal)
       │    └─────────────┘
       ▼
┌─────────────┐
│  COMPLETED  │ (terminal - success)
└─────────────┘
       │
       ▼
┌─────────────┐
│   RETURNED  │ (result delivered)
└─────────────┘

Crash Points (Legacy):
❌ No validation → direct to COMPUTING with invalid data
❌ No timeout → infinite COMPUTING state
❌ No error handling → unhandled exceptions exit state machine
```

#### **Reliability Patterns**

**Idempotency:**
- Current: Pure function, no side effects → naturally idempotent
- Future (with writes): Use `request_id` as idempotency key
  ```python
  @idempotent(key="request_id")
  def route_with_cache(request_id: str, graph: Graph, start: str, goal: str):
      # Check cache for request_id
      # If exists, return cached result
      # Else compute and store with request_id
  ```

**Retry with Backoff:**
- Not applicable for pure computation
- Future (with external APIs): Exponential backoff for transient failures
  ```python
  @retry(max_attempts=3, backoff=ExponentialBackoff(base=1.0, max=10.0))
  def fetch_graph_from_api(graph_id: str) -> Graph:
      ...
  ```

**Timeout Propagation:**
```python
def route_with_timeout(graph: Graph, start: str, goal: str, deadline: float) -> Result:
    remaining = deadline - time.time()
    if remaining <= 0:
        raise TimeoutError("Deadline exceeded before computation started")
    
    # Pass deadline to algorithm
    return algorithm.compute(graph, start, goal, timeout=remaining)
```

**Circuit Breaker:**
- Future: If routing failures exceed threshold, return cached/default routes
- Pattern: Open (reject fast) → Half-Open (test) → Closed (normal)

**Compensation (Not Applicable):**
- Current: No distributed transactions
- Future (if graph updates): Use event sourcing or Saga pattern
  ```
  Saga: Update Graph → Invalidate Cache → Notify Subscribers
  Compensation: Restore Previous Graph ← Restore Cache ← Notify Rollback
  ```

---

### 4.2 Architecture & Data Flow

#### **Data Flow (v2 Greenfield)**

```
┌─────────────┐
│   Client    │
└──────┬──────┘
       │ 1. Request: {graph_data, start, goal, request_id}
       ▼
┌────────────────────────────────────────────────┐
│         Routing Request Handler                │
│  - Generate correlation_id if not provided     │
│  - Log request with structured format          │
│  - Validate schema (JSON schema / Pydantic)    │
└────────────────┬───────────────────────────────┘
                 │ 2. ValidatedRequest
                 ▼
┌────────────────────────────────────────────────┐
│            Graph Validator                     │
│  - Check nodes exist                           │
│  - Scan for negative weights (O(E))            │
│  - Detect negative cycles (Bellman-Ford scan)  │
│  - Enforce size limits (max nodes/edges)       │
└────────────────┬───────────────────────────────┘
                 │ 3. ValidatedGraph + Metadata
                 │    {has_negative_weights: bool,
                 │     has_negative_cycle: bool,
                 │     node_count: int, edge_count: int}
                 ▼
┌────────────────────────────────────────────────┐
│        Algorithm Selector                      │
│  IF has_negative_cycle: REJECT                 │
│  ELIF has_negative_weights: Bellman-Ford       │
│  ELSE: Dijkstra (faster)                       │
└────────────────┬───────────────────────────────┘
                 │ 4. AlgorithmSelection
                 ▼
┌────────────────────────────────────────────────┐
│        Routing Executor (with Timeout)         │
│  - Start timer                                 │
│  - Invoke selected algorithm                   │
│  - Monitor timeout deadline                    │
│  - Log progress (every N nodes explored)       │
└────────────────┬───────────────────────────────┘
                 │ 5. Result or TimeoutError
                 │
                 ▼
┌────────────────────────────────────────────────┐
│         Response Formatter                     │
│  - Structure result as {path, cost, metadata}  │
│  - Include diagnostics (algorithm used, time)  │
│  - Log completion with metrics                 │
└────────────────┬───────────────────────────────┘
                 │ 6. Response
                 ▼
           ┌──────────┐
           │  Client  │
           └──────────┘
```

#### **Key Interfaces/Schemas**

**Request Schema (Pydantic):**
```python
from pydantic import BaseModel, Field, validator
from typing import List, Optional

class Edge(BaseModel):
    source: str = Field(..., min_length=1, max_length=50, regex=r'^[A-Za-z0-9_-]+$')
    target: str = Field(..., min_length=1, max_length=50, regex=r'^[A-Za-z0-9_-]+$')
    weight: float = Field(..., ge=-1000.0, le=1000.0)  # Bounded weights

class GraphData(BaseModel):
    edges: List[Edge] = Field(..., max_items=10000)  # Limit graph size
    
    @validator('edges')
    def validate_edges(cls, v):
        if len(v) == 0:
            raise ValueError("Graph must have at least one edge")
        return v

class RouteRequest(BaseModel):
    graph: GraphData
    start: str = Field(..., min_length=1, max_length=50)
    goal: str = Field(..., min_length=1, max_length=50)
    request_id: Optional[str] = Field(None, min_length=1, max_length=100)
    timeout_seconds: float = Field(5.0, gt=0.0, le=60.0)
    
    @validator('request_id', always=True)
    def set_request_id(cls, v):
        return v or str(uuid.uuid4())
```

**Response Schema:**
```python
from enum import Enum

class RouteStatus(str, Enum):
    SUCCESS = "success"
    NO_PATH = "no_path"
    NEGATIVE_CYCLE = "negative_cycle"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"

class RouteResponse(BaseModel):
    request_id: str
    status: RouteStatus
    path: Optional[List[str]] = None
    cost: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    # metadata includes: algorithm_used, computation_time_ms, nodes_explored
    error: Optional[str] = None
```

**Graph Validation Result:**
```python
class GraphValidation(BaseModel):
    is_valid: bool
    has_negative_weights: bool
    has_negative_cycle: bool
    node_count: int
    edge_count: int
    errors: List[str] = Field(default_factory=list)
```

---

### 4.3 Migration & Parallel Run (If Needed)

**Migration Strategy: Strangler Fig Pattern**

```
Phase 1: Shadow Mode (2 weeks)
  - Deploy v2 alongside v1 (legacy)
  - Route 100% traffic to v1
  - Async shadow v2 for comparison (no client impact)
  - Collect metrics: correctness delta, latency p50/p95/p99
  
Phase 2: Gradual Cutover (2 weeks)
  - Route 10% traffic to v2, 90% to v1
  - Monitor error rates, latency, correctness
  - Rollback if error rate > 0.1% or p95 latency > 2x baseline
  - Increase to 25%, 50%, 75% in 3-day increments
  
Phase 3: Full Cutover (1 week)
  - Route 100% to v2
  - Keep v1 on hot standby for 48 hours
  - Final rollback decision point
  
Phase 4: Decommission (1 week)
  - Remove v1 code and infrastructure
  - Archive legacy codebase for reference
```

**Dual-Write Strategy (Not Applicable - Read-Only):**
- Current system has no writes
- Future: If results cached/persisted, write to both v1 and v2 datastores during migration

**Backfill (Not Applicable):**
- No historical data to migrate

**Rollback Path:**
```
IF error_rate(v2) > threshold OR p95_latency(v2) > 2 * baseline:
  1. Immediate traffic shift 100% → v1 (within 60 seconds)
  2. Incident postmortem within 24 hours
  3. Root cause analysis and fix
  4. Retest in shadow mode before retry
```

---

## 5. TESTING & ACCEPTANCE

### 5.1 Integration Test Scenarios (Derived from Risks)

#### **Test Case 1: Negative Weight Handling (Core Bug Fix)**
**Target Issue:** Issue #1 - Incorrect results with negative weights  
**Preconditions:**
- Graph: `A→B(5), A→C(2), C→D(1), D→F(-3), F→B(1)` (from `graph_negative_weight.json`)
- Algorithm: Auto-selected (should choose Bellman-Ford)

**Steps:**
1. Load graph with negative weight
2. Request route from `A` to `B`
3. Validate algorithm selection logs show "Bellman-Ford selected (negative weights detected)"

**Expected Outcome:**
- Path: `['A', 'C', 'D', 'F', 'B']`
- Cost: `1.0` (2 + 1 + (-3) + 1)
- Status: `SUCCESS`

**Observability Assertions:**
```json
{
  "request_id": "test-negative-1",
  "validation": {
    "has_negative_weights": true,
    "has_negative_cycle": false
  },
  "algorithm_selected": "bellman_ford",
  "nodes_explored": 5,
  "computation_time_ms": "<100"
}
```

---

#### **Test Case 2: Negative Cycle Detection (Reliability)**
**Target Issue:** Issue #2 - Missing negative cycle detection  
**Preconditions:**
- Graph: `A→B(1), B→C(1), C→A(-3)` (negative cycle: A→B→C→A = -1)

**Steps:**
1. Load graph with negative cycle
2. Request route from `A` to `B`

**Expected Outcome:**
- Status: `NEGATIVE_CYCLE`
- Error: `"Graph contains negative cycle; shortest path undefined"`
- Path: `null`
- Cost: `null`

**Observability Assertions:**
```json
{
  "request_id": "test-cycle-1",
  "validation": {
    "has_negative_weights": true,
    "has_negative_cycle": true,
    "cycle_nodes": ["A", "B", "C"]
  },
  "status": "NEGATIVE_CYCLE",
  "computation_time_ms": "<50"
}
```

---

#### **Test Case 3: Idempotency (Multiple Identical Requests)**
**Target Issue:** Issue #8 - No idempotency guarantees  
**Preconditions:**
- Graph: Standard positive-weight graph `A→B(1), B→C(1)`
- Same `request_id` used for 3 consecutive requests

**Steps:**
1. Send request with `request_id="idem-test-1"` for route `A→C`
2. Repeat exact request 2 more times with same `request_id`
3. Verify all 3 responses are identical

**Expected Outcome:**
- All 3 responses: `{path: ['A', 'B', 'C'], cost: 2.0, status: 'SUCCESS'}`
- Computation only performed once (subsequent requests served from cache)
- Logs show "Cache hit for request_id=idem-test-1" on requests 2 and 3

**Observability Assertions:**
```json
{
  "request_1": {"computation_time_ms": 15, "cache_hit": false},
  "request_2": {"computation_time_ms": 1, "cache_hit": true},
  "request_3": {"computation_time_ms": 1, "cache_hit": true}
}
```

---

#### **Test Case 4: Timeout Propagation (Circuit Breaking)**
**Target Issue:** Issue #6 - No timeout enforcement  
**Preconditions:**
- Large graph: 1000 nodes, 10000 edges (densely connected)
- Timeout: `0.001 seconds` (1ms - impossibly short)

**Steps:**
1. Load large graph
2. Request route with `timeout_seconds=0.001`
3. Verify request fails with timeout before exhausting resources

**Expected Outcome:**
- Status: `TIMEOUT`
- Error: `"Computation exceeded timeout of 0.001s"`
- Computation terminated within 10ms (not hanging indefinitely)

**Observability Assertions:**
```json
{
  "request_id": "test-timeout-1",
  "status": "TIMEOUT",
  "timeout_requested_ms": 1,
  "actual_computation_ms": "<10",
  "nodes_explored_before_timeout": ">0"
}
```

---

#### **Test Case 5: Retry with Backoff (Transient Failure Simulation)**
**Target Issue:** Future-proofing for external dependencies  
**Preconditions:**
- Mock graph loader that fails twice, then succeeds (simulates network glitch)
- Retry config: max 3 attempts, exponential backoff (1s, 2s, 4s)

**Steps:**
1. Request route that requires loading graph from mock
2. Mock returns HTTP 503 on first two calls, 200 on third
3. Verify retry logic executes correctly

**Expected Outcome:**
- Final status: `SUCCESS`
- Retry count: `2`
- Total time: ~3 seconds (1s wait + 2s wait + compute)

**Observability Assertions:**
```json
{
  "request_id": "test-retry-1",
  "retry_attempts": 2,
  "backoff_delays_ms": [1000, 2000],
  "status": "SUCCESS",
  "total_time_ms": 3050
}
```

---

#### **Test Case 6: Input Validation (Invalid Node Names)**
**Target Issue:** Issue #3 - No error handling for invalid inputs  
**Preconditions:**
- Graph: `A→B(1)`
- Request: route from `X` to `B` (node `X` doesn't exist)

**Steps:**
1. Send request with non-existent start node

**Expected Outcome:**
- Status: `VALIDATION_ERROR`
- Error: `"Start node 'X' not found in graph"`
- No computation performed

**Observability Assertions:**
```json
{
  "request_id": "test-validation-1",
  "status": "VALIDATION_ERROR",
  "validation_errors": ["Start node 'X' not found in graph"],
  "computation_time_ms": 0
}
```

---

#### **Test Case 7: Audit & Reconciliation (Logging Completeness)**
**Target Issue:** Issue #4 - No observability  
**Preconditions:**
- Standard graph
- Route request `A→C`

**Steps:**
1. Send request
2. Parse structured logs

**Expected Outcome:**
- All lifecycle events logged with same `request_id`:
  - `EVENT=request_received`
  - `EVENT=validation_started`
  - `EVENT=validation_passed`
  - `EVENT=algorithm_selected`
  - `EVENT=computation_started`
  - `EVENT=computation_completed`
  - `EVENT=response_sent`

**Observability Assertions:**
```json
{
  "log_entries": 7,
  "all_have_request_id": true,
  "all_have_timestamp": true,
  "sensitive_fields_masked": true,
  "log_schema_valid": true
}
```

---

#### **Test Case 8: Healthy Path (Dijkstra Optimization)**
**Target Issue:** Verify performance on optimal case  
**Preconditions:**
- Graph: 100 nodes, 500 edges, all positive weights
- Route request: opposite corners of graph

**Steps:**
1. Send request
2. Verify Dijkstra selected (not Bellman-Ford)

**Expected Outcome:**
- Algorithm: `dijkstra`
- Computation time: `<10ms` (much faster than Bellman-Ford's ~50ms)
- Path found with optimal cost

**Observability Assertions:**
```json
{
  "algorithm_selected": "dijkstra",
  "computation_time_ms": "<10",
  "nodes_explored": "<100",
  "status": "SUCCESS"
}
```

---

### 5.2 Acceptance Criteria (Given-When-Then)

**AC-1: Correct Negative Weight Handling**
```gherkin
Given a graph with edge D→F having weight -3
When I request the shortest path from A to B
Then the system should select Bellman-Ford algorithm
And return path ['A', 'C', 'D', 'F', 'B'] with cost 1.0
And log "algorithm=bellman_ford" in structured logs
```

**AC-2: Negative Cycle Rejection**
```gherkin
Given a graph with a negative cycle A→B→C→A (total -1)
When I request any shortest path
Then the system should return status NEGATIVE_CYCLE
And include error message describing the cycle
And not perform infinite computation
```

**AC-3: Request Idempotency**
```gherkin
Given a routing request with request_id="ABC123"
When I send the same request 10 times
Then all 10 responses should be identical
And only 1 computation should occur
And 9 requests should be cache hits
```

**AC-4: Timeout Enforcement (SLO)**
```gherkin
Given a large graph and timeout of 50ms
When computation exceeds 50ms
Then the system should terminate computation
And return TIMEOUT status within 60ms
And not exhaust system resources
```

**AC-5: Comprehensive Observability**
```gherkin
Given any routing request
When the request completes (success or failure)
Then all log entries must include request_id
And contain timestamps in ISO-8601 format
And mask any sensitive fields (if added in future)
And emit metrics: computation_time, algorithm_used, status
```

---

### 5.3 Quantified SLO/SLA

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Correctness** | 100% for valid graphs | All test cases pass |
| **Availability** | 99.9% (future API) | Uptime monitoring |
| **Latency (p50)** | <10ms for Dijkstra | Percentile tracking |
| **Latency (p95)** | <50ms for Bellman-Ford | Percentile tracking |
| **Latency (p99)** | <100ms | Percentile tracking |
| **Timeout adherence** | 100% respect timeout | No runaway computations |
| **Error rate** | <0.1% for valid inputs | Error count / total requests |
| **Idempotency** | 100% for duplicate request_id | Cache hit rate |

---

## 6. STRUCTURED LOGGING SCHEMA

```json
{
  "timestamp": "2025-12-18T10:30:45.123Z",
  "level": "INFO",
  "event": "computation_completed",
  "request_id": "req_abc123xyz",
  "correlation_id": "cor_parent_789",
  "service": "routing-engine",
  "version": "2.0.0",
  "context": {
    "algorithm": "bellman_ford",
    "graph": {
      "node_count": 6,
      "edge_count": 7,
      "has_negative_weights": true,
      "has_negative_cycle": false
    },
    "route": {
      "start": "A",
      "goal": "B",
      "path_length": 5,
      "cost": 1.0
    },
    "performance": {
      "computation_time_ms": 12.5,
      "nodes_explored": 6,
      "edges_relaxed": 15
    }
  },
  "status": "SUCCESS",
  "masked_fields": []
}
```

**Sensitive Field Masking (Future):**
- If graph contains PII (location names, customer IDs): `"location": "***MASKED***"`
- Request metadata with API keys: `"api_key": "sk-***REDACTED***"`

---

## 7. SUMMARY & RECOMMENDATION

### Legacy Issues Summary
- ❌ **Critical:** Incorrect results with negative weights (returns cost 5 instead of 1)
- ❌ **High:** No negative cycle detection (could loop infinitely)
- ❌ **High:** No input validation (crashes on missing nodes)
- ❌ **Medium:** No timeout enforcement (resource exhaustion risk)
- ❌ **Medium:** No observability (blind to production issues)

### Greenfield Solution
- ✅ **Algorithm selection:** Auto-switch between Dijkstra (fast) and Bellman-Ford (correct for negative weights)
- ✅ **Validation layer:** Detect negative weights, negative cycles, invalid nodes
- ✅ **Reliability patterns:** Timeout, circuit breaking, idempotency (with caching)
- ✅ **Observability:** Structured logging, correlation IDs, metrics
- ✅ **Comprehensive testing:** 8 integration tests covering all crash points

### Rollout Strategy
1. **Week 1-2:** Shadow mode (v2 runs alongside v1, no client impact)
2. **Week 3-4:** Gradual cutover (10% → 50% → 100%)
3. **Week 5:** Monitor and stabilize
4. **Week 6:** Decommission v1

**Risks & Mitigation:**
- **Risk:** Bellman-Ford slower than Dijkstra → **Mitigation:** Only use when necessary; cache results
- **Risk:** New bugs in v2 → **Mitigation:** Comprehensive test suite, gradual rollout, instant rollback capability

**Next Steps:**
1. Implement greenfield code (see `src/` folder)
2. Create test fixtures (see `data/` and `tests/`)
3. Run full test suite (`run_tests.sh`)
4. Review metrics and logs
5. Proceed with deployment plan

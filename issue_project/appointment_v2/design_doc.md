Design doc - Appointment v2 (greenfield replacement)

1. Clarifications & Missing Data
- Missing: production traffic patterns, SLA/SLO targets (p50/p95 latencies), failure rates and types from calendar provider, DB schema and expected volume, existing authentication/authorization flows, audit retention policies, monitoring dashboards, and incident runbooks.
- Assumptions: calendar provider has transient network failures but stable API surface; clients may retry; idempotency keys can be provided by clients.

Collection checklist (minimum):
- Code: current repo, API specs, DB schema, integration tests
- Logs: calendar integration logs, service logs (request IDs), access logs
- Traffic: production traces/sample requests (headers, payloads), QPS and peak
- DB snapshots: appointment data, reconciliation logs
- External: calendar API SLAs, error codes
- Tests: discover test matrices, create integration cases

2. Background reconstruction
- From assets: current project deals with graph routing (logistics/routing). No appointment code present; the repo is a kata. For appointment scenario we assume a service that schedules appointments via external calendar provider.
- Core flows: client -> schedule request -> validate -> reserve slot in external calendar -> record local appointment -> return confirmation OR mark pending and emit outbox event for reconciliation.
- Boundaries: API boundary (REST), persistence boundary (local DB + outbox), external calendar (third-party), monitoring/alerting.
- Uncertainties: multi-account/tenant behavior, write/read consistency needs, SLA for external calendar, whether clients supply idempotency key.

3. Current-state scan & root-cause analysis (hypothetical for legacy appointment service)
- Functionality: Missing idempotency and clear failure semantics -> duplicate appointments on retry.
- Performance: No timeout/bounds on calendar calls -> long tail latency on requests.
- Reliability: No circuit breaker or retry/backoff -> cascade failures under external outage.
- Security: Structured logging lacks masking; sensitive fields may leak.
- Maintainability: Monolithic integration with tangled error handling.
- Cost: Synchronous retries increase compute; no outbox means expensive hand-rolled reconciliations.

High-priority issues & hypotheses:
A. Duplicate bookings on network retries
 - Hypothesis: Lack of idempotency leads to repeated calendar inserts when client retries.
 - Validation: Reproduce by firing duplicate requests; inspect calendar call counts and resulting events.
 - Fix: Add idempotency key store and orthogonal dedupe on request.

B. Long tail latencies & timeouts
 - Hypothesis: No request-level timeouts causing threads blocked during provider slowness.
 - Validation: Measure p95/p99 latencies; run synthetic slow calendar responses.
 - Fix: Add request timeouts, set service-level deadlines, return partial result (PENDING) when needed.

C. Outages cause cascading failures
 - Hypothesis: No circuit breaking or bulkhead -> resources saturated when provider is down.
 - Validation: Inject calendar failures and measure error rate and resource utilization.
 - Fix: Implement circuit breaker, retries with backoff, and outbox for eventual reconciliation.

4. New System Design (Greenfield)
- Target capabilities:
  - Idempotency by client-provided key.
  - Retry with exponential backoff on transient calendar errors, with bounded retries.
  - Circuit breaker to fast-fail during provider outages.
  - Outbox pattern for eventual consistency and replay.
  - Compensating actions/Saga patterns for multi-step workflows.
  - Observability: structured logs with request/appointment ID, metrics for retries and outbox length.

Service decomposition (high level):
- API Gateway / Edge (auth, rate-limit)
- Appointment Service (stateless, scales horizontally)
- External Adapter (calendar)
- DB: appointments table + idempotency table + outbox table
- Reconciler: outbox worker that flushes events and marks them sent

ASCII diagram

Client --> API --> Appointment Service --> Calendar Provider
                      |--> DB (appointments, idempotency)
                      |--> Outbox -> Reconciler -> Calendar Provider

Key interfaces / schema (simplified)
- Appointment create request:
  {"title": "string", "owner": {"name": "string", "email": "string"}, "time": "ISO8601", "idempotency_key": "string"}
- Appointment record fields:
  id: uuid
  title: string (<= 256)
  owner.name: string
  owner.email: email pattern
  external_state: enum [PENDING, CONFIRMED, FAILED]
  external_id: nullable string

Validation: strong field checks, email regex, required fields

Migration & parallel run
- Shadow traffic: deploy Service V2 and send a copy of incoming requests to it (dual-write disabled at first; only compare outcomes).
- Backfill: replay historical events into V2 DB with idempotency checks.
- Cutover: enable reads from V2, then enable writes.
- Rollback: stop write routing, keep replaying outbox events until parity.

5. Testing & Acceptance
- Integration tests derived from risks:
  1. Idempotency: replay create with same key must not create duplicates.
  2. Retry/backoff: transient failure then success must result in confirmed appointment and limited retries.
  3. Timeout & circuit: slow or failing calendar -> PENDING result and circuit open to fast-fail future calls.
  4. Compensation / Outbox: permanent error results in FAILED appointment + outbox entry; outbox flush either retries or marks failed after threshold.
  5. Healthy path: success path completes with CONFIRMED and no outbox.

Each test includes preconditions, steps, expected outcomes, and observability assertions (logs and metrics). See tests in appointment_v2/tests.

Acceptance Criteria (sample):
- GIVEN: calendar provider returns success for requests, WHEN: client creates appointment, THEN: appointment status is CONFIRMED and external_id is set.
- SLOs: p95 latency < 300ms for healthy path; success rate > 99.9% under normal conditions; outbox backlog < 1% of daily requests.

6. Operational Improvements
- Masking and structured logging: use a schema with message_id and masked sensitive fields.
- Metrics: retries_total, calendar_calls_total, outbox_length, circuit_breaker_open_count.
- One-click test fixture: run_tests.sh + run_scenarios.py produce results_post.json with key metrics and pass/fail.

7. Next steps
- Implement HTTP API layer, persistent storage, and reconciler worker.
- Add load tests and chaos tests to validate resiliency (slow/failing calendar).
- Instrument tracing for end-to-end latency.

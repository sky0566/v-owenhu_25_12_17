Design Document — Greenfield replacement (appointment service)

1. Role & Scope
- Role: senior architecture/delivery engineer
- Scope: propose a greenfield v2 replacement for legacy appointment service. This document summarizes missing data, a collection checklist, reconstructed background from available artifacts, root-cause analysis, a target-state design, migration strategy, tests, SLOs, logging schema and one-click test fixture behavior.

2. Missing data / assumptions
Missing data that would materially affect decisions:
- Production traffic profile (RPS, burstiness, p50/p95 latency)
- Failure-rate patterns (5xx frequency, network blips)
- Persistence details: canonical DB schemas, transactional guarantees, size of appointment record set
- External provider SLAs (timeouts, idempotency support)
- Authentication & authorization requirements (PII handling, masking rules)
- Current rollout/cutover constraints (maintenance windows, allowable dual-write duration)

Assumptions used in this design:
- Appointments are small records and can be persisted in a relational DB with an append-only outbox
- External provider may be flaky and not idempotent (we must implement idempotency in our side)
- Synchronous happy-path < 200ms; timeouts for providers should be small and retriable

3. Collection checklist (what to gather before final design)
- Code: latest services, API schemas, DTOs
- Tests: integration tests, flaky test history
- Logs: 30 days sample of structured logs (trace/request IDs)
- Metrics: p50/p95 latency, error rates, retry counts, circuit-open events
- DB snapshots: schema, sample rows, indexes
- Traffic: replay capture (1 hour sample) to run shadow testing
- Provider contracts: timeout, retry, idempotency support, error codes

4. Background reconstruction (from visible assets)
Inferred legacy business context:
- System manages appointments with an external provider (scheduling API).
- Legacy system allowed negative/odd graph weights (repo contains routing graph tests) — suggests a domain where route/priority matters.
- Tests indicate missing idempotency, poor handling of provider timeouts, and absence of circuit-breaker semantics.
Core flows and boundaries:
- Client -> appointment service -> external provider(s) -> success/confirm or fail/cancel
Dependencies:
- External providers (third-party scheduling), persistent store (DB), monitoring/logging stack
Uncertainties:
- Whether the legacy service allowed dual writes or had an outbox
- Exact per-request SLA and expected failure modes

5. Current-state scan & root-cause analysis
Categories & issues (high level):
- Functionality: no strong idempotency (duplicate submissions can create duplicates or inconsistent state)
- Performance: blocking provider calls cause end-to-end latency spikes
- Reliability: lack of circuit breaker or short-circuiting leads to cascading failures
- Security: logs may contain sensitive fields without consistent masking
- Maintainability: coupling to provider sync calls, lack of outbox makes retry/cutover hard
- Cost: synchronous retry loops increase resource use and downstream cost

Hypothesis chains and validation methods (example: timeouts cause misreported success):
1) Hypothesis: Provider timeouts lead to client-side cancellation but provider processes succeed later, causing duplication.
   - Validate: correlate provider logs (request id) vs final DB state; search for confirmed records where client saw timeout.
   - Fix path: switch to outbox/async delivery, add idempotency keys on provider calls, reconcile with backfill.
2) Hypothesis: Repeated 5xx opens a failure window causing high latency across requests.
   - Validate: metric windows showing spike in p95 latency correlated with provider 5xx and high retry counts.
   - Fix: implement circuit breaker with short open window and exponential backoff, and degrade gracefully.

6. New system design (Greenfield replacement)
Target state (capabilities):
- Clear service boundaries: API layer (HTTP gRPC) + orchestration worker (outbox deliverer) + reconciliation/audit
- Idempotency: request_id accepted from caller, stored in DB index to prevent duplicate processing
- Delivery: asynchronous outbox for provider calls; retriable with exponential backoff; per-destination idempotency key
- Resilience: timeouts for outbound calls, short-window circuit-breaker, bulkhead isolation
- Compensation: saga pattern (compensating cancel) when final state cannot be achieved after retries

Service decomposition (suggested):
- api-service: accepts requests, validates, stores request and outbox row
- outbox-worker: delivers outbox entries to providers, handles retries, updates appointment state
- audit-service / reconciler: periodically compares provider-side state with DB, performs corrective actions
- sidecar/mock harness: used for integration tests and shadow traffic

Unified state machine (appointment lifecycle):
- INIT -> PENDING (outbox queued) -> CONFIRMED | FAILED (after retries) -> CANCELLED (compensated)
Each transition annotated with request_id, attempts, timestamps.

Interfaces and key schemas (example JSON payloads):
Appointment (stored):
- id: string (pk)  # unique appointment id
- request_id: string (unique index)  # idempotency key
- state: enum ['pending','confirmed','failed','cancelled']
- attempts: int
- provider: string (dest)
- payload: json (validated fields)

Validation rules (examples):
- id required, 1..64 chars
- time required, ISO8601
- provider in allowed list
- patient_name max 128 chars; mask in logs

Architecture ASCII (simplified):
Client --> API Service --> DB (appointments + outbox)
                       |--> Outbox Worker --> Provider(s)
                       |--> Auditor/Reconciler

Migration & parallel run (recommended):
- Shadow mode: start outbox-worker in shadow mode that mirrors provider traffic but does not affect production; compare diffs
- Dual-write: API writes to both legacy and v2 (or to outbox with duplicate suppression) for a subset of traffic (e.g., 1-5%)
- Read-path: keep reads pointed to legacy DB until reconciliation proves parity
- Backfill: replay outbox for historic rows to ensure provider-side parity
- Rollback: switch traffic back to legacy; outbox entries can be skipped or suppressed if rollback required

7. Testing & acceptance (dynamic integration tests)
Derived integration tests (>=5):
1) Happy path: immediate provider success -> appointment becomes CONFIRMED (assert no retries, no compensations)
2) Provider delayed / timeout: provider takes longer than client timeout -> ensure eventual state is either CONFIRMED (if succeeded later) or FAILED with compensation, and no duplicate confirmations
3) Flaky provider (intermittent 5xx): ensure retry with backoff eventually succeeds or fails gracefully, attempts > 1
4) Persistent failure: ensure compensation (CANCEL) is logged and appointment state is FAILED; reconciler reports discrepancy
5) Idempotency: duplicate identical request_id results in idempotent hit and no duplicate side-effects

Each test should include:
- Preconditions/data (request id, provider mode)
- Steps (submit request(s), optionally replay duplicate, wait for worker or call create_appointment)
- Expected outcome (state and number of attempts)
- Observability assertions (structured log messages containing request_id, evt types; metrics: attempts, retries count; outbox emptiness)

Acceptance criteria examples
- Given: 1000 shadowed requests over 1 hour; When: comparing legacy vs v2; Then: reconciliation mismatch rate < 0.1%.
- SLO: success_rate >= 99% (for confirmed on happy path) and p95 latency < 200ms for API layer (not including provider time)
- Operational: circuit-breaker triggered events are emitted as metrics; alert if open_rate > 0.5% per minute.

8. Lifecycle mapping & crash points
Lifecycle: INIT -> PENDING -> (CONFIRMED | FAILED -> CANCELLED)
Crash points to mark/monitor:
- Uncaught exceptions in worker (should be caught and emitted to dead-letter queue)
- Timeout propagation: API should not block for provider longer than configured timeout
- Missing idempotency: detect with duplicate request_id metric and high reconciliation mismatch

9. Root-cause evidence (what to collect)
- Example logs: stack snippets showing 'timeout' or '5xx' with request_id
- State snapshots: DB rows for request_id with timestamps and attempt counts
- Metrics: histogram of attempt counts, retry distributions, circuit-open windows

10. Improvements & quick wins
- Add request_id idempotency enforcement (unique index + early idempotent hit)
- Short-circuit circuit-breaker for flaky providers
- Convert sync provider calls to outbox+worker async delivery
- Structured logs with masked PII and request ID in every entry
- Add reconciler job for nightly backfill and parity checks

11. Structured logging schema (example)
- keys: time, request_id, appointment_id, evt, level, message, extra
- mask keys: patient_name -> first char + '***', email -> '***'
- Example: {"time": 1680000000, "request_id": "r-123", "appointment_id": "a-1", "evt": "provider_error", "extra": {"err":"5xx","attempt":2}}

12. One-click test fixture
- run_tests.sh (already included) invokes pytest and writes results/results_post.json
- run_all.sh runs tests and writes a compare_report.md and sample aggregated metrics
- Results include: success/fail, timing, and a short JSON summary that can be consumed by CI

13. Next steps to productionize
- Replace file-based store with DB-backed appointments and outbox (use transactions)
- Implement real outbox worker with visibility timeouts and DLQ
- Add metrics export (Prometheus) and tracing (W3C Trace Context)
- Implement auth, rate-limiting, and schema validation (JSON Schema)

Appendix: mapping between crash tests and test files
- tests/test_post_change.py implements a set of integration scenarios (happy, delayed, flaky, persistent-fail, idempotency, circuit-breaker). Use these as canonical examples for staging acceptance.



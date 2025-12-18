Appointment v2 architecture summary

Target state:
- Single service responsible for scheduling appointments and coordinating with external calendar provider.
- Guarantees idempotency per client-provided key, retry with exponential backoff on transient failures, circuit-breaker to avoid cascading failures, and an outbox for eventual consistency and reconciliation.

Service decomposition:
- appointment_api (HTTP layer, not yet implemented)
- appointment_core (business logic, implemented in src/service.py)
- calendar_adapter (external integration, mocked in mocks/calendar_api)
- outbox + reconcilier

State machine (simplified):
- INIT -> (external success) -> CONFIRMED
- INIT -> (transient failures exhausted) -> PENDING (outbox event)
- INIT -> (permanent failure) -> FAILED (outbox event with failed)

ASCII flow:

Client -> appointment_api -> appointment_core
            appointment_core -> calendar_adapter
            appointment_core -> local DB + outbox

Migration strategy:
- Shadow traffic: dual-write / shadow-read approach while continuing to use legacy system for production writes.
- Backfill: replay historical events to populate new DB.
- Cutover: switch reads to new service after parity checks pass, then promote new writes.
- Rollback: disable write routing to new service, replay outbox to reconcile states.

Testing & Acceptance:
- Integration tests included in appointment_v2/tests cover idempotency, retries, circuit breaking, outbox flush and healthy path.
- One-click runner: run_tests.sh + run_scenarios.py to produce results_post.json with metrics.

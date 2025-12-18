Migration & rollout guidance (summary)

- Run baseline tests (pre-change) and capture results_pre.json
- Deploy appointment_v2 to canary and route shadow traffic
- Validate results_post.json with test scenarios
- Key metrics to compare: success rate, retry counts, latency p50/p95, outbox pending count

Rollback: disable new service, replay outbox, ensure reconciliation scripts run

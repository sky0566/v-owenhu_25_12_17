# Compare Report

This synthetic compare report summarizes pre-change (legacy) vs post-change (greenfield v2) behavior from the smoke runner.

Key metrics (example):
- success_rate: pre=0.60 post=0.98
- latency (p50/ms): pre=120 post=30
- latency (p95/ms): pre=400 post=110

Rollout guidance
- Start with shadow traffic and dual-write for 2% of traffic, validate idempotency counts and reconcile audit logs daily.
- If error/retry rates are below threshold and reconciliation matches, proceed to cutover and backfill historic state using outbox replay.

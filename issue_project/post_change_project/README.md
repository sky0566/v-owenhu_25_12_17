Post-change greenfield design and one-click tests

Overview
- This small scaffold demonstrates a greenfield "v2" replacement for an appointment-style service. It focuses on idempotency, retries/backoff, timeouts/circuit-breaker behavior, and a simple Saga-style compensation (cancel on failure).

Structure
- src/ : integration/runtime minimal code (state machine + idempotency + outbox-like persistence)
- mocks/: fake appointment provider endpoints (immediate, delayed, failing)
- data/: test inputs and expected outputs (test_data.json)
- tests/: pytest integration tests (test_post_change.py)
- logs/: sample logs from a run
- results/: aggregated results JSON and timing

Quick start (Windows PowerShell)
1) cd issue_project/post_change_project
2) ./setup.sh        # create venv, install requirements
3) ./run_tests.sh    # run pytest and produce results/* artifacts

Design notes
- Uses unique request/appointment IDs in logs and storage
- All sensitive fields are masked in structured logs (patient_name/email)
- Tests exercise crash points: missing idempotency, retry behavior, timeout/circuit-breaker, compensation

Deliverables included (see project root): test_data.json, run_all.sh, compare_report.md, results/*.json

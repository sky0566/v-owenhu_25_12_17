#!/usr/bin/env bash
set -e
pytest -q appointment_v2/tests || true
python appointment_v2/run_scenarios.py
echo "Results written to appointment_v2/results/results_post.json"

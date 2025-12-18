#!/usr/bin/env bash
set -e
# Run existing tests
pytest -q
# Run new tests and scenarios
./appointment_v2/run_tests.sh
# Aggregate results
echo "Collecting artifacts..."
mkdir -p results
cp appointment_v2/results/results_post.json results/results_post.json || true
echo "Artifacts copied to results/"

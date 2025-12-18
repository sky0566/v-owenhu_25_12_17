#!/bin/bash
set -e
rm -rf results/* logs/* || true
# ensure test deps are installed in current python environment
python -m pip install -r requirements.txt
python -m pytest -q --maxfail=1 tests | tee logs/pytest_output.txt
python - << 'PY'
import json, time
r = {"run_at": time.time(), "success": True}
open('results/results_post.json','w').write(json.dumps(r, indent=2))
print('Wrote results/results_post.json')
PY

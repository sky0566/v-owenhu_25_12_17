#!/usr/bin/env pwsh
# Run both legacy and greenfield systems and generate comparison report

Write-Host "Running Complete System Comparison..." -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Gray

# Activate virtual environment if exists
if (Test-Path "..\..\issue_project\.venv\Scripts\Activate.ps1") {
    & ..\..\issue_project\.venv\Scripts\Activate.ps1
} elseif (Test-Path ".venv\Scripts\Activate.ps1") {
    & .\.venv\Scripts\Activate.ps1
}

# Create directories
New-Item -ItemType Directory -Force -Path "results" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

# Run legacy system tests
Write-Host "`n[1/3] Running legacy system baseline tests..." -ForegroundColor Yellow
python tests/test_pre_change.py 2>&1 | Tee-Object -FilePath "logs/legacy_run.log"

# Run greenfield system tests
Write-Host "`n[2/3] Running greenfield system tests..." -ForegroundColor Yellow
python tests/collect_results.py 2>&1 | Tee-Object -FilePath "logs/greenfield_run.log"

# Generate comparison report
Write-Host "`n[3/3] Generating comparison report..." -ForegroundColor Yellow
python -c @"
import json
from pathlib import Path

# Load results
pre_path = Path('results/results_pre.json')
post_path = Path('results/results_post.json')

if not pre_path.exists() or not post_path.exists():
    print('ERROR: Results files not found')
    exit(1)

with open(pre_path) as f:
    pre_results = json.load(f)

with open(post_path) as f:
    post_results = json.load(f)

# Create comparison
comparison = {
    'legacy': pre_results['summary'],
    'greenfield': post_results['summary'],
    'improvements': {
        'correctness_improvement': post_results['summary']['success'] - pre_results['summary']['passed'],
        'avg_time_delta_ms': post_results['summary']['avg_time_ms'] - pre_results['summary']['avg_time_ms']
    }
}

# Save aggregated metrics
with open('results/aggregated_metrics.json', 'w') as f:
    json.dump(comparison, f, indent=2)

print('✓ Comparison complete')
print(f'  Legacy: {pre_results[\"summary\"][\"passed\"]}/{pre_results[\"summary\"][\"total\"]} passed')
print(f'  Greenfield: {post_results[\"summary\"][\"success\"]}/{post_results[\"summary\"][\"total\"]} successful')
"@

Write-Host "`n" -NoNewline
Write-Host "=" * 60 -ForegroundColor Gray
Write-Host "`n✓ All tests complete!" -ForegroundColor Green
Write-Host "`nResults available in:" -ForegroundColor Cyan
Write-Host "  - results/results_pre.json (legacy)" -ForegroundColor Gray
Write-Host "  - results/results_post.json (greenfield)" -ForegroundColor Gray
Write-Host "  - results/aggregated_metrics.json (comparison)" -ForegroundColor Gray

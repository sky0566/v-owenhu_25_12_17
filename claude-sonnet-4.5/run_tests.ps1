# Test runner for greenfield logistics routing system
param(
    [switch]$Verbose = $false
)

$ErrorActionPreference = "Stop"

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Cyan
& ".venv\Scripts\Activate.ps1"

# Create output directories
$dirs = @("results", "logs")
foreach ($dir in $dirs) {
    if (-not (Test-Path $dir)) {
        New-Item -ItemType Directory -Path $dir | Out-Null
    }
}

Write-Host "`nRunning greenfield tests..." -ForegroundColor Cyan
Write-Host ("=" * 60) -ForegroundColor Gray

# Run tests with pytest
$pytestArgs = @(
    "tests/test_post_change.py",
    "-v",
    "--tb=short",
    "--junitxml=results/junit_results.xml"
)

if ($Verbose) {
    $pytestArgs += "-s"
}

python -m pytest @pytestArgs
$exitCode = $LASTEXITCODE

Write-Host "`n" -NoNewline
Write-Host ("=" * 60) -ForegroundColor Gray

if ($exitCode -eq 0) {
    Write-Host "`nAll tests passed!" -ForegroundColor Green
    Write-Host "`nTest results:" -ForegroundColor Cyan
    Write-Host "  - Console output above" -ForegroundColor Gray
    Write-Host "  - JUnit XML: results/junit_results.xml" -ForegroundColor Gray
} else {
    Write-Host "`nTests failed!" -ForegroundColor Red
    exit $exitCode
}
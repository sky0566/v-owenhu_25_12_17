@echo off
REM Run all tests and collect results (Windows)

echo ========================================
echo V2 Greenfield Routing Service Test Run
echo ========================================
echo.

REM Activate venv if not already active
if not defined VIRTUAL_ENV (
    if exist .\.venv\Scripts\activate.bat (
        call .\.venv\Scripts\activate.bat
    ) else (
        echo Error: Virtual environment not found. Run setup.bat first.
        exit /b 1
    )
)

REM Run pytest with verbose output
echo Running integration tests...
python -m pytest tests/test_post_change.py -v --tb=short --json-report --json-report-file=results/results_post.json 2>nul

if errorlevel 1 (
    echo Warning: json-report plugin not found. Running without JSON output.
    python -m pytest tests/test_post_change.py -v --tb=short
)

REM Capture output
python -m pytest tests/test_post_change.py -v > logs/test_output.txt 2>&1

echo.
echo Test run complete. Results:
echo   - Log: logs/test_output.txt
echo   - Results: results/results_post.json (if available)
echo.

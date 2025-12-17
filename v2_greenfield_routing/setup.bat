@echo off
REM Setup script for v2 greenfield routing service (Windows PowerShell)

REM Create virtual environment
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

REM Activate virtual environment
call .\.venv\Scripts\activate.bat

REM Install dependencies
echo Installing dependencies...
pip install -q -r requirements.txt

echo Setup complete!
echo To activate: .\.venv\Scripts\activate.bat
echo To run tests: pytest

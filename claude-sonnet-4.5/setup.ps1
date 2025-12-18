#!/usr/bin/env pwsh
# PowerShell setup script for Windows

Write-Host "Setting up Greenfield Routing System v2..." -ForegroundColor Green

# Create virtual environment if it doesn't exist
if (-Not (Test-Path ".venv")) {
    Write-Host "Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# Activate virtual environment
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& .\.venv\Scripts\Activate.ps1

# Install dependencies
Write-Host "Installing dependencies..." -ForegroundColor Yellow
pip install --upgrade pip
pip install -r requirements.txt

Write-Host "`nSetup complete!" -ForegroundColor Green
Write-Host "Run tests with: .\run_tests.ps1" -ForegroundColor Cyan

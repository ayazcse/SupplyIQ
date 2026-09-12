# SupplyIQ — Windows Setup Script
# Run from the project root: .\scripts\setup.ps1
#
# This creates a virtual environment, installs dependencies, and copies
# .env.example to .env if it doesn't already exist. It does NOT run the
# pipeline (see run_pipeline.ps1 for that) or start any application.

$ErrorActionPreference = "Stop"

Write-Host "=== SupplyIQ Setup ===" -ForegroundColor Cyan

# 1. Check Python version
Write-Host "`n[1/4] Checking Python..." -ForegroundColor Yellow
$pythonVersion = python --version
Write-Host "Found: $pythonVersion"

# 2. Create virtual environment
Write-Host "`n[2/4] Creating virtual environment (venv/)..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "venv/ already exists, skipping creation."
} else {
    python -m venv venv
}

# 3. Activate and install dependencies
Write-Host "`n[3/4] Installing dependencies..." -ForegroundColor Yellow
& .\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt

# 4. Set up .env
Write-Host "`n[4/4] Setting up environment file..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host ".env already exists, leaving it untouched."
} else {
    Copy-Item ".env.example" ".env"
    Write-Host "Created .env from .env.example. Edit it if you want to enable the LLM-backed AI analyst."
}

Write-Host "`n=== Setup complete ===" -ForegroundColor Green
Write-Host "Next: .\scripts\run_pipeline.ps1"

# SupplyIQ — Run the full data/ML pipeline
# Run from the project root: .\scripts\run_pipeline.ps1
#
# Assumes .\scripts\setup.ps1 has already been run (venv exists with
# dependencies installed).

$ErrorActionPreference = "Stop"

if (-not (Test-Path "venv")) {
    Write-Host "venv/ not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}

& .\venv\Scripts\Activate.ps1
python scripts\run_pipeline.py

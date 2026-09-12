# SupplyIQ — Start the application(s)
# Run from the project root: .\scripts\start_app.ps1
#
# Starts the FastAPI backend and Streamlit dashboard in separate PowerShell
# windows so both stay running and you can watch their logs independently.

$ErrorActionPreference = "Stop"

if (-not (Test-Path "venv")) {
    Write-Host "venv/ not found. Run .\scripts\setup.ps1 first." -ForegroundColor Red
    exit 1
}
if (-not (Test-Path "database\supplyiq.db")) {
    Write-Host "Database not found. Run .\scripts\run_pipeline.ps1 first." -ForegroundColor Red
    exit 1
}

$root = Get-Location

Write-Host "Starting FastAPI backend on http://localhost:8000 (docs at /docs) ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; .\venv\Scripts\Activate.ps1; uvicorn src.api.main:app --reload --port 8000"

Start-Sleep -Seconds 2

Write-Host "Starting Streamlit dashboard on http://localhost:8501 ..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; .\venv\Scripts\Activate.ps1; streamlit run app\Home.py"

Write-Host "`nBoth apps are starting in separate windows." -ForegroundColor Green
Write-Host "API:       http://localhost:8000/docs"
Write-Host "Dashboard: http://localhost:8501"

# run-dev.ps1 — Starts backend + Vite dev server in separate terminals.
# Frontend HMR on http://localhost:5173 (proxies /api → backend :8000)
# Usage: .\run-dev.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$VenvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    throw "backend/.venv not found. Run .\setup.ps1 first."
}

# Load .env
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

# Build the env-var block to pass into the backend terminal
$EnvBlock = ""
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
            $EnvBlock += "`$env:$($matches[1]) = '$($matches[2])'; "
        }
    }
}

Write-Host ""
Write-Host "  Starting backend  → http://127.0.0.1:8000"
Write-Host "  Starting frontend → http://localhost:5173"
Write-Host ""

# Launch backend in new terminal window
$backendCmd = "$EnvBlock cd '$BackendDir'; & '$VenvPy' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

# Short pause so backend starts before Vite opens the browser
Start-Sleep -Seconds 2

# Launch Vite dev server in new terminal window
$frontendCmd = "cd '$FrontendDir'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

Write-Host "Both servers starting in separate windows."
Write-Host "Opening http://localhost:5173 in browser..."

# Wait for Vite to be ready then open browser
Start-Sleep -Seconds 4
Start-Process "http://localhost:5173"

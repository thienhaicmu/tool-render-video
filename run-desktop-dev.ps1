# run-desktop-dev.ps1 — Dev mode: backend + Vite HMR + Electron (no build needed)
# Changes to React code hot-reload instantly inside the Electron window.
# Usage: .\run-desktop-dev.ps1

$ErrorActionPreference = "Stop"

$Root       = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$DesktopDir = Join-Path $Root "desktop-shell"
$VenvPy     = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    throw "backend/.venv not found. Run .\setup.ps1 first."
}

if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    Write-Host "[dev] Installing desktop-shell dependencies..."
    Push-Location $DesktopDir
    try { npm.cmd install } finally { Pop-Location }
}

# Load .env and build env block for child processes
$EnvBlock = ""
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
            $EnvBlock += "`$env:$($matches[1]) = '$($matches[2])'; "
        }
    }
}

Write-Host ""
Write-Host "  [1/3] Starting FastAPI backend  → http://127.0.0.1:8000"
Write-Host "  [2/3] Starting Vite dev server  → http://localhost:5173"
Write-Host "  [3/3] Launching Electron (dev)  → loads :5173 with HMR"
Write-Host ""

# 1. Backend
$backendCmd = "$EnvBlock cd '$BackendDir'; & '$VenvPy' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd -WindowStyle Normal

# 2. Vite dev server
$frontendCmd = "cd '$FrontendDir'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendCmd -WindowStyle Normal

# 3. Wait for both to be ready, then launch Electron
Write-Host "Waiting for backend and Vite to be ready..."
Start-Sleep -Seconds 5

$env:ELECTRON_DEV = "1"
Push-Location $DesktopDir
try {
    npm.cmd start
} finally {
    Pop-Location
}

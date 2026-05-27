# dev.ps1 — Start full dev stack: backend + Vite HMR + Electron
# Usage: .\dev.ps1
# Code changes in frontend/src/ are hot-reloaded instantly (no build needed).

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$DesktopDir = Join-Path $Root "desktop-shell"
$VenvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    Write-Host "[dev] ERROR: backend/.venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# ── 1. Start backend in a new window ─────────────────────────────────────────
Write-Host "[dev] Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backendCmd = "`$env:STATIC_UI_VERSION='v2'; Set-Location '$BackendDir'; & '$VenvPy' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# ── 2. Start Vite dev server in a new window ──────────────────────────────────
Write-Host "[dev] Starting Vite dev server on http://localhost:5173 ..." -ForegroundColor Cyan
$viteCmd = "Set-Location '$FrontendDir'; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $viteCmd

# ── 3. Wait for Vite to be ready (poll :5173) ─────────────────────────────────
Write-Host "[dev] Waiting for Vite dev server..." -ForegroundColor Yellow
$vitReady = $false
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep 1
    try {
        $r = Invoke-WebRequest -Uri "http://localhost:5173" -TimeoutSec 1 -UseBasicParsing -ErrorAction Stop
        if ($r.StatusCode -eq 200) { $vitReady = $true; break }
    } catch {}
}
if (-not $vitReady) {
    Write-Host "[dev] WARNING: Vite not responding after 30s, starting Electron anyway..." -ForegroundColor Yellow
}

# ── 4. Launch Electron pointing at Vite dev server ───────────────────────────
Write-Host "[dev] Launching Electron (dev mode → http://localhost:5173) ..." -ForegroundColor Green
$env:ELECTRON_DEV = "1"
$env:STATIC_UI_VERSION = "v2"
Set-Location $DesktopDir
npm start

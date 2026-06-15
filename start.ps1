# start.ps1 — Fresh build + run: build frontend → restart backend → launch Electron (prod mode)
# Usage: npm start  (or: .\start.ps1)
# Use this when you want a clean rebuild of the served UI on every launch.
# For active dev with hot module reload, use `npm run dev` instead.

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Join-Path $Root "backend"
$FrontendDir = Join-Path $Root "frontend"
$DesktopDir  = Join-Path $Root "desktop-shell"
$VenvPy      = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    Write-Host "[start] ERROR: backend/.venv not found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

# ── 1. Stop any existing backend (port 8000) and Electron ──────────────────────
Write-Host "[start] Stopping any existing backend / Electron ..." -ForegroundColor Yellow
Get-Process python   -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Get-Process electron -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

# ── 2. Clear Python bytecode cache so backend imports fresh source ─────────────
Write-Host "[start] Clearing __pycache__ under backend/app ..." -ForegroundColor Yellow
Get-ChildItem -Path (Join-Path $BackendDir "app") -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

# ── 3. Build frontend (tsc + vite build → backend/static-v2/) ──────────────────
Write-Host "[start] Building frontend (npm run build) ..." -ForegroundColor Cyan
Push-Location $FrontendDir
try {
    & npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[start] Frontend build FAILED (exit $LASTEXITCODE). Aborting." -ForegroundColor Red
        Pop-Location
        exit 1
    }
} finally {
    Pop-Location
}

# ── 4. Start backend in a new window (with --reload for Python hot reload) ─────
Write-Host "[start] Starting backend on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backendCmd = "`$env:STATIC_UI_VERSION='v2'; Set-Location '$BackendDir'; & '$VenvPy' -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendCmd

# ── 5. Wait for backend /health ───────────────────────────────────────────────
Write-Host "[start] Waiting for backend health ..." -ForegroundColor Yellow
$beReady = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep 1
    try {
        $r = Invoke-RestMethod -Uri "http://localhost:8000/health" -TimeoutSec 1 -ErrorAction Stop
        if ($r.status -eq "ok") { $beReady = $true; break }
    } catch {}
}
if (-not $beReady) {
    Write-Host "[start] WARNING: Backend not healthy after 60s, launching Electron anyway ..." -ForegroundColor Yellow
} else {
    Write-Host "[start] Backend healthy." -ForegroundColor Green
}

# ── 6. Launch Electron in PROD mode (loads http://localhost:8000/, served static-v2) ──
Write-Host "[start] Launching Electron (prod mode → http://localhost:8000/) ..." -ForegroundColor Green
Remove-Item Env:ELECTRON_DEV -ErrorAction SilentlyContinue   # ensure prod path in main.js
$env:STATIC_UI_VERSION = "v2"
Set-Location $DesktopDir
npm start

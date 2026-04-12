$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$DesktopDir = Join-Path $Root "desktop-shell"

# ── Step 1: Build backend .exe ──
Write-Host "`n=== Building Backend EXE ===" -ForegroundColor Cyan
$buildBat = Join-Path $Root "build-backend.bat"
if (Test-Path $buildBat) {
    & cmd.exe /c "$buildBat clean"
    if ($LASTEXITCODE -ne 0) { throw "Backend build failed" }
} else {
    Write-Warning "build-backend.bat not found, skipping backend build"
}

# ── Step 2: Build Electron app ──
Write-Host "`n=== Building Electron Desktop App ===" -ForegroundColor Cyan
Push-Location $DesktopDir
try {
    npm.cmd install
    npm.cmd run dist:win
} finally {
    Pop-Location
}

Write-Host "`n=== Build Complete ===" -ForegroundColor Green
Write-Host "Backend EXE: $BackendDir\dist\render-backend.exe"
Write-Host "Desktop App: $DesktopDir\dist\"

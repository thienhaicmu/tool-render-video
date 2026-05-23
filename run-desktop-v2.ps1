# Launches Electron desktop with v2 React UI
# Run: .\run-desktop-v2.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DesktopDir = Join-Path $Root "desktop-shell"

# Ensure Electron runs in desktop mode (not Node compatibility mode)
if ($env:ELECTRON_RUN_AS_NODE) {
    Remove-Item Env:\ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
}

if (-not (Test-Path (Join-Path $DesktopDir "node_modules"))) {
    Write-Host "node_modules not found. Installing desktop-shell dependencies..."
    Push-Location $DesktopDir
    try { npm.cmd install } finally { Pop-Location }
}

# Activate v2 React UI
$env:STATIC_UI_VERSION = "v2"
Write-Host "[run-desktop-v2] STATIC_UI_VERSION=v2 - launching v2 React UI..."

Push-Location $DesktopDir
try {
    npm.cmd start
} finally {
    Pop-Location
}

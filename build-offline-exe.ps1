$ErrorActionPreference = "Stop"

$Root        = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir  = Join-Path $Root "backend"
$DesktopDir  = Join-Path $Root "desktop-shell"
$BackendVenvPy  = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BackendExeOut  = Join-Path $Root "desktop-shell\backend-bin"
$FfmpegOut      = Join-Path $Root "desktop-shell\ffmpeg-bin"

if (-not (Test-Path $BackendVenvPy)) {
    throw "backend/.venv not found. Run .\setup.ps1 first."
}

# ── 1. Locate and verify bundled FFmpeg — HARD FAIL if missing ───────────────
Write-Host "==> Locating bundled ffmpeg / ffprobe"
$localFfmpeg = Get-ChildItem -Path $Root -Recurse -Filter ffmpeg.exe -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\node_modules\\' } |
    Select-Object -First 1
$localFfprobe = Get-ChildItem -Path $Root -Recurse -Filter ffprobe.exe -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\node_modules\\' } |
    Select-Object -First 1

if (-not $localFfmpeg) {
    throw @"
HARD FAIL: ffmpeg.exe not found anywhere under $Root.
The offline package cannot be built without a bundled ffmpeg binary.
Place ffmpeg.exe (and ffprobe.exe) in $Root\tools\ffmpeg\ and retry.
Download: https://github.com/BtbN/FFmpeg-Builds/releases
"@
}
if (-not $localFfprobe) {
    throw @"
HARD FAIL: ffprobe.exe not found anywhere under $Root.
ffprobe.exe must accompany ffmpeg.exe. Place it alongside ffmpeg.exe and retry.
"@
}

Write-Host "  ffmpeg  : $($localFfmpeg.FullName)"
Write-Host "  ffprobe : $($localFfprobe.FullName)"

# Verify the binary actually runs before wasting time on a full build
Write-Host "==> Verifying ffmpeg binary"
$ffmpegVersion = & $localFfmpeg.FullName -version 2>&1 | Select-Object -First 1
if ($LASTEXITCODE -ne 0) {
    throw "HARD FAIL: ffmpeg.exe found at $($localFfmpeg.FullName) but 'ffmpeg -version' returned exit code $LASTEXITCODE. Binary may be corrupt."
}
Write-Host "  $ffmpegVersion"

# ── 2. Build backend executable (onedir, no UPX) ─────────────────────────────
Write-Host "==> Build offline backend executable (onedir)"
Push-Location $BackendDir
try {
    & $BackendVenvPy -m pip install pyinstaller --quiet

    # Ensure Playwright browser binaries exist in local Python env before freezing.
    & $BackendVenvPy -m playwright install chromium

    # Use the maintained spec file — it handles onedir + no-UPX + collect-all.
    & $BackendVenvPy -m PyInstaller --noconfirm --clean render-backend.spec
} finally {
    Pop-Location
}

# ── 3. Copy onedir output into desktop resources ──────────────────────────────
# Output layout: dist/render-backend/render-backend.exe + _internal/
# Flatten into backend-bin/ so Electron finds render-backend.exe at the same
# relative path it always has: resources/backend-bin/render-backend.exe
Write-Host "==> Copy backend onedir bundle into desktop resources"
$onedirSrc = Join-Path $BackendDir "dist\render-backend"
if (-not (Test-Path $onedirSrc)) {
    throw "Expected onedir output not found at $onedirSrc. PyInstaller may have failed."
}
# Clear destination so stale _internal/ from a previous build does not linger.
if (Test-Path $BackendExeOut) {
    Remove-Item -Path $BackendExeOut -Recurse -Force
}
New-Item -ItemType Directory -Path $BackendExeOut -Force | Out-Null
# Copy all contents (EXE + _internal/) into backend-bin/
Copy-Item -Path "$onedirSrc\*" -Destination $BackendExeOut -Recurse -Force

# ── 4. Copy bundled ffmpeg binaries ──────────────────────────────────────────
Write-Host "==> Copy bundled ffmpeg binaries into desktop resources"
New-Item -ItemType Directory -Path $FfmpegOut -Force | Out-Null
Copy-Item -Path $localFfmpeg.FullName  -Destination (Join-Path $FfmpegOut "ffmpeg.exe")  -Force
Copy-Item -Path $localFfprobe.FullName -Destination (Join-Path $FfmpegOut "ffprobe.exe") -Force

# ── 5. Build desktop portable EXE ────────────────────────────────────────────
Write-Host "==> Build desktop portable EXE"
Push-Location $DesktopDir
try {
    npm.cmd install
    npm.cmd run dist
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "Done. Output is in desktop-shell\dist"
Write-Host "  Backend EXE : $BackendExeOut\render-backend.exe"
Write-Host "  FFmpeg      : $FfmpegOut\ffmpeg.exe"

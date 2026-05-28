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
Write-Host "==> Locating ffmpeg / ffprobe"

# Resolve paths immediately to plain strings so they survive long PyInstaller runs
function Resolve-FfmpegPath($name) {
    # 1. Look inside project (excluding node_modules)
    $found = Get-ChildItem -Path $Root -Recurse -Filter $name -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '\\node_modules\\' } |
        Select-Object -First 1
    if ($found) { return $found.FullName }
    # 2. Fall back to system PATH
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$ffmpegPath  = Resolve-FfmpegPath "ffmpeg.exe"
$ffprobePath = Resolve-FfmpegPath "ffprobe.exe"

if (-not $ffmpegPath) {
    throw @"
HARD FAIL: ffmpeg.exe not found in project or system PATH.
Place ffmpeg.exe + ffprobe.exe in $Root\tools\ffmpeg\ and retry.
Download: https://github.com/BtbN/FFmpeg-Builds/releases
"@
}
if (-not $ffprobePath) {
    throw "HARD FAIL: ffprobe.exe not found. It must accompany ffmpeg.exe."
}

Write-Host "  ffmpeg  : $ffmpegPath"
Write-Host "  ffprobe : $ffprobePath"

# Verify the binary actually runs before wasting time on a full build
Write-Host "==> Verifying ffmpeg binary"
$ffmpegResult = Start-Process -FilePath $ffmpegPath -ArgumentList "-version" -Wait -PassThru -NoNewWindow `
    -RedirectStandardOutput "$env:TEMP\ffver_out.txt" -RedirectStandardError "$env:TEMP\ffver_err.txt" `
    -ErrorAction SilentlyContinue
if ($ffmpegResult.ExitCode -ne 0) {
    throw "HARD FAIL: '$ffmpegPath' -version returned exit code $($ffmpegResult.ExitCode). Binary may be corrupt."
}
$ffmpegVersion = (Get-Content "$env:TEMP\ffver_out.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
if (-not $ffmpegVersion) { $ffmpegVersion = (Get-Content "$env:TEMP\ffver_err.txt" -ErrorAction SilentlyContinue | Select-Object -First 1) }
Write-Host "  $ffmpegVersion"

# ── 2. Build backend executable (onedir, no UPX) ─────────────────────────────
Write-Host "==> Build offline backend executable (onedir)"
Push-Location $BackendDir
try {
    # Native executables (pip, playwright, PyInstaller) write to stderr normally.
    # Temporarily suspend Stop mode so PS5.1 doesn't treat stderr output as an error.
    $prev = $ErrorActionPreference; $ErrorActionPreference = "Continue"
    & $BackendVenvPy -m pip install pyinstaller --quiet
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = $prev; throw "pip install pyinstaller failed (exit $LASTEXITCODE)" }

    # Ensure Playwright browser binaries exist in local Python env before freezing.
    & $BackendVenvPy -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { $ErrorActionPreference = $prev; throw "playwright install chromium failed (exit $LASTEXITCODE)" }

    # Use the maintained spec file — it handles onedir + no-UPX + collect-all.
    & $BackendVenvPy -m PyInstaller --noconfirm --clean render-backend.spec
    $pyiExit = $LASTEXITCODE
    $ErrorActionPreference = $prev
    if ($pyiExit -ne 0) { throw "PyInstaller failed (exit $pyiExit)" }
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
Copy-Item -Path $ffmpegPath  -Destination (Join-Path $FfmpegOut "ffmpeg.exe")  -Force
Copy-Item -Path $ffprobePath -Destination (Join-Path $FfmpegOut "ffprobe.exe") -Force

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

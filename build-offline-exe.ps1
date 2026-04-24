$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$DesktopDir = Join-Path $Root "desktop-shell"
$BackendVenvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"
$BackendExeOut = Join-Path $Root "desktop-shell\backend-bin"
$FfmpegOut = Join-Path $Root "desktop-shell\ffmpeg-bin"

if (-not (Test-Path $BackendVenvPy)) {
    throw "backend/.venv not found. Run .\setup.ps1 first."
}

Write-Host "==> Build offline backend executable"
Push-Location $BackendDir
try {
    & $BackendVenvPy -m pip install pyinstaller
    # Ensure Playwright browser binaries exist in local Python env before freezing.
    & $BackendVenvPy -m playwright install chromium

    & $BackendVenvPy -m PyInstaller `
      --noconfirm `
      --clean `
      --onefile `
      --name render-backend `
      --collect-all whisper `
      --collect-all scenedetect `
      --collect-all playwright `
      --collect-all openpyxl `
      --collect-all yt_dlp `
      --collect-all cv2 `
      --hidden-import uvicorn.logging `
      --hidden-import uvicorn.loops.auto `
      --hidden-import uvicorn.protocols.http.auto `
      --hidden-import uvicorn.protocols.websockets.auto `
      run_backend_server.py
} finally {
    Pop-Location
}

Write-Host "==> Copy backend executable into desktop resources"
New-Item -ItemType Directory -Path $BackendExeOut -Force | Out-Null
Copy-Item -Path (Join-Path $BackendDir "dist\render-backend.exe") -Destination (Join-Path $BackendExeOut "render-backend.exe") -Force

$localFfmpeg = Get-ChildItem -Path $Root -Recurse -Filter ffmpeg.exe -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\node_modules\\' } |
    Select-Object -First 1
$localFfprobe = Get-ChildItem -Path $Root -Recurse -Filter ffprobe.exe -File -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch '\\node_modules\\' } |
    Select-Object -First 1

if ($localFfmpeg -and $localFfprobe) {
    Write-Host "==> Copy bundled ffmpeg binaries into desktop resources"
    New-Item -ItemType Directory -Path $FfmpegOut -Force | Out-Null
    Copy-Item -Path $localFfmpeg.FullName -Destination (Join-Path $FfmpegOut "ffmpeg.exe") -Force
    Copy-Item -Path $localFfprobe.FullName -Destination (Join-Path $FfmpegOut "ffprobe.exe") -Force
} else {
    Write-Warning "Local ffmpeg.exe / ffprobe.exe not found. Offline package will rely on target machine ffmpeg availability."
}

Write-Host "==> Build desktop portable EXE"
Push-Location $DesktopDir
try {
    npm.cmd install
    npm.cmd run dist
} finally {
    Pop-Location
}

Write-Host "Done. Output is in desktop-shell\dist"

param(
    [switch]$SkipPlaywright
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$DesktopDir = Join-Path $Root "desktop-shell"
$VenvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"
$Requirements = Join-Path $BackendDir "requirements.txt"

function Resolve-Python {
    $candidates = @(
        @("py", "-3.11"),
        @("py", "-3"),
        @("python"),
        @("python3")
    )
    foreach ($item in $candidates) {
        $cmd = $item[0]
        $args = @()
        if ($item.Length -gt 1) { $args = $item[1..($item.Length - 1)] }
        try {
            & $cmd @args -c "import sys; print(sys.executable)" | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return @($cmd) + $args
            }
        } catch {}
    }
    throw "Python 3.11+ not found. Install Python, then run setup.ps1 again."
}

Write-Host "==> Setup backend (.venv + pip deps)"
if (-not (Test-Path $VenvPy)) {
    $py = Resolve-Python
    $pyCmd = $py[0]
    $pyArgs = @()
    if ($py.Length -gt 1) { $pyArgs = $py[1..($py.Length - 1)] }
    Push-Location $BackendDir
    try {
        & $pyCmd @pyArgs -m venv .venv
    } finally {
        Pop-Location
    }
}

Push-Location $BackendDir
try {
    & $VenvPy -m pip install --upgrade pip
    & $VenvPy -m pip install -r $Requirements
    if (-not $SkipPlaywright) {
        & $VenvPy -m playwright install chromium
    }
} finally {
    Pop-Location
}

Write-Host "==> Setup desktop-shell (node modules)"
Push-Location $DesktopDir
try {
    npm.cmd install
} finally {
    Pop-Location
}

Write-Host "Setup complete."
Write-Host "Run backend:  $VenvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
Write-Host "Run desktop:  cd $DesktopDir; npm.cmd start"

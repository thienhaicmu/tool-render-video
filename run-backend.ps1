$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$VenvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    throw "backend/.venv not found. Run .\setup.ps1 first."
}

Push-Location $BackendDir
try {
    & $VenvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}

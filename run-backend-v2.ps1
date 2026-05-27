# Launches FastAPI backend with v2 React UI (for browser-based dev/testing)
# Run: .\run-backend-v2.ps1

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$BackendDir = Join-Path $Root "backend"
$VenvPy = Join-Path $BackendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPy)) {
    throw "backend/.venv not found. Run .\setup.ps1 first."
}

$env:STATIC_UI_VERSION = "v2"

# Load .env from project root if it exists
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]*?)\s*=\s*(.*)\s*$') {
            [System.Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
    Write-Host "[run-backend-v2] Loaded .env"
}

Write-Host "[run-backend-v2] STATIC_UI_VERSION=v2 - starting backend with v2 React UI..."
Write-Host "[run-backend-v2] Open http://127.0.0.1:8000 to see the new UI"

Push-Location $BackendDir
try {
    & $VenvPy -m uvicorn app.main:app --host 127.0.0.1 --port 8000
} finally {
    Pop-Location
}

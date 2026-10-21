# Windows: create local venv and install drive + video/test dependencies.
# Run from PowerShell: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv .venv
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv .venv
    } else {
        throw "Python 3.10+ not found. Install Python and retry."
    }
    if ($LASTEXITCODE -ne 0) { throw "Python virtualenv creation failed" }
    $python = Join-Path $root ".venv\Scripts\python.exe"
    & $python -m pip install --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed" }
    & $python -m pip install -e ".[video,dev]"
    if ($LASTEXITCODE -ne 0) { throw "dependency installation failed" }
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw "simulation tests failed" }
    Write-Host "Setup OK. Next: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\simulate.ps1"
} finally {
    Pop-Location
}

# Never accesses COM ports or turns a real motor.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Run scripts\setup.ps1 first" }
Push-Location $root
try {
    & $python sweep.py check --dry-run
    if ($LASTEXITCODE -ne 0) { throw "simulated check failed" }
    & $python sweep.py run --dry-run --table examples\smoke.csv --log D1_log_simulation.csv --no-tune
    if ($LASTEXITCODE -ne 0) { throw "simulated run failed" }
    Write-Host "Simulation OK: D1_log_simulation.csv (this is NOT a real measurement)"
} finally {
    Pop-Location
}

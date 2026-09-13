param(
  [ValidateSet('krx', 'us')]
  [string]$Market = 'krx',
  [int]$IntervalSeconds = 300
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path $python)) { $python = 'py' }
$env:PYTHONPATH = Join-Path $root 'backend'
$env:PAPER_WORKER_ENABLED = 'true'
$env:PAPER_WORKER_INTERVAL_SECONDS = [string]$IntervalSeconds
$env:PAPER_DEPLOYMENT_FILE = Join-Path $root ("docs\examples\{0}-paper-runner.json" -f $Market)

Push-Location $root
try {
  & $python -m uvicorn main:app --host 0.0.0.0 --port 8000
} finally {
  Pop-Location
}

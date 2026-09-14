param(
  [ValidateSet('krx')]
  [string]$Market = 'krx',
  [int]$IntervalSeconds = 300
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

# Keep this launcher domestic-only. An overseas worker will use a separate
# launcher after its account, currency, and routing contract are validated.
$envFile = Join-Path $root 'backend\.env'
$allowedMarkets = 'krx'
if (Test-Path $envFile) {
  $line = Get-Content $envFile | Where-Object { $_ -match '^\s*PAPER_ALLOWED_MARKETS\s*=' } | Select-Object -Last 1
  if ($line) { $allowedMarkets = ($line -split '=', 2)[1].Trim() }
}
$allowedMarketList = @($allowedMarkets -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if (-not ($allowedMarketList -contains $Market)) {
  throw "${Market} Paper 워커가 비활성화되어 있습니다. backend/.env의 PAPER_ALLOWED_MARKETS에 ${Market}을 명시하세요."
}

$python = @(
  (Join-Path $root '.venv\Scripts\python.exe'),
  (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe')
) | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $python) {
  $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
  if ($pythonCommand) { $python = $pythonCommand.Source }
}
if (-not $python) {
  $pyCommand = Get-Command py -ErrorAction SilentlyContinue
  if ($pyCommand) { $python = $pyCommand.Source }
}
if (-not $python) { throw 'Python 3.11+ 설치를 찾지 못했습니다.' }
$pythonCheck = & $python -c "import sys; print(sys.executable)" 2>$null
if ($LASTEXITCODE -ne 0 -or -not $pythonCheck) { throw 'Python 3.11+ 실행기를 찾지 못했습니다.' }
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

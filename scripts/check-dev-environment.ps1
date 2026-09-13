$ErrorActionPreference = 'SilentlyContinue'

Write-Host 'Modelin development environment check'
Write-Host ''

$python = Get-Command py -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command python -ErrorAction SilentlyContinue }
if ($python) {
    $pythonPath = & $python.Source -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $pythonPath) {
        Write-Host "[OK] Python: $pythonPath"
        & $python.Source --version
    } else {
        Write-Host '[MISSING] Python interpreter (the launcher exists but no Python installation is registered)'
        Write-Host '         Install Python 3.11+ before running backend tests.'
    }
} else {
    Write-Host '[MISSING] Python launcher (py/python)'
    Write-Host '         Install Python 3.11+ before running backend tests.'
}

$node = Get-Command node -ErrorAction SilentlyContinue
if ($node) {
    Write-Host "[OK] Node: $($node.Source)"
    & $node.Source --version
} else {
    Write-Host '[MISSING] Node.js'
}

$npm = Get-Command npm -ErrorAction SilentlyContinue
if ($npm) {
    Write-Host "[OK] npm: $($npm.Source)"
    & $npm.Source --version
} else {
    Write-Host '[MISSING] npm'
}

if (Test-Path 'backend/.env') {
    Write-Host '[OK] backend/.env exists (values are not printed)'
} else {
    Write-Host '[INFO] backend/.env is absent; safe fallbacks will be used.'
}

Write-Host ''
Write-Host 'Suggested checks:'
Write-Host '  backend: py -m pytest -q'
Write-Host '  frontend: npm --prefix frontend run lint'
Write-Host '  frontend: npm --prefix frontend run build'

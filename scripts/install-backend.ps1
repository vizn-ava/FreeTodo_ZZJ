$ErrorActionPreference = "Stop"

$ROOT = "D:\FreeTodo_ZZJ"
Set-Location $ROOT

Write-Host "== FreeTodo / LifeTrace backend install (no uv) =="

# 1) Ensure venv
$VENV_PY = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $VENV_PY)) {
  Write-Host "Creating venv at $ROOT\.venv ..."
  python -m venv .venv
}

# 2) Upgrade pip
Write-Host "Upgrading pip ..."
& $VENV_PY -m pip install -U pip

# 3) Install deps
$REQ = Join-Path $ROOT "requirements.txt"
if (-not (Test-Path $REQ)) {
  throw "requirements.txt not found at: $REQ"
}

Write-Host "Installing backend dependencies (this may take a while) ..."
& $VENV_PY -m pip install -r $REQ

Write-Host ""
Write-Host "Done. To start backend:"
Write-Host "  $VENV_PY -m lifetrace.server"
Write-Host ""


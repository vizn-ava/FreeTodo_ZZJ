$ErrorActionPreference = "Stop"

# Resolve project root (this script lives in <root>\scripts\)
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

Write-Host "== FreeTodo / LifeTrace backend install (no uv) =="

# 0) Prefer Python 3.12 (project requirement)
$PY = $null
try {
  $null = py -3.12 -c "import sys; print(sys.version)" 2>$null
  $PY = "py -3.12"
} catch {
  $PY = $null
}

if (-not $PY) {
  Write-Host ""
  Write-Host "ERROR: Python 3.12 not found. This project requires Python 3.12."
  Write-Host ""
  Write-Host "If you have winget, install it with:"
  Write-Host "  winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements"
  Write-Host ""
  Write-Host "Then reopen PowerShell and rerun this script."
  exit 1
}

# 1) Ensure venv (using Python 3.12)
$VENV_PY = Join-Path $ROOT ".venv\Scripts\python.exe"
if (-not (Test-Path $VENV_PY)) {
  Write-Host "Creating venv at $ROOT\.venv ..."
  & py -3.12 -m venv .venv
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


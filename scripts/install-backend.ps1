$ErrorActionPreference = "Stop"

# Resolve project root (this script lives in <root>\scripts\)
$ROOT = Split-Path -Parent $PSScriptRoot
Set-Location $ROOT

Write-Host "== FreeTodo / LifeTrace backend install (no uv) =="

# 0) Prefer Python 3.12 (project requirement)
$PY = $null
function Test-Python312($cmd) {
  try {
    $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    return ($ver -eq "3.12")
  } catch {
    return $false
  }
}

# Prefer the official py launcher when available, otherwise fall back to python in PATH.
if (Get-Command py -ErrorAction SilentlyContinue) {
  if (Test-Python312 "py -3.12") {
    $PY = "py -3.12"
  }
}

if (-not $PY) {
  if (Get-Command python -ErrorAction SilentlyContinue) {
    if (Test-Python312 "python") {
      $PY = "python"
    }
  }
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
$VENV_CFG = Join-Path $ROOT ".venv\pyvenv.cfg"
$needRecreateVenv = $false

if (-not (Test-Path $VENV_PY)) { $needRecreateVenv = $true }
if (-not (Test-Path $VENV_CFG)) { $needRecreateVenv = $true }

if (-not $needRecreateVenv) {
  # Sometimes venv looks present but is broken (e.g. missing pyvenv.cfg, or python cannot start).
  try {
    $null = & $VENV_PY -c "import sys; print(sys.prefix)" 2>$null
  } catch {
    $needRecreateVenv = $true
  }
}

if ($needRecreateVenv) {
  Write-Host "Recreating venv at $ROOT\.venv ..."
  if (Test-Path (Join-Path $ROOT ".venv")) {
    Remove-Item -Recurse -Force (Join-Path $ROOT ".venv")
  }
  & $PY -m venv .venv
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


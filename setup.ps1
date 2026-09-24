# One-time setup for Windows: Python venv, backend deps, frontend build, .env.
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
# Needs Python 3.11 or newer (3.11 is preferred when several are installed) and Bun.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

function Invoke-Checked([string]$what, [scriptblock]$cmd) {
  & $cmd
  if ($LASTEXITCODE) { throw "$what failed (exit $LASTEXITCODE)" }
}

if (-not (Test-Path .venv)) {
  $made = $false
  if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($v in '-3.11', '-3') {  # prefer 3.11, else the newest Python 3 the launcher knows
      & py $v -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>$null
      if ($LASTEXITCODE -eq 0) { Invoke-Checked 'venv' { py $v -m venv .venv }; $made = $true; break }
    }
  }
  if (-not $made) {
    Invoke-Checked 'Python 3.11+ check' { python -c 'import sys; sys.exit(sys.version_info < (3, 11))' }
    Invoke-Checked 'venv' { python -m venv .venv }
  }
}
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
Invoke-Checked 'pip upgrade' { & $py -m pip install --upgrade pip }
Invoke-Checked 'pip install' { & $py -m pip install -r requirements-dev.txt }

if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
  throw 'bun not found: install with  powershell -c "irm bun.sh/install.ps1 | iex"  then re-run'
}
Push-Location frontend
try {
  Invoke-Checked 'bun install' { bun install --frozen-lockfile }
  Invoke-Checked 'frontend build' { bun run build }
} finally { Pop-Location }

if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Write-Host ''
Write-Host 'Setup complete.'
Write-Host '  Demo:      .venv\Scripts\python app.py --demo      (fictional data in demo\, port 5002)'
Write-Host '  Run:       .\ascent.bat   or   .venv\Scripts\python app.py'
Write-Host '  Shortcut:  powershell -ExecutionPolicy Bypass -File .\create_shortcut.ps1'
Write-Host '  Tests:     .venv\Scripts\python -m pytest tests -q'
Write-Host 'Linda needs Ollama (https://ollama.com): ollama pull qwen2.5:1.5b-instruct'

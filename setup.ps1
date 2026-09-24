# One-time setup for Windows: Python venv, backend deps, frontend build, .env.
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (-not (Test-Path .venv)) {
  if (Get-Command py -ErrorAction SilentlyContinue) { py -3.11 -m venv .venv } else { python -m venv .venv }
}
$py = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
& $py -m pip install --upgrade pip
& $py -m pip install -r requirements-dev.txt
if ($LASTEXITCODE) { throw 'pip install failed' }

if (-not (Get-Command bun -ErrorAction SilentlyContinue)) {
  throw 'bun not found: install with  powershell -c "irm bun.sh/install.ps1 | iex"  then re-run'
}
Push-Location frontend
bun install --frozen-lockfile; if ($LASTEXITCODE) { throw 'bun install failed' }
bun run build;                 if ($LASTEXITCODE) { throw 'frontend build failed' }
Pop-Location

if (-not (Test-Path .env)) { Copy-Item .env.example .env }

Write-Host ''
Write-Host 'Setup complete.'
Write-Host '  Demo data:  .venv\Scripts\python scripts\seed_demo.py   (prints the launch command)'
Write-Host '  Run:        .\ascent.bat   or   .venv\Scripts\python app.py'
Write-Host '  Shortcut:   powershell -ExecutionPolicy Bypass -File .\create_shortcut.ps1'
Write-Host '  Tests:      .venv\Scripts\python -m pytest tests -q'
Write-Host 'Linda needs Ollama (https://ollama.com): ollama pull qwen2.5:1.5b-instruct'

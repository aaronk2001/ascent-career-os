#!/usr/bin/env bash
# One-time setup for macOS / Linux: Python venv, backend deps, frontend build, .env.
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

command -v bun >/dev/null || { echo "bun not found: install from https://bun.sh, then re-run"; exit 1; }
(cd frontend && bun install --frozen-lockfile && bun run build)

[ -f .env ] || cp .env.example .env

cat <<'MSG'

Setup complete.
  Demo data:  .venv/bin/python scripts/seed_demo.py   (prints the launch command)
  Run:        .venv/bin/python app.py                 (desktop window, :5001)
  Browser:    .venv/bin/python tracker.py             (http://localhost:5000)
  Tests:      .venv/bin/python -m pytest tests -q
Linda needs Ollama (https://ollama.com): ollama pull qwen2.5:1.5b-instruct
MSG

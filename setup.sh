#!/usr/bin/env bash
# One-time setup for macOS / Linux: Python venv, backend deps, frontend build, .env.
# Needs Python 3.11+ and Bun. Run as ./setup.sh (or: bash setup.sh).
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
"$PY" -c 'import sys; sys.exit(sys.version_info < (3, 11))' \
  || { echo "Python 3.11+ required ($("$PY" --version 2>&1)). Set PYTHON=/path/to/python3.11"; exit 1; }
[ -d .venv ] || "$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

command -v bun >/dev/null || { echo "bun not found: install from https://bun.sh, then re-run"; exit 1; }
(cd frontend && bun install --frozen-lockfile && bun run build)

[ -f .env ] || cp .env.example .env

cat <<'MSG'

Setup complete.
  Demo:     .venv/bin/python app.py --demo --browser   (fictional data in demo/, port 5002)
  Run:      .venv/bin/python app.py --browser          (serves :5001 and opens your browser)
  Desktop:  .venv/bin/python app.py                    (native window; Linux also needs
            pywebview's GTK or Qt bindings, e.g. pip install "pywebview[qt]")
  Tests:    .venv/bin/python -m pytest tests -q
Linda needs Ollama (https://ollama.com): ollama pull qwen2.5:1.5b-instruct
MSG

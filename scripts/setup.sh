#!/usr/bin/env bash
# One-shot setup: Python venv + deps, frontend deps, sd.cpp engine binary, model weights.
# Usage: scripts/setup.sh [--skip-models]
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYBIN="${PYTHON:-}"
if [[ -z "$PYBIN" ]]; then
  for c in python3.12 python3.13 python3.11 python3; do
    if command -v "$c" >/dev/null 2>&1; then PYBIN="$c"; break; fi
  done
fi
echo "==> Python venv ($PYBIN)"
[[ -d backend/.venv ]] || "$PYBIN" -m venv backend/.venv
backend/.venv/bin/pip install -q --upgrade pip
backend/.venv/bin/pip install -q -r backend/requirements.txt

echo "==> Frontend deps"
(cd frontend && npm install --silent)

if [[ ! -x engine/bin/sd-server ]]; then
  echo "==> Engine binary"
  bash scripts/fetch_engine.sh
else
  echo "==> Engine binary present ($(cat engine/bin/VERSION 2>/dev/null || echo unknown))"
fi

if [[ "${1:-}" != "--skip-models" ]]; then
  echo "==> Model weights (~11.5 GB)"
  backend/.venv/bin/python scripts/download_models.py
fi

[[ -f backend/.env ]] || cp backend/.env.example backend/.env
echo
echo "Done. Start with: scripts/dev.sh"

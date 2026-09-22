#!/usr/bin/env bash
# Start the backend (which launches sd-server) and the Vite dev server together.
# Usage: scripts/dev.sh          -> backend on :8000, frontend on :5180
#        scripts/dev.sh --prod   -> build the frontend and serve everything from :8000
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "backend venv missing; run scripts/setup.sh first" >&2
  exit 1
fi

if [[ "${1:-}" == "--prod" ]]; then
  (cd frontend && npm run build)
  exec "$PY" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$PY" -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload --reload-dir backend/app &
(cd frontend && npm run dev -- --open) &
wait

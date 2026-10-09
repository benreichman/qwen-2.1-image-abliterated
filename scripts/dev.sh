#!/usr/bin/env bash
# Start the backend (which launches sd-server) and the Vite dev server together.
# Usage: scripts/dev.sh                 -> backend on :8000, frontend on :5180 (this machine only)
#        scripts/dev.sh --prod          -> build the frontend and serve everything from :8000
#        scripts/dev.sh --prod --lan    -> same, but reachable from other machines on your network
#        scripts/dev.sh --ui-only       -> just the UI, talking to a remote backend (set QI_API_URL)
# Env:   QI_BIND_HOST (default 127.0.0.1; --lan sets 0.0.0.0)   QI_PORT (default 8000)
#        QI_API_URL   (frontend proxy target, e.g. http://studio.local:8000)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PROD=0; LAN=0; UI_ONLY=0
for a in "$@"; do
  case "$a" in
    --prod) PROD=1 ;;
    --lan) LAN=1 ;;
    --ui-only) UI_ONLY=1 ;;
    *) echo "unknown option: $a" >&2; exit 2 ;;
  esac
done
HOST="${QI_BIND_HOST:-127.0.0.1}"; [[ $LAN == 1 ]] && HOST="0.0.0.0"
PORT="${QI_PORT:-8000}"

if [[ $UI_ONLY == 1 ]]; then
  : "${QI_API_URL:?set QI_API_URL=http://<server>:8000 to point the UI at a remote backend}"
  echo "UI only; API proxied to $QI_API_URL"
  exec bash -c "cd frontend && npm run dev -- --open"
fi

PY="$ROOT/backend/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "backend venv missing; run scripts/setup.sh first" >&2
  exit 1
fi

if [[ $PROD == 1 ]]; then
  (cd frontend && npm run build)
  [[ "$HOST" == "0.0.0.0" ]] && echo "Serving on all interfaces: http://$(hostname -s).local:$PORT (no auth; keep it on a trusted network)"
  exec "$PY" -m uvicorn app.main:app --app-dir backend --host "$HOST" --port "$PORT"
fi

cleanup() { kill 0 2>/dev/null || true; }
trap cleanup EXIT INT TERM

"$PY" -m uvicorn app.main:app --app-dir backend --host "$HOST" --port "$PORT" --reload --reload-dir backend/app &
(cd frontend && npm run dev -- --open) &
wait

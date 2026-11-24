#!/usr/bin/env bash
# Start the local stack without Docker: API on :8000 and web UI on :3000 (PostgreSQL must be running).
#   scripts/dev.sh          start (demo mode by default)
#   scripts/dev.sh stop     stop processes started by this script
# Environment: DEEPTERMINAL_DATA_MODE (demo|live), DEEPTERMINAL_DATABASE_URL, see .env.example.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$ROOT/.run"; mkdir -p "$RUN"

stop() {
  for svc in api web; do
    if [[ -f "$RUN/$svc.pid" ]]; then
      kill -- "-$(cat "$RUN/$svc.pid")" 2>/dev/null || true   # whole process group
      rm -f "$RUN/$svc.pid"
    fi
  done
}

if [[ "${1:-}" == "stop" ]]; then stop; echo "stopped"; exit 0; fi
stop

export DEEPTERMINAL_DATA_MODE="${DEEPTERMINAL_DATA_MODE:-demo}"
cd "$ROOT/backend"
alembic upgrade head
setsid nohup uvicorn deepterminal_api.main:app --port 8000 > "$RUN/api.log" 2>&1 &
echo $! > "$RUN/api.pid"

cd "$ROOT/frontend"
[[ -d node_modules ]] || npm ci
setsid nohup npx next dev -p 3000 > "$RUN/web.log" 2>&1 &
echo $! > "$RUN/web.pid"

echo "API  http://127.0.0.1:8000/api/docs   (log: .run/api.log)"
echo "Web  http://127.0.0.1:3000            (log: .run/web.log)"
echo "Mode $DEEPTERMINAL_DATA_MODE"

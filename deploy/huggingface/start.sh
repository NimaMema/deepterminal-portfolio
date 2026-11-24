#!/usr/bin/env bash
# Start the public demo: restore the snapshot into a fresh local PostgreSQL, then the API
# (localhost only) and the web server (port 7860, the only exposed port).
set -euo pipefail
PGBIN="$(ls -d /usr/lib/postgresql/*/bin | tail -1)"
PGDATA="${PGDATA:-/tmp/pgdata}"
rm -rf "$PGDATA" /tmp/deepterminal-warm-done
"$PGBIN/initdb" -D "$PGDATA" -U postgres -A trust --no-sync >/dev/null
"$PGBIN/pg_ctl" -D "$PGDATA" -l /tmp/postgres.log -w \
  -o "-c listen_addresses=127.0.0.1 -c unix_socket_directories=/tmp -c fsync=off -c max_connections=40" start
createdb -h 127.0.0.1 -U postgres deepterminal
pg_restore -h 127.0.0.1 -U postgres -d deepterminal --no-owner --no-privileges /app/snapshot/deepterminal.dump
cd /app/backend
alembic upgrade head
uvicorn deepterminal_api.main:app --host 127.0.0.1 --port 8000 --no-access-log &
API_PID=$!
python /app/warm.py &                       # finishes on its own; not a reason to stop the container
cd /app/frontend
node node_modules/next/dist/bin/next start -H 0.0.0.0 -p "${PORT:-7860}" &
WEB_PID=$!
wait -n "$API_PID" "$WEB_PID"               # exit (and let the host restart us) only if a server stops
exit 1

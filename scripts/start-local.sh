#!/usr/bin/env bash
# Runs the whole app on this Linux/macOS machine, with no cloud account and no Docker.
# Starts a project-local PostgreSQL with pgvector (scripts/local_db.py, data in .local-postgres/),
# applies migrations, then starts the API (:8000), the worker and the web app (:5173) in the background.
# Logs: .local-run/*.log. Stop with ./scripts/stop-local.sh.
#
#   ./scripts/start-local.sh --paid-calls   # allow real Gemini/OpenAI calls with the keys in .env (costs money)
set -euo pipefail
cd "$(dirname "$0")/.."
root=$PWD
python=$root/backend/.venv/bin/python

[ -x "$python" ] && [ -d frontend/node_modules ] || { echo "Install dependencies first (README, 'Run locally on Linux')." >&2; exit 1; }
[ ! -f .local-run/pids.txt ] || { echo "Already running. Run ./scripts/stop-local.sh first." >&2; exit 1; }

DATABASE_URL=$("$python" scripts/local_db.py start)

# Local settings. They override anything in .env, which only needs your API keys and model catalog.
export APP_ENV=local DATABASE_URL
export STORAGE_DIR=$root/.local-storage
export CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
export PROVIDER_RETENTION_VERIFIED=false
[ "${1:-}" = "--paid-calls" ] && PROVIDER_RETENTION_VERIFIED=true
# No VITE_API_URL: the web app calls the API on the hostname you opened it with, so the sign-in cookie works.
export VITE_API_URL=

(cd backend && "$python" -m alembic upgrade head)

mkdir -p .local-run
: > .local-run/pids.txt
start() { # name, dir, command...
  local name=$1 dir=$2; shift 2
  cd "$dir"
  setsid "$@" > "$root/.local-run/$name.log" 2>&1 < /dev/null &  # own process group, so stop-local.sh can kill the whole tree
  echo $! >> "$root/.local-run/pids.txt"
  cd "$root"
}
start api backend "$python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000
start worker backend "$python" -m worker.main
start web frontend npx vite --host 127.0.0.1 --port 5173 --strictPort

echo "Open http://localhost:5173  (paid calls: $PROVIDER_RETENTION_VERIFIED)"
echo "Stop with ./scripts/stop-local.sh"

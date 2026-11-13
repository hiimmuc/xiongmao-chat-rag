#!/usr/bin/env bash
# Stops what start-local.sh started. The database and uploaded files are kept.
cd "$(dirname "$0")/.."
if [ -f .local-run/pids.txt ]; then
  while read -r pid; do kill -- "-$pid" 2>/dev/null || kill "$pid" 2>/dev/null || true; done < .local-run/pids.txt
  rm .local-run/pids.txt
fi
backend/.venv/bin/python scripts/local_db.py stop
echo "Stopped. Delete the .local-postgres folder to start with an empty database."

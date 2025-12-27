#!/usr/bin/env bash
set -euo pipefail

: "${HIM_ENABLED:=1}"
: "${HIM_PORT:=8000}"
: "${HIM_DATA_DIR:=/app/project_echo/data}"
: "${DATA_DIR:=/app/project_echo/data}"

# Ensure data directory exists and is writable (for SQLite and HIM)
mkdir -p "$HIM_DATA_DIR" "$DATA_DIR"
if ! touch "$DATA_DIR/sel.db" 2>/dev/null; then
  echo "[entrypoint] ERROR: cannot write to $DATA_DIR/sel.db. Check volume permissions."
  exit 1
fi

if [ "$HIM_ENABLED" != "0" ]; then
  echo "[entrypoint] starting HIM on port ${HIM_PORT} with data dir ${HIM_DATA_DIR}"
  python run_him.py --data-dir "$HIM_DATA_DIR" --host 0.0.0.0 --port "$HIM_PORT" --skip-hardware-checks &
else
  echo "[entrypoint] HIM disabled via HIM_ENABLED=0"
fi

echo "[entrypoint] starting Sel bot"
exec python -m sel_bot.main

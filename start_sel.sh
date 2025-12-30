#!/usr/bin/env bash
set -euo pipefail

# Set defaults; override via env if needed
RUN_UID=${SUDO_UID:-$(id -u)}
RUN_GID=${SUDO_GID:-$(id -g)}
RUN_USER=${SUDO_USER:-$(id -un)}
if [ -n "${SUDO_USER:-}" ] && command -v getent >/dev/null 2>&1; then
  RUN_HOME=$(getent passwd "$RUN_USER" | cut -d: -f6)
else
  RUN_HOME=$HOME
fi

HOST_UID=${HOST_UID:-$RUN_UID}
HOST_GID=${HOST_GID:-$RUN_GID}
HOST_USER=${HOST_USER:-$RUN_USER}
HOST_HOME=${HOST_HOME:-$RUN_HOME}
DBUS_SESSION_BUS_ADDRESS=${DBUS_SESSION_BUS_ADDRESS:-unix:path=/run/user/$HOST_UID/bus}
XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/$HOST_UID}
DBUS_RUNTIME_DIR=${DBUS_RUNTIME_DIR:-$XDG_RUNTIME_DIR}
HIM_PORT=${HIM_PORT:-8000}

LOG_DIR=${LOG_DIR:-/tmp/sel_logs_${RUN_UID}}
mkdir -p "$LOG_DIR"
if [ "$(id -u)" -eq 0 ]; then
  chown "$RUN_UID:$RUN_GID" "$LOG_DIR"
fi

export HOST_UID HOST_GID HOST_USER HOST_HOME
export DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR DBUS_RUNTIME_DIR HIM_PORT

echo "[start_sel] Building sel-service image"
docker-compose build sel-service

echo "[start_sel] Bringing up Sel/HIM stack (docker-compose up)"
docker-compose up

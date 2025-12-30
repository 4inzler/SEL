#!/usr/bin/env bash
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN=${PYTHON_BIN:-python3}
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Error: Python interpreter '$PYTHON_BIN' not found. Set PYTHON_BIN to a valid executable." >&2
  exit 1
fi

if ! command -v poetry >/dev/null 2>&1; then
  echo "Poetry not detected. Installing the latest stable release for the current user..."
  curl -sSL https://install.python-poetry.org | "$PYTHON_BIN" -
  export PATH="$HOME/.local/bin:$PATH"
fi

export PATH="$HOME/.local/bin:$PATH"

# Ensure Poetry uses the requested interpreter when possible.
if poetry env use "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Poetry virtual environment configured for $PYTHON_BIN."
else
  echo "Poetry env use command was not executed (environment may already exist)."
fi

echo "Installing project dependencies via Poetry..."
poetry install

DATA_DIR=${HIM_DATA_DIR:-"$PROJECT_ROOT/data"}
mkdir -p "$DATA_DIR"

# Prime the storage engine and display the system profile for visibility.
echo "\nInspecting hardware profile and verifying storage directory: $DATA_DIR"
HIM_DATA_DIR="$DATA_DIR" poetry run python run_him.py --profile-only --data-dir "$DATA_DIR"

echo "\nSetup complete. To launch the Hierarchical Image Memory API server, run:\n  poetry run python run_him.py --data-dir '$DATA_DIR'"

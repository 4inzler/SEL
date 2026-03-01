#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

if [[ -f "${ENV_FILE}" ]]; then
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  if [[ -n "${OPENROUTER_API_KEY:-}" ]]; then
    export OPENAI_API_KEY="${OPENROUTER_API_KEY}"
  fi
fi

export API_BASE_URL="${API_BASE_URL:-https://openrouter.ai/api/v1}"
export DEFAULT_MODEL="${DEFAULT_MODEL:-${OPENROUTER_MAIN_MODEL:-anthropic/claude-3-5-sonnet-20241022}}"
export OPENAI_USE_FUNCTIONS="true"
export PRETTIFY_MARKDOWN="false"
export SHELL_INTERACTION="false"
export REQUEST_TIMEOUT="${REQUEST_TIMEOUT:-30}"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "Missing API key. Set OPENAI_API_KEY or OPENROUTER_API_KEY in .env." >&2
  exit 1
fi

if [[ $# -eq 0 ]]; then
  echo "Usage: $0 \"your shell request\"" >&2
  exit 2
fi

# Tool-calling mode (no chat session mode): allows ShellGPT functions to execute.
if ! timeout "${SGPT_TIMEOUT_SECONDS:-60}" sgpt --functions --no-interaction "$*"; then
  code=$?
  if [[ "${code}" -eq 124 ]]; then
    echo "ShellGPT timed out after ${SGPT_TIMEOUT_SECONDS:-60}s." >&2
  else
    echo "ShellGPT failed (exit ${code})." >&2
  fi
  echo "Check network/DNS to openrouter.ai and verify OPENROUTER_API_KEY in .env." >&2
  exit "${code}"
fi

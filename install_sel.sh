#!/usr/bin/env bash
# Installer for Sel bot dependencies on common Linux distros.
# Detects package manager, installs Python toolchain, then installs the project in a venv.

set -euo pipefail

PKG_MANAGER=""
PKG_INSTALL=""

detect_pkg_manager() {
  if command -v apt-get >/dev/null 2>&1; then
    PKG_MANAGER="apt"
    PKG_INSTALL="sudo apt-get update && sudo apt-get install -y"
  elif command -v dnf >/dev/null 2>&1; then
    PKG_MANAGER="dnf"
    PKG_INSTALL="sudo dnf install -y"
  elif command -v yum >/dev/null 2>&1; then
    PKG_MANAGER="yum"
    PKG_INSTALL="sudo yum install -y"
  elif command -v pacman >/dev/null 2>&1; then
    PKG_MANAGER="pacman"
    PKG_INSTALL="sudo pacman -Sy --noconfirm"
  fi
}

install_system_packages() {
  case "$PKG_MANAGER" in
    apt)
      eval "$PKG_INSTALL" python3 python3-venv python3-pip build-essential libpq-dev curl git
      ;;
    dnf|yum)
      eval "$PKG_INSTALL" python3 python3-virtualenv python3-pip gcc python3-devel libpq-devel curl git
      ;;
    pacman)
      eval "$PKG_INSTALL" python python-pip python-virtualenv base-devel libpq curl git
      ;;
    *)
      echo "Unsupported or undetected package manager. Please install Python 3.11+, pip, and build tools manually."
      exit 1
      ;;
  esac
}

create_venv_and_install() {
  REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  cd "$REPO_ROOT/project_echo"

  # Create virtualenv if missing
  if [ ! -d ".venv" ]; then
    python3 -m venv .venv
  fi
  # Activate venv
  # shellcheck disable=SC1091
  source .venv/bin/activate

  python -m pip install --upgrade pip
  python -m pip install -e .
}

main() {
  detect_pkg_manager
  install_system_packages
  create_venv_and_install
  echo "✅ Sel dependencies installed. Activate with: source project_echo/.venv/bin/activate"
}

main "$@"

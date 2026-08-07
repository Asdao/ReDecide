#!/usr/bin/env bash
set -euo pipefail

# Install the two JavaScript projects from their checked-in pnpm lockfiles.
# pnpm is the authoritative package manager even if legacy npm lockfiles are
# present for external tooling.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

case "$repo_root" in
  /mnt/[a-zA-Z]/*)
    echo "error: do not install JavaScript dependencies from WSL into a Windows-mounted checkout ($repo_root)" >&2
    echo "use Windows PowerShell for this checkout, or clone the repository under the native WSL filesystem" >&2
    exit 1
    ;;
esac

if ! command -v node >/dev/null 2>&1; then
  echo "error: Node.js is required (frontend requires Node 24.x)" >&2
  exit 1
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "error: pnpm is required; install/enable pnpm 11 first" >&2
  exit 1
fi

node_major="$(node -p 'process.versions.node.split(".")[0]')"
if [[ "$node_major" != "24" ]]; then
  echo "error: frontend requires Node 24.x; found $(node --version)" >&2
  exit 1
fi

pnpm_major="$(pnpm --version | cut -d. -f1)"
if [[ "$pnpm_major" != "11" ]]; then
  echo "error: this repository requires pnpm 11.x; found $(pnpm --version)" >&2
  exit 1
fi

node "$repo_root/security/check-lockfiles.mjs"

install_project() {
  local project="$1"
  echo "Installing $project from its frozen lockfile..."
  (
    cd "$repo_root/$project"
    pnpm install --frozen-lockfile
  )
}

install_project "agent-harness"
install_project "frontend"

echo "JavaScript dependencies installed successfully."

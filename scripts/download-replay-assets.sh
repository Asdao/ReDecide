#!/usr/bin/env bash
set -euo pipefail

# Thin WSL wrapper around the canonical replay-engine downloaders.
# Raw demos require explicit --file arguments and a byte budget.

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

usage() {
  cat <<'EOF'
Usage:
  bash scripts/download-replay-assets.sh maps [download_maps options]
  bash scripts/download-replay-assets.sh metadata [download_dataset options]
  bash scripts/download-replay-assets.sh sidecars [download_dataset options]
  bash scripts/download-replay-assets.sh demos --file <repo-path> [options]

Examples:
  bash scripts/download-replay-assets.sh maps
  bash scripts/download-replay-assets.sh maps --maps de_mirage de_nuke
  bash scripts/download-replay-assets.sh metadata --max-gb 1
  bash scripts/download-replay-assets.sh sidecars --max-files 100 --max-gb 0.25
  bash scripts/download-replay-assets.sh demos \
    --file demos/shard-example/match/map.dem --max-gb 1

All paths are stored under the configured data roots:
  public assets: data/public (or CS2_PUBLIC_DATA_ROOT)
  private assets: data/private (or CS2_PRIVATE_DATA_ROOT)
EOF
}

command_name="${1:-}"
if [[ -z "$command_name" || "$command_name" == "-h" || "$command_name" == "--help" ]]; then
  usage
  exit 0
fi
shift

python_bin="${PYTHON_BIN:-$(command -v python || true)}"
if [[ -z "$python_bin" ]]; then
  echo "error: activate the project WSL virtual environment first" >&2
  echo "hint: source /home/<user>/.virtualenvs/GHackathon1/bin/activate" >&2
  exit 1
fi

case "$command_name" in
  maps)
    "$python_bin" -m backend.replay_engine.training.download_maps "$@"
    ;;
  metadata|sidecars|demos)
    "$python_bin" -m backend.replay_engine.training.download_dataset "$command_name" \
      "$@"
    ;;
  *)
    echo "error: unknown command: $command_name" >&2
    usage >&2
    exit 2
    ;;
esac

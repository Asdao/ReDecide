"""Create a reproducibility fingerprint for a model/data release."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from backend.replay_engine.training.data_paths import DATA_PATHS

DEFAULT_PATHS = (
    DATA_PATHS.private_processed / "full_replays.jsonl",
    DATA_PATHS.private_databases / "cs2_replays_v2.sqlite",
    Path("model/artifacts/releases/v2/full_replay_value.txt"),
    Path("model/artifacts/releases/v2/full_replay_value.txt.json"),
    Path("model/artifacts/releases/v2/full_replay_value.manifest.json"),
    Path("model/artifacts/releases/v2/full_replay_calibrator.json"),
    Path("model/artifacts/releases/v2/small_snapshot_value.json"),
    Path("model/artifacts/releases/v2/action_frequency.json"),
    Path("model/artifacts/releases/v2/zone_transitions.json"),
    Path("model/artifacts/releases/v2/engagement_model.json"),
    Path("model/artifacts/releases/v2/engagement_lightgbm.json"),
    Path("model/artifacts/releases/v2/feature_schema.json"),
)


def _sha256(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def fingerprint(
    paths: list[Path],
    *,
    root: Path = Path(""),
    release_version: str = "v1",
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for path in paths:
        resolved = path if path.is_absolute() else root / path
        if not resolved.is_file():
            continue
        entries.append(
            {
                "path": str(path).replace("\\", "/"),
                "bytes": resolved.stat().st_size,
                "sha256": _sha256(resolved),
            }
        )
    return {
        "release_version": release_version,
        "created_at": datetime.now(UTC).isoformat(),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "files": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/releases/v1/fingerprint.json"))
    parser.add_argument("--root", type=Path, default=Path(""))
    parser.add_argument("--version", default="v1")
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    paths = args.paths or list(DEFAULT_PATHS)
    result = fingerprint(paths, root=args.root, release_version=args.version)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"[fingerprint] files={len(result['files'])} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

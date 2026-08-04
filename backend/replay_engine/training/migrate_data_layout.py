"""Move the existing data tree into explicit public and private roots.

The migration refuses to overwrite an existing destination.  Run it first
with ``--dry-run`` and then with ``--apply``.  It records the completed moves
in ``data/public/layout_manifest.json`` so a later parity check can identify
exactly which source paths were moved.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

from backend.replay_engine.training.data_paths import DataPaths, get_data_paths


@dataclass(frozen=True, slots=True)
class Move:
    source: Path
    destination: Path
    visibility: str


def planned_moves(root: Path, paths: DataPaths) -> list[Move]:
    """Return the idempotent migration plan relative to ``root``."""

    return [
        Move(root / "data/small/metadata", paths.public_metadata, "public"),
        Move(root / "data/small/processed", paths.public_processed, "public"),
        Move(root / "data/small/sidecars", paths.private_sidecars, "private"),
        Move(root / "data/maps", paths.public_maps, "public"),
        Move(root / "data/full/demos", paths.private_raw_demos, "private"),
        Move(root / "data/full/processed/analysis_snapshots.jsonl", paths.private_processed / "analysis_snapshots.jsonl", "private"),
        Move(root / "data/full/processed/full_replays.jsonl", paths.private_processed / "full_replays.jsonl", "private"),
        Move(root / "data/full/processed/full_replays_native_test.jsonl", paths.private_processed / "full_replays_native_test.jsonl", "private"),
        Move(root / "data/full/processed/replay_audit.json", paths.private_processed / "replay_audit.json", "private"),
        Move(root / "data/full/processed/cs2_replays.sqlite", paths.private_databases / "cs2_replays.sqlite", "private"),
        Move(root / "data/full/processed/cs2_replays_v2.sqlite", paths.private_databases / "cs2_replays_v2.sqlite", "private"),
        Move(root / "data/benchmark/demos", paths.private_benchmark_cache / "demos", "private"),
        Move(root / "data/benchmark/manifest.json", paths.public_benchmark_manifest, "public"),
        Move(root / "data/benchmark/evaluation.json", paths.public_benchmark_evaluation, "public"),
    ]


def _validate_move(move: Move) -> str:
    if not move.source.exists():
        return "missing"
    if move.destination.exists():
        raise FileExistsError(
            f"refusing to overwrite migration destination: {move.destination}"
        )
    return "ready"


def migrate(root: Path, *, apply: bool, paths: DataPaths | None = None) -> list[dict[str, str]]:
    """Validate and optionally execute the non-destructive move plan."""

    configured = paths or get_data_paths()
    moves = planned_moves(root.resolve(), configured)
    statuses: list[dict[str, str]] = []
    for move in moves:
        status = _validate_move(move)
        entry = {
            "source": move.source.relative_to(root.resolve()).as_posix(),
            "destination": move.destination.as_posix(),
            "visibility": move.visibility,
            "status": status,
        }
        if status == "ready" and apply:
            move.destination.parent.mkdir(parents=True, exist_ok=True)
            move.source.rename(move.destination)
            entry["status"] = "moved"
        statuses.append(entry)

    if apply:
        _rewrite_benchmark_artifacts(configured)
        manifest_path = configured.public / "layout_manifest.json"
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "public_root": configured.public.as_posix(),
                    "private_root": configured.private.as_posix(),
                    "moves": statuses,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return statuses


def _rewrite_benchmark_artifacts(paths: DataPaths) -> None:
    """Remove machine-specific paths from the public benchmark artifacts."""

    manifest_path = paths.public_benchmark_manifest
    if manifest_path.is_file():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        payload["training_database"] = "private:databases/cs2_replays_v2.sqlite"
        for entry in payload.get("files", []):
            if isinstance(entry, dict) and isinstance(entry.get("local_path"), str):
                local = Path(entry["local_path"].replace("\\", "/"))
                if local.parts and local.parts[0] == "demos":
                    entry["local_path"] = "private:benchmark_cache/" + local.as_posix()
        manifest_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    evaluation_path = paths.public_benchmark_evaluation
    if evaluation_path.is_file():
        payload = json.loads(evaluation_path.read_text(encoding="utf-8"))
        payload["benchmark_manifest"] = paths.public_benchmark_manifest.as_posix()
        for entry in payload.get("demos", []):
            if isinstance(entry, dict):
                entry.pop("local_path", None)
        evaluation_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--apply", action="store_true", help="perform validated moves")
    args = parser.parse_args()
    statuses = migrate(args.root, apply=args.apply)
    print(json.dumps(statuses, indent=2))
    if not args.apply:
        print("dry-run only; rerun with --apply to move the files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

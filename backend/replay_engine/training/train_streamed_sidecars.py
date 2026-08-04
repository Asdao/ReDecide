"""One-command compact sidecar streaming and replay-value training.

This command streams quality-filtered sidecars into compact JSONL snapshots,
then trains the snapshot Bayesian model and event-only full replay model. Raw
sidecars are not retained unless ``--cache-dir`` is supplied.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from backend.replay_engine.training.data_paths import DATA_PATHS
from backend.replay_engine.training.stream_sidecars import select_and_stream
from backend.replay_engine.training.train_full_replay import train as train_full_replay
from backend.replay_engine.training.train_snapshot_model import train as train_snapshot_model


def train_from_stream(
    *,
    metadata_dir: str | Path = DATA_PATHS.public_metadata,
    snapshot_output: str | Path = DATA_PATHS.private_processed / "analysis_snapshots.jsonl",
    release_dir: str | Path = Path("backend/replay_engine/model/artifacts/releases/v3"),
    cache_dir: str | Path | None = None,
    max_files: int | None = 500,
    max_bytes: int = 250_000_000,
    min_rounds: int = 16,
    min_kills: int = 80,
    min_stars: int = 0,
    decision_window_seconds: float = 5.0,
    seed: int = 7,
    validation_fraction: float = 0.2,
    release_version: str | None = None,
    tick_rate: float | None = None,
) -> dict[str, Any]:
    """Stream sidecars and train both replay-value artifacts."""

    snapshot_path = Path(snapshot_output)
    release = Path(release_dir)
    release.mkdir(parents=True, exist_ok=True)
    stream_result = select_and_stream(
        metadata_dir,
        snapshot_path,
        max_files=max_files,
        max_bytes=max_bytes,
        min_rounds=min_rounds,
        min_kills=min_kills,
        min_stars=min_stars,
        cache_dir=cache_dir,
        decision_window_seconds=decision_window_seconds,
    )
    small_model = release / "small_snapshot_value.json"
    small_metrics = release / "small_snapshot_metrics.json"
    full_model = release / "full_replay_value.txt"
    full_metrics = release / "full_replay_metrics.json"
    calibrator = release / "full_replay_calibrator.json"
    manifest = release / "full_replay_value.manifest.json"

    train_snapshot_model(snapshot_path, small_model, small_metrics, seed)
    train_full_replay(
        None,
        full_model,
        full_metrics,
        snapshot_input=snapshot_path,
        sample_every=1,
        decision_window_seconds=decision_window_seconds,
        small_model_path=small_model,
        small_model_output=small_model,
        calibrator_path=calibrator,
        manifest_path=manifest,
        allow_event_only=False,
        seed=seed,
        validation_fraction=validation_fraction,
        verbose=True,
        release_version=release_version or release.name,
        tick_rate=tick_rate,
    )
    return {
        "stream": stream_result,
        "release_dir": str(release),
        "small_model": str(small_model),
        "small_metrics": str(small_metrics),
        "full_model": str(full_model),
        "full_metrics": str(full_metrics),
        "calibrator": str(calibrator) if calibrator.is_file() else None,
        "manifest": str(manifest),
        "note": (
            "This sidecar mode trains replay-value models only. Movement and "
            "candidate-action models require native positional replay data."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DATA_PATHS.public_metadata)
    parser.add_argument(
        "--snapshot-output",
        type=Path,
        default=DATA_PATHS.private_processed / "analysis_snapshots.jsonl",
    )
    parser.add_argument(
        "--release-dir",
        type=Path,
        default=Path("backend/replay_engine/model/artifacts/releases/v3"),
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--max-gb", type=float, default=0.25)
    parser.add_argument("--min-rounds", type=int, default=16)
    parser.add_argument("--min-kills", type=int, default=80)
    parser.add_argument("--min-stars", type=int, default=0)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument(
        "--release-version",
        default=None,
        help="release identity recorded in all generated replay artifacts",
    )
    parser.add_argument(
        "--tick-rate",
        type=float,
        default=None,
        help="override tick-rate metadata (otherwise infer it from sidecars)",
    )
    args = parser.parse_args()
    if args.max_gb <= 0:
        raise ValueError("--max-gb must be positive")
    result = train_from_stream(
        metadata_dir=args.metadata,
        snapshot_output=args.snapshot_output,
        release_dir=args.release_dir,
        cache_dir=args.cache_dir,
        max_files=args.max_files,
        max_bytes=int(args.max_gb * 1_000_000_000),
        min_rounds=args.min_rounds,
        min_kills=args.min_kills,
        min_stars=args.min_stars,
        decision_window_seconds=args.decision_window_seconds,
        seed=args.seed,
        validation_fraction=args.validation_fraction,
        release_version=args.release_version,
        tick_rate=args.tick_rate,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["train_from_stream"]

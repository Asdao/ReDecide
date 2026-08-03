"""Train the full LightGBM replay-value model from parsed JSONL records."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from cs2_sim.core.model import ReplayValueEnsemble, SnapshotValueModel
from training.full_features import (
    FULL_FEATURE_NAMES,
    record_to_event_rows,
    record_to_rows,
    snapshot_to_event_row,
)
from training.metrics import binary_probability_metrics
from training.replay_repository import ReplayRepository
from training.calibration import PlattCalibrator


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _first_round_indices(rows: list[dict[str, Any]]) -> list[int]:
    """Return the earliest decision row for each demo round."""

    first: dict[tuple[str, int], int] = {}
    for index, row in enumerate(rows):
        key = (str(row.get("source") or "unknown"), int(row.get("round_num") or 0))
        previous = first.get(key)
        if previous is None or int(row.get("tick") or 0) < int(rows[previous].get("tick") or 0):
            first[key] = index
    return list(first.values())


def train(
    input_path: Path | None,
    output_path: Path,
    metrics_path: Path,
    *,
    database_path: Path | None = None,
    calibrator_path: Path | None = None,
    manifest_path: Path | None = None,
    snapshot_input: Path | None,
    sample_every: int,
    decision_window_seconds: float,
    small_model_path: Path | None,
    allow_event_only: bool,
    seed: int,
) -> None:
    rows: list[dict[str, Any]] = []
    event_only_rows = 0
    if database_path is not None and snapshot_input is not None:
        raise ValueError("database_path and snapshot_input are mutually exclusive")
    source_path = database_path or snapshot_input or input_path
    if database_path is not None:
        with ReplayRepository(database_path) as repository:
            rows = list(repository.iter_snapshot_rows(include_terminal=False))
    elif snapshot_input is not None:
        snapshots = _read_records(snapshot_input)
        rows = [
            snapshot_to_event_row(snapshot)
            for snapshot in snapshots
            if snapshot.get("label_round_winner") in {"ct", "t"}
        ]
        event_only_rows = len(rows)
    else:
        if input_path is None:
            raise ValueError("input_path is required when database_path is not provided")
        records = _read_records(input_path)
        for record in records:
            parsed_rows = record_to_rows(
                record,
                sample_every=sample_every,
                decision_window_seconds=decision_window_seconds,
                include_terminal=False,
            )
            if not parsed_rows and allow_event_only:
                parsed_rows = record_to_event_rows(
                    record,
                    decision_window_seconds=decision_window_seconds,
                    include_terminal=False,
                )
                event_only_rows += len(parsed_rows)
            rows.extend(parsed_rows)
    if not rows:
        raise ValueError(
            "no positional tick rows found; run parse_demos on a machine where "
            "Awpy/PyArrow native parsing works, or pass --allow-event-only"
        )
    sources = sorted({str(row["source"]) for row in rows})
    random.Random(seed).shuffle(sources)
    validation_sources = set(sources[-max(1, len(sources) // 5) :])
    train_rows = [row for row in rows if row["source"] not in validation_sources]
    validation_rows = [row for row in rows if row["source"] in validation_sources]
    if not train_rows or not validation_rows:
        raise ValueError("need at least two demos for a demo-separated split")

    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("install the full dependencies with `pip install .[full]`") from exc

    train_matrix = np.asarray(
        [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in train_rows],
        dtype=float,
    )
    train_labels = np.asarray([row["label_ct_win"] for row in train_rows], dtype=int)
    validation_matrix = np.asarray(
        [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in validation_rows],
        dtype=float,
    )
    validation_labels = np.asarray([row["label_ct_win"] for row in validation_rows], dtype=int)
    round_counts: dict[tuple[str, int], int] = {}
    for row in train_rows:
        key = (str(row["source"]), int(row.get("round_num") or 0))
        round_counts[key] = round_counts.get(key, 0) + 1
    train_weights = np.asarray(
        [1.0 / round_counts[(str(row["source"]), int(row.get("round_num") or 0))] for row in train_rows],
        dtype=float,
    )
    if len(set(train_labels.tolist())) < 2:
        raise ValueError("training rows contain only one outcome class")
    train_set = lgb.Dataset(
        train_matrix,
        label=train_labels,
        weight=train_weights,
        feature_name=list(FULL_FEATURE_NAMES),
    )
    valid_set = lgb.Dataset(
        validation_matrix,
        label=validation_labels,
        reference=train_set,
        feature_name=list(FULL_FEATURE_NAMES),
    )
    parameters = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.05,
        "num_leaves": 15,
        "max_bin": 63,
        "min_data_in_leaf": 20,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "verbosity": -1,
        "seed": seed,
        "feature_fraction_seed": seed,
        "bagging_seed": seed,
    }
    booster = lgb.train(
        parameters,
        train_set,
        num_boost_round=200,
        valid_sets=[valid_set],
        valid_names=["validation"],
        callbacks=[lgb.early_stopping(30, verbose=False)],
    )
    raw_probabilities = booster.predict(validation_matrix).tolist()
    probabilities = raw_probabilities
    small = None
    if small_model_path is not None and small_model_path.exists():
        # Build a split-safe Bayesian blend for evaluation.  Loading the final
        # all-data artifact here would leak validation demo outcomes.
        small = SnapshotValueModel()
        for row in train_rows:
            snapshot = dict(row["snapshot"])
            snapshot["label_round_winner"] = "ct" if row["label_ct_win"] else "t"
            small.observe(snapshot)
        prior = [small.predict_ct_win(row["snapshot"]) for row in validation_rows]
        probabilities = [0.8 * full + 0.2 * prior for full, prior in zip(raw_probabilities, prior, strict=True)]
    baseline_probability = float(train_labels.mean())
    validation_metrics = binary_probability_metrics(
        probabilities,
        validation_labels.tolist(),
        baseline_probability=baseline_probability,
    )
    round_indices = _first_round_indices(validation_rows)
    round_metrics = binary_probability_metrics(
        [probabilities[index] for index in round_indices],
        [int(validation_labels[index]) for index in round_indices],
        baseline_probability=baseline_probability,
    )
    calibrator = None
    calibrated_metrics = None
    if calibrator_path is not None and len(set(validation_labels.tolist())) >= 2:
        calibrator = PlattCalibrator().fit(probabilities, validation_labels.tolist())
        calibrated_metrics = binary_probability_metrics(
            calibrator.predict(probabilities),
            validation_labels.tolist(),
            baseline_probability=baseline_probability,
        )

    # Retrain the deployable booster on all rows using the iteration count
    # selected without touching validation during evaluation.
    all_matrix = np.asarray(
        [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in rows],
        dtype=float,
    )
    all_labels = np.asarray([row["label_ct_win"] for row in rows], dtype=int)
    all_round_counts: dict[tuple[str, int], int] = {}
    for row in rows:
        key = (str(row["source"]), int(row.get("round_num") or 0))
        all_round_counts[key] = all_round_counts.get(key, 0) + 1
    all_weights = np.asarray(
        [1.0 / all_round_counts[(str(row["source"]), int(row.get("round_num") or 0))] for row in rows],
        dtype=float,
    )
    final_set = lgb.Dataset(
        all_matrix,
        label=all_labels,
        weight=all_weights,
        feature_name=list(FULL_FEATURE_NAMES),
    )
    best_iteration = booster.best_iteration or 200
    final_booster = lgb.train(parameters, final_set, num_boost_round=best_iteration)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    final_booster.save_model(str(output_path))
    output_path.with_suffix(output_path.suffix + ".json").write_text(
        json.dumps(
            {
                "version": 1,
                "feature_names": list(FULL_FEATURE_NAMES),
                "small_model_blend": 0.2 if small is not None else 0.0,
                "training_mode": "sqlite" if database_path is not None else ("event_only" if event_only_rows else "positional_ticks"),
                "event_only_rows": event_only_rows,
                "decision_window_seconds": decision_window_seconds,
                "training_rows": len(rows),
                "boosting_rounds": best_iteration,
                "weighting": "equal_total_weight_per_replay_round",
                "calibrator": str(calibrator_path) if calibrator is not None else None,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(
            {
                "source": str(source_path),
                "train_rows": len(train_rows),
                "validation_rows": len(validation_rows),
                "validation_sources": sorted(validation_sources),
                "feature_names": list(FULL_FEATURE_NAMES),
                "small_model_blend": 0.2 if small is not None else 0.0,
                "training_mode": "sqlite" if database_path is not None else ("event_only" if event_only_rows else "positional_ticks"),
                "database": str(database_path) if database_path is not None else None,
                "event_only_rows": event_only_rows,
                "decision_window_seconds": decision_window_seconds,
                "artifact_training_rows": len(rows),
                "boosting_rounds": best_iteration,
                "weighting": "equal_total_weight_per_replay_round",
                "snapshot_metrics": validation_metrics,
                "round_metrics": round_metrics,
                "calibrated_snapshot_metrics": calibrated_metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if calibrator is not None and calibrator_path is not None:
        calibrator_path.parent.mkdir(parents=True, exist_ok=True)
        calibrator_path.write_text(json.dumps(calibrator.to_dict(), indent=2), encoding="utf-8")
    if manifest_path is not None:
        ReplayValueEnsemble(booster_weight=0.8 if small is not None else 1.0).save_manifest(
            manifest_path,
            booster_path=output_path,
            bayesian_path=small_model_path if small is not None else None,
            calibrator_path=calibrator_path if calibrator is not None else None,
        )
    print(f"[full] rows={len(rows)} train={len(train_rows)} validation={len(validation_rows)}")
    print(f"[full] saved {output_path}")
    print(f"[full] validation {json.dumps(validation_metrics, sort_keys=True)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/full_replays.jsonl"))
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="read leakage-safe rows directly from the canonical SQLite database",
    )
    parser.add_argument(
        "--snapshot-input",
        type=Path,
        default=None,
        help="train event-only LightGBM directly from leakage-safe snapshot JSONL",
    )
    parser.add_argument("--output", type=Path, default=Path("models/full_replay_value.txt"))
    parser.add_argument("--metrics", type=Path, default=Path("models/full_replay_metrics.json"))
    parser.add_argument("--calibrator", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    parser.add_argument("--small-model", type=Path, default=Path("models/small_snapshot_value.json"))
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--allow-event-only",
        action="store_true",
        help="train a provisional round-value model without positional ticks",
    )
    args = parser.parse_args()
    database_path = args.database
    default_database = Path("data/full/processed/cs2_replays.sqlite")
    if database_path is None and default_database.exists() and args.snapshot_input is None:
        database_path = default_database
    train(
        args.input,
        args.output,
        args.metrics,
        database_path=database_path,
        calibrator_path=args.calibrator,
        manifest_path=args.manifest,
        snapshot_input=args.snapshot_input,
        sample_every=args.sample_every,
        decision_window_seconds=args.decision_window_seconds,
        small_model_path=args.small_model,
        allow_event_only=args.allow_event_only,
        seed=args.seed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

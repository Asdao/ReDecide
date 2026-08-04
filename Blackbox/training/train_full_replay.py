"""Train the full LightGBM replay-value model from parsed JSONL records."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from cs2_sim.core.model import ReplayValueEnsemble, SnapshotValueModel

from Blackbox.training.calibration import PlattCalibrator
from Blackbox.training.data_paths import DATA_PATHS
from Blackbox.training.dataset_split import evaluation_metadata, group_id, grouped_split
from Blackbox.training.full_features import (
    FEATURE_SCHEMA_VERSION,
    FULL_FEATURE_NAMES,
    record_to_event_rows,
    record_to_rows,
    snapshot_to_event_row,
)
from Blackbox.training.metrics import binary_probability_metrics
from Blackbox.training.replay_repository import ReplayRepository

DEFAULT_TICK_RATE = 64.0


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _first_round_indices(rows: list[dict[str, Any]]) -> list[int]:
    """Return the earliest decision row for each demo round."""

    first: dict[tuple[str, int], int] = {}
    for index, row in enumerate(rows):
        key = (group_id(row, index=index), int(row.get("round_num") or 0))
        previous = first.get(key)
        if previous is None or int(row.get("tick") or 0) < int(rows[previous].get("tick") or 0):
            first[key] = index
    return list(first.values())


def _snapshot_for_model(row: dict[str, Any]) -> dict[str, Any]:
    """Return a labelled snapshot suitable for ``SnapshotValueModel``."""

    snapshot = dict(row["snapshot"])
    snapshot["label_round_winner"] = "ct" if row["label_ct_win"] else "t"
    return snapshot


def _fit_snapshot_model(rows: list[dict[str, Any]]) -> SnapshotValueModel:
    """Fit a Bayesian snapshot model without writing an artifact."""

    model = SnapshotValueModel()
    for row in rows:
        model.observe(_snapshot_for_model(row))
    return model


def _load_or_fit_snapshot_model(
    rows: list[dict[str, Any]],
    *,
    small_model_path: Path | None,
    small_model_output: Path | None,
) -> tuple[SnapshotValueModel, Path | None, str]:
    """Resolve the deployable Bayesian model and its artifact path.

    ``small_model_path`` is intentionally an input to the trainer.  When it
    already exists, it is loaded and never overwritten; this is what allows
    the streamed workflow to train the Bayesian artifact once and then reuse
    it while fitting LightGBM.  If no existing artifact is available, the
    model is fitted from ``rows`` and written only when
    ``small_model_output`` is supplied.
    """

    source_path = Path(small_model_path) if small_model_path is not None else None
    if source_path is not None and source_path.is_file():
        return SnapshotValueModel.load(source_path), source_path, "loaded"

    model = _fit_snapshot_model(rows)
    output_path = Path(small_model_output) if small_model_output is not None else None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        model.save(output_path)
    return model, output_path, "trained"


def _positive_float(value: Any, *, name: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive number") from exc
    if not math.isfinite(converted) or converted <= 0:
        raise ValueError(f"{name} must be a positive number")
    return converted


def _resolve_tick_rate(
    configured: float | None,
    candidates: list[Any],
    rows: list[dict[str, Any]],
) -> float:
    """Resolve tick metadata from an explicit value or the input dataset."""

    explicit = _positive_float(configured, name="tick_rate")
    if explicit is not None:
        return explicit
    values: list[float] = []
    for value in candidates:
        try:
            converted = _positive_float(value, name="tick_rate")
        except ValueError:
            converted = None
        if converted is not None:
            values.append(converted)
    for row in rows:
        snapshot = row.get("snapshot")
        if isinstance(snapshot, dict):
            try:
                converted = _positive_float(snapshot.get("tick_rate"), name="tick_rate")
            except ValueError:
                converted = None
            if converted is not None:
                values.append(converted)
    if not values:
        return DEFAULT_TICK_RATE
    # Mixed-rate datasets are possible.  Report the dominant rate rather than
    # silently retaining the historical hard-coded 64 Hz value.
    rounded = [round(value, 6) for value in values]
    return float(Counter(rounded).most_common(1)[0][0])


def _resolve_release_version(
    configured: str | None,
    *,
    output_path: Path,
    manifest_path: Path | None,
) -> str:
    """Resolve one release identity for every generated artifact."""

    if configured is not None:
        value = str(configured).strip()
        if not value:
            raise ValueError("release_version must not be empty")
        return value
    parent = (manifest_path or output_path).parent.name
    return parent or "unversioned"


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
    validation_fraction: float = 0.2,
    small_model_output: Path | None = None,
    verbose: bool = True,
    release_version: str | None = None,
    tick_rate: float | None = None,
) -> None:
    rows: list[dict[str, Any]] = []
    event_only_rows = 0
    tick_rate_candidates: list[Any] = []
    if database_path is not None and snapshot_input is not None:
        raise ValueError("database_path and snapshot_input are mutually exclusive")
    source_path = database_path or snapshot_input or input_path
    if database_path is not None:
        with ReplayRepository(database_path) as repository:
            dataset_metadata = repository.metadata()
            tick_rate_candidates.append(dataset_metadata.get("default_tick_rate"))
            rows = list(repository.iter_snapshot_rows(include_terminal=False))
    elif snapshot_input is not None:
        snapshots = _read_records(snapshot_input)
        tick_rate_candidates.extend(snapshot.get("tick_rate") for snapshot in snapshots)
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
            header = record.get("header")
            if isinstance(header, dict):
                tick_rate_candidates.append(header.get("tick_rate"))
            tick_rate_candidates.append(record.get("tick_rate"))
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
    resolved_tick_rate = _resolve_tick_rate(tick_rate, tick_rate_candidates, rows)
    resolved_release_version = _resolve_release_version(
        release_version,
        output_path=output_path,
        manifest_path=manifest_path,
    )
    development_rows, test_rows, outer_split = grouped_split(
        rows,
        validation_fraction=validation_fraction,
        seed=seed,
    )
    tuning_pool, calibration_rows, _calibration_split = grouped_split(
        development_rows,
        validation_fraction=0.2,
        seed=seed + 1,
    )
    train_rows, tuning_rows, _tuning_split = grouped_split(
        tuning_pool,
        validation_fraction=0.2,
        seed=seed + 2,
    )
    if not train_rows or not tuning_rows or not calibration_rows or not test_rows:
        raise ValueError("need enough match/source groups for train, tuning, calibration and test splits")

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
    tuning_matrix = np.asarray(
        [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in tuning_rows],
        dtype=float,
    )
    tuning_labels = np.asarray([row["label_ct_win"] for row in tuning_rows], dtype=int)
    round_counts: dict[tuple[str, int], int] = {}
    for row in train_rows:
        key = (group_id(row), int(row.get("round_num") or 0))
        round_counts[key] = round_counts.get(key, 0) + 1
    train_weights = np.asarray(
        [1.0 / round_counts[(group_id(row), int(row.get("round_num") or 0))] for row in train_rows],
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
        tuning_matrix,
        label=tuning_labels,
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
    # Fit the calibration input only on rows not used by this initial booster.
    # Keep calibration leakage-safe by fitting this prior only on the inner
    # training split.  The deployable Bayesian artifact is resolved below and
    # may have been produced by the streamed snapshot workflow.
    small_train = _fit_snapshot_model(train_rows)
    calibration_booster = booster.predict(
        np.asarray(
            [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in calibration_rows],
            dtype=float,
        )
    ).tolist()
    calibration_prior = [small_train.predict_ct_win(row["snapshot"]) for row in calibration_rows]
    calibration_probabilities = [
        0.8 * full + 0.2 * prior
        for full, prior in zip(calibration_booster, calibration_prior, strict=True)
    ]
    calibrator = None
    if calibrator_path is not None and len({int(row["label_ct_win"]) for row in calibration_rows}) >= 2:
        calibrator = PlattCalibrator().fit(
            calibration_probabilities,
            [int(row["label_ct_win"]) for row in calibration_rows],
        )

    # The deployable artifacts are trained on development groups only; the
    # final test groups remain untouched until metrics are computed below.
    dev_rows = development_rows
    all_matrix = np.asarray(
        [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in dev_rows],
        dtype=float,
    )
    all_labels = np.asarray([row["label_ct_win"] for row in dev_rows], dtype=int)
    all_round_counts: dict[tuple[str, int], int] = {}
    for row in dev_rows:
        key = (group_id(row), int(row.get("round_num") or 0))
        all_round_counts[key] = all_round_counts.get(key, 0) + 1
    all_weights = np.asarray(
        [1.0 / all_round_counts[(group_id(row), int(row.get("round_num") or 0))] for row in dev_rows],
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
    small, small_artifact_path, small_artifact_source = _load_or_fit_snapshot_model(
        dev_rows,
        small_model_path=small_model_path,
        small_model_output=small_model_output,
    )
    # If a pre-trained deployment artifact was supplied, do not use its
    # all-row counts for held-out metrics.  Build an in-memory evaluation prior
    # from development groups while retaining the loaded model for deployment.
    evaluation_small = (
        _fit_snapshot_model(dev_rows)
        if small_artifact_source == "loaded"
        else small
    )

    test_matrix = np.asarray(
        [[row["features"][name] for name in FULL_FEATURE_NAMES] for row in test_rows],
        dtype=float,
    )
    raw_test_probabilities = final_booster.predict(test_matrix).tolist()
    test_prior = [evaluation_small.predict_ct_win(row["snapshot"]) for row in test_rows]
    probabilities = [
        0.8 * full + 0.2 * prior
        for full, prior in zip(raw_test_probabilities, test_prior, strict=True)
    ]
    baseline_probability = float(all_labels.mean())
    test_labels = [int(row["label_ct_win"]) for row in test_rows]
    validation_metrics = binary_probability_metrics(
        probabilities,
        test_labels,
        baseline_probability=baseline_probability,
    )
    round_indices = _first_round_indices(test_rows)
    round_metrics = binary_probability_metrics(
        [probabilities[index] for index in round_indices],
        [test_labels[index] for index in round_indices],
        baseline_probability=baseline_probability,
    )
    calibrated_metrics = None
    if calibrator is not None:
        calibrated_metrics = binary_probability_metrics(
            calibrator.predict(probabilities),
            test_labels,
            baseline_probability=baseline_probability,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    final_booster.save_model(str(output_path))
    artifact_metadata = {
        "version": 2,
        "release_version": resolved_release_version,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_names": list(FULL_FEATURE_NAMES),
        "small_model_blend": 0.2 if small is not None else 0.0,
        "training_mode": "sqlite" if database_path is not None else ("event_only" if event_only_rows else "positional_ticks"),
        "event_only_rows": event_only_rows,
        "decision_window_seconds": decision_window_seconds,
        "tick_rate": resolved_tick_rate,
        "training_rows": len(dev_rows),
        "test_rows": len(test_rows),
        "boosting_rounds": best_iteration,
        "weighting": "equal_total_weight_per_replay_round",
        "calibrator": str(calibrator_path) if calibrator is not None else None,
        "small_model_path": str(small_artifact_path) if small_artifact_path is not None else None,
        "small_model_source": small_artifact_source,
        "evaluation_small_model_source": "development_split",
    }
    output_path.with_suffix(output_path.suffix + ".json").write_text(
        json.dumps(
            artifact_metadata,
            indent=2,
        ),
        encoding="utf-8",
    )
    metadata = evaluation_metadata(
        rows,
        train_rows=dev_rows,
        validation_rows=test_rows,
        feature_schema_version=str(FEATURE_SCHEMA_VERSION),
        seed=seed,
        validation_fraction=validation_fraction,
    )
    metrics_report = {
        "source": str(source_path),
        "train_rows": len(dev_rows),
        "test_rows": len(test_rows),
        "test_groups": outer_split["validation_groups"],
        "feature_names": list(FULL_FEATURE_NAMES),
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "small_model_blend": 0.2 if small is not None else 0.0,
        "training_mode": "sqlite" if database_path is not None else ("event_only" if event_only_rows else "positional_ticks"),
        "database": str(database_path) if database_path is not None else None,
        "event_only_rows": event_only_rows,
        "decision_window_seconds": decision_window_seconds,
        "tick_rate": resolved_tick_rate,
        "release_version": resolved_release_version,
        "artifact_training_rows": len(dev_rows),
        "boosting_rounds": best_iteration,
        "weighting": "equal_total_weight_per_replay_round",
        "training_prior": baseline_probability,
        "snapshot_metrics": validation_metrics,
        "round_metrics": round_metrics,
        "calibrated_snapshot_metrics": calibrated_metrics,
        "small_model_path": str(small_artifact_path) if small_artifact_path is not None else None,
        "small_model_source": small_artifact_source,
        "evaluation_small_model_source": "development_split",
        "metadata": metadata,
    }
    metrics_path.write_text(json.dumps(metrics_report, indent=2), encoding="utf-8")
    if calibrator is not None and calibrator_path is not None:
        calibrator_path.parent.mkdir(parents=True, exist_ok=True)
        calibrator_path.write_text(json.dumps(calibrator.to_dict(), indent=2), encoding="utf-8")
    if manifest_path is not None:
        if small_artifact_path is None:
            raise ValueError(
                "deployment manifest requires an existing --small-model path or "
                "--small-model-output so calibration matches the Bayesian artifact"
            )
        ReplayValueEnsemble(booster_weight=0.8 if small is not None else 1.0).save_manifest(
            manifest_path,
            booster_path=output_path,
            bayesian_path=small_artifact_path,
            calibrator_path=calibrator_path if calibrator is not None else None,
        )
        manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_payload.update(
            {
                "release_version": resolved_release_version,
                "deployed_model": "lightgbm+bayesian",
                "baseline_role": "advisory_only",
                "feature_schema_version": FEATURE_SCHEMA_VERSION,
                "tick_rate": resolved_tick_rate,
                "training_prior": baseline_probability,
                "dataset_fingerprint": metadata["dataset_fingerprint"],
                "split_fingerprint": metadata["split_fingerprint"],
            }
        )
        manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")
    if verbose:
        print(f"[full] rows={len(rows)} train={len(dev_rows)} test={len(test_rows)}")
        print(f"[full] saved {output_path}")
        print(f"[full] held-out test {json.dumps(validation_metrics, sort_keys=True)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "full_replays.jsonl")
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
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/full_replay_value.txt"))
    parser.add_argument("--metrics", type=Path, default=Path("model/artifacts/full_replay_metrics.json"))
    parser.add_argument("--calibrator", type=Path, default=None)
    parser.add_argument("--manifest", type=Path, default=None)
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    parser.add_argument(
        "--small-model",
        type=Path,
        default=Path("model/artifacts/small_snapshot_value.json"),
        help="reuse an existing Bayesian artifact when present",
    )
    parser.add_argument("--small-model-output", type=Path, default=None)
    parser.add_argument(
        "--release-version",
        default=None,
        help="release identity recorded in artifact, metrics, and replay manifest",
    )
    parser.add_argument(
        "--tick-rate",
        type=float,
        default=None,
        help="override tick-rate metadata (otherwise infer it from the input)",
    )
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--allow-event-only",
        action="store_true",
        help="train a provisional round-value model without positional ticks",
    )
    args = parser.parse_args()
    database_path = args.database
    default_database = DATA_PATHS.private_databases / "cs2_replays.sqlite"
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
        validation_fraction=args.validation_fraction,
        small_model_output=args.small_model_output,
        release_version=args.release_version,
        tick_rate=args.tick_rate,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

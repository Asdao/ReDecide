"""Train the full LightGBM replay-value model from parsed JSONL records."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from cs2_sim.models import SnapshotValueModel
from training.full_features import FULL_FEATURE_NAMES, record_to_event_rows, record_to_rows


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _metrics(probabilities: list[float], labels: list[int]) -> dict[str, float]:
    eps = 1e-7
    log_loss = -sum(
        label * math.log(max(eps, probability))
        + (1 - label) * math.log(max(eps, 1 - probability))
        for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    brier = sum(
        (probability - label) ** 2
        for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    accuracy = sum(
        (probability >= 0.5) == bool(label)
        for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    return {"log_loss": log_loss, "brier": brier, "accuracy": accuracy}


def train(
    input_path: Path,
    output_path: Path,
    metrics_path: Path,
    *,
    sample_every: int,
    small_model_path: Path | None,
    allow_event_only: bool,
) -> None:
    records = _read_records(input_path)
    rows: list[dict[str, Any]] = []
    event_only_rows = 0
    for record in records:
        parsed_rows = record_to_rows(record, sample_every=sample_every)
        if not parsed_rows and allow_event_only:
            parsed_rows = record_to_event_rows(record)
            event_only_rows += len(parsed_rows)
        rows.extend(parsed_rows)
    if not rows:
        raise ValueError(
            "no positional tick rows found; run parse_demos on a machine where "
            "Awpy/PyArrow native parsing works, or pass --allow-event-only"
        )
    sources = sorted({str(row["source"]) for row in rows})
    validation_source = sources[-1]
    train_rows = [row for row in rows if row["source"] != validation_source]
    validation_rows = [row for row in rows if row["source"] == validation_source]
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
    if len(set(train_labels.tolist())) < 2:
        raise ValueError("training rows contain only one outcome class")
    train_set = lgb.Dataset(train_matrix, label=train_labels, feature_name=list(FULL_FEATURE_NAMES))
    valid_set = lgb.Dataset(
        validation_matrix,
        label=validation_labels,
        reference=train_set,
        feature_name=list(FULL_FEATURE_NAMES),
    )
    booster = lgb.train(
        {
            "objective": "binary",
            "metric": "binary_logloss",
            "learning_rate": 0.05,
            "num_leaves": 15,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 1,
            "verbosity": -1,
            "seed": 7,
        },
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
        small = SnapshotValueModel.load(small_model_path)
        prior = [small.predict_ct_win(row["snapshot"]) for row in validation_rows]
        probabilities = [0.8 * full + 0.2 * prior for full, prior in zip(raw_probabilities, prior, strict=True)]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(output_path))
    output_path.with_suffix(output_path.suffix + ".json").write_text(
        json.dumps(
            {
                "version": 1,
                "feature_names": list(FULL_FEATURE_NAMES),
                "small_model_blend": 0.2 if small is not None else 0.0,
                "training_mode": "event_only" if event_only_rows else "positional_ticks",
                "event_only_rows": event_only_rows,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metrics_path.write_text(
        json.dumps(
            {
                "source": str(input_path),
                "train_rows": len(train_rows),
                "validation_rows": len(validation_rows),
                "validation_source": validation_source,
                "feature_names": list(FULL_FEATURE_NAMES),
                "small_model_blend": 0.2 if small is not None else 0.0,
                "training_mode": "event_only" if event_only_rows else "positional_ticks",
                "event_only_rows": event_only_rows,
                "metrics": _metrics(probabilities, validation_labels.tolist()),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[full] rows={len(rows)} train={len(train_rows)} validation={len(validation_rows)}")
    print(f"[full] saved {output_path}")
    print(f"[full] validation {json.dumps(_metrics(probabilities, validation_labels.tolist()), sort_keys=True)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/full_replays.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("models/full_replay_value.txt"))
    parser.add_argument("--metrics", type=Path, default=Path("models/full_replay_metrics.json"))
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--small-model", type=Path, default=Path("models/small_snapshot_value.json"))
    parser.add_argument(
        "--allow-event-only",
        action="store_true",
        help="train a provisional round-value model without positional ticks",
    )
    args = parser.parse_args()
    train(
        args.input,
        args.output,
        args.metrics,
        sample_every=args.sample_every,
        small_model_path=args.small_model,
        allow_event_only=args.allow_event_only,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

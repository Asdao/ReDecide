"""Train lightweight Gaussian and logistic replay-value baselines."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from training.full_features import FULL_FEATURE_NAMES, record_to_rows
from training.metrics import binary_probability_metrics
from training.replay_repository import ReplayRepository
from training.statistical_baselines import GaussianNaiveBayes, LogisticBaseline


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _load_rows(input_path: Path | None, database_path: Path | None, *, sample_every: int) -> list[dict[str, Any]]:
    if database_path is not None:
        with ReplayRepository(database_path) as repository:
            return list(repository.iter_snapshot_rows(include_terminal=False))
    if input_path is None:
        raise ValueError("input_path is required when database_path is not provided")
    rows: list[dict[str, Any]] = []
    for record in _read_records(input_path):
        rows.extend(record_to_rows(record, sample_every=sample_every, include_terminal=False))
    return rows


def _first_round_indices(rows: list[dict[str, Any]]) -> list[int]:
    first: dict[tuple[str, int], int] = {}
    for index, row in enumerate(rows):
        key = (str(row.get("source") or "unknown"), int(row.get("round_num") or 0))
        if key not in first or int(row.get("tick") or 0) < int(rows[first[key]].get("tick") or 0):
            first[key] = index
    return list(first.values())


def train_baselines(
    *,
    input_path: Path | None,
    database_path: Path | None,
    output_path: Path,
    metrics_path: Path,
    sample_every: int = 4,
    seed: int = 7,
    max_rows: int | None = None,
) -> dict[str, Any]:
    rows = _load_rows(input_path, database_path, sample_every=sample_every)
    if max_rows is not None:
        if max_rows <= 0:
            raise ValueError("max_rows must be positive")
        rows = rows[:max_rows]
    if not rows:
        raise ValueError("no labelled replay rows found")
    sources = sorted({str(row.get("source") or "unknown") for row in rows})
    random.Random(seed).shuffle(sources)
    validation_sources = set(sources[-max(1, len(sources) // 5) :])
    train_rows = [row for row in rows if str(row.get("source") or "unknown") not in validation_sources]
    validation_rows = [row for row in rows if str(row.get("source") or "unknown") in validation_sources]
    if not train_rows or not validation_rows:
        raise ValueError("need at least two replay sources for a grouped split")
    train_features = [[float(row["features"][name]) for name in FULL_FEATURE_NAMES] for row in train_rows]
    validation_features = [[float(row["features"][name]) for name in FULL_FEATURE_NAMES] for row in validation_rows]
    train_labels = [int(row["label_ct_win"]) for row in train_rows]
    validation_labels = [int(row["label_ct_win"]) for row in validation_rows]
    models = {
        "gaussian_naive_bayes": GaussianNaiveBayes().fit(train_features, train_labels),
        "logistic_regression": LogisticBaseline().fit(train_features, train_labels),
    }
    metrics: dict[str, Any] = {
        "source": str(database_path or input_path),
        "feature_names": list(FULL_FEATURE_NAMES),
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "validation_sources": sorted(validation_sources),
        "models": {},
    }
    round_indices = _first_round_indices(validation_rows)
    baseline = sum(train_labels) / len(train_labels)
    for name, model in models.items():
        probabilities = model.predict(validation_features)
        metrics["models"][name] = {
            "snapshot": binary_probability_metrics(probabilities, validation_labels, baseline_probability=baseline),
            "round": binary_probability_metrics(
                [probabilities[index] for index in round_indices],
                [validation_labels[index] for index in round_indices],
                baseline_probability=baseline,
            ),
        }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "version": 1,
                "feature_names": list(FULL_FEATURE_NAMES),
                "models": {name: model.to_dict() for name, model in models.items()},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/full_replays.jsonl"))
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=Path("models/statistical_baselines.json"))
    parser.add_argument("--metrics", type=Path, default=Path("models/statistical_baseline_metrics.json"))
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    metrics = train_baselines(
        input_path=args.input,
        database_path=args.database,
        output_path=args.output,
        metrics_path=args.metrics,
        sample_every=args.sample_every,
        seed=args.seed,
        max_rows=args.max_rows,
    )
    print(f"[baseline] rows={metrics['train_rows']} train, {metrics['validation_rows']} validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

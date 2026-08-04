"""Train the small Bayesian model from extracted replay snapshots."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from cs2_sim.core.model import SnapshotValueModel
from backend.replay_engine.training.metrics import binary_probability_metrics
from backend.replay_engine.training.data_paths import DATA_PATHS


def _read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _metrics(
    model: SnapshotValueModel,
    rows: list[dict[str, Any]],
    *,
    baseline_probability: float,
) -> dict[str, Any]:
    labelled = [row for row in rows if row.get("label_round_winner") in {"ct", "t"}]
    if not labelled:
        raise ValueError("snapshot file contains no round outcome labels")
    probabilities = [model.predict_ct_win(row) for row in labelled]
    labels = [float(row["label_round_winner"] == "ct") for row in labelled]
    return binary_probability_metrics(
        probabilities,
        labels,
        baseline_probability=baseline_probability,
    )


def _one_snapshot_per_round(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Use the earliest decision state so long fights do not dominate metrics."""

    first: dict[tuple[str, int], dict[str, Any]] = {}
    for row in rows:
        key = (str(row.get("source") or "unknown"), int(row.get("round_num") or 0))
        current = first.get(key)
        if current is None or int(row.get("tick") or 0) < int(current.get("tick") or 0):
            first[key] = row
    return list(first.values())


def train(input_path: Path, output_path: Path, metrics_path: Path, seed: int) -> None:
    rows = _read_rows(input_path)
    labelled = [row for row in rows if row.get("label_round_winner") in {"ct", "t"}]
    if not labelled:
        raise ValueError("snapshot file contains no round outcome labels")

    # Split by demo so snapshots from the same replay cannot leak across sets.
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in labelled:
        by_source.setdefault(str(row.get("source") or "unknown"), []).append(row)
    sources = sorted(by_source)
    random.Random(seed).shuffle(sources)
    validation_sources = set(sources[-max(1, len(sources) // 5) :])
    train_rows = [row for source in sources if source not in validation_sources for row in by_source[source]]
    validation_rows = [row for source in sources if source in validation_sources for row in by_source[source]]

    model = SnapshotValueModel()
    for row in train_rows:
        model.observe(row)
    baseline_probability = sum(row["label_round_winner"] == "ct" for row in train_rows) / len(train_rows)
    metrics = _metrics(model, validation_rows, baseline_probability=baseline_probability)
    round_metrics = _metrics(
        model,
        _one_snapshot_per_round(validation_rows),
        baseline_probability=baseline_probability,
    )
    evaluation_bucket_count = sum(key.startswith("exact|") for key in model._counts)
    evaluation_sample_count = model.global_sample_count()

    # Save the deployment artifact trained on every row only after computing
    # untouched validation metrics with the split model above.
    final_model = SnapshotValueModel()
    for row in labelled:
        final_model.observe(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    final_model.save(output_path)
    metrics_path.write_text(
        json.dumps(
            {
                "source": str(input_path),
                "train_rows": len(train_rows),
                "validation_rows": len(validation_rows),
                "validation_sources": sorted(validation_sources),
                "evaluation_exact_state_buckets": evaluation_bucket_count,
                "evaluation_training_samples": evaluation_sample_count,
                "artifact_training_samples": final_model.global_sample_count(),
                "snapshot_metrics": metrics,
                "round_metrics": round_metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"[snapshot] rows={len(labelled)} train={len(train_rows)} validation={len(validation_rows)}")
    print(f"[snapshot] saved {output_path}")
    print(f"[snapshot] validation {json.dumps(metrics, sort_keys=True)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.public_processed / "analysis_snapshots.jsonl")
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/small_snapshot_value.json"))
    parser.add_argument("--metrics", type=Path, default=Path("model/artifacts/small_snapshot_metrics.json"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    train(args.input, args.output, args.metrics, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

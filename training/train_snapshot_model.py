"""Train the small Bayesian model from extracted replay snapshots."""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any

from cs2_sim.models import SnapshotValueModel


def _read_rows(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _metrics(model: SnapshotValueModel, rows: list[dict[str, Any]]) -> dict[str, float]:
    labelled = [row for row in rows if row.get("label_round_winner") in {"ct", "t"}]
    if not labelled:
        raise ValueError("snapshot file contains no round outcome labels")
    probabilities = [model.predict_ct_win(row) for row in labelled]
    labels = [float(row["label_round_winner"] == "ct") for row in labelled]
    eps = 1e-7
    log_loss = -sum(
        label * math.log(max(eps, probability))
        + (1.0 - label) * math.log(max(eps, 1.0 - probability))
        for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    brier = sum(
        (probability - label) ** 2
        for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    return {"log_loss": log_loss, "brier": brier}


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
    output_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    model.save(output_path)
    metrics = _metrics(model, validation_rows)
    metrics_path.write_text(
        json.dumps(
            {
                "source": str(input_path),
                "train_rows": len(train_rows),
                "validation_rows": len(validation_rows),
                "validation_sources": sorted(validation_sources),
                "unique_state_buckets": len(model._counts),
                "metrics": metrics,
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
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/analysis_snapshots.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("models/small_snapshot_value.json"))
    parser.add_argument("--metrics", type=Path, default=Path("models/small_snapshot_metrics.json"))
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    train(args.input, args.output, args.metrics, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


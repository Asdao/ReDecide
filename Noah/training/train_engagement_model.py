"""Train the compact statistical engagement model on leakage-safe JSONL windows.

The trainer is intentionally dependency-free.  It creates a reproducible
Beta-smoothed artifact that can be deployed immediately; LightGBM heads can
later be evaluated against the same grouped split without changing the input
contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from collections import Counter
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cs2_sim.core.model import EngagementModel

from Noah.training.data_paths import DATA_PATHS
from Noah.training.metrics import binary_probability_metrics

TRAINING_SCHEMA_VERSION = "engagement_training_v2"
TARGETS = ("kill", "death", "trade", "survival", "damage", "round_win")


def _rows(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        for line in source:
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("engagement JSONL rows must be objects")
                yield value


def _group(row: dict[str, Any], index: int) -> str:
    for key in ("match_id", "source", "source_path", "demo_file", "replay_id"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return f"row:{index}"


def _label(row: dict[str, Any], target: str) -> int | None:
    value = row.get(f"label_{target}")
    if value is None and target == "survived_after_kill":
        value = row.get(target)
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip().lower()
        if value in {"", "none", "null", "unknown", "nan"}:
            return None
        return int(value not in {"0", "false", "no", "dead", "negative"})
    return int(bool(value))


def _split_groups(groups: set[str], *, validation_fraction: float, seed: int) -> set[str]:
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if len(groups) < 2:
        return set()
    ordered = sorted(groups)
    random.Random(seed).shuffle(ordered)
    count = max(1, round(len(ordered) * validation_fraction))
    return set(ordered[-min(count, len(ordered) - 1) :])


def train_engagement_model(
    input_path: str | Path,
    output_path: str | Path,
    *,
    metrics_path: str | Path | None = None,
    validation_fraction: float = 0.2,
    seed: int = 7,
    alpha: float = 1.0,
    min_support: int = 5,
) -> dict[str, Any]:
    """Fit the statistical model and evaluate it on held-out match groups."""

    source = Path(input_path)
    if not source.is_file():
        raise FileNotFoundError(source)
    groups: set[str] = set()
    row_count = 0
    label_counts: Counter[str] = Counter()
    digest = hashlib.sha256()
    for index, row in enumerate(_rows(source)):
        group = _group(row, index)
        groups.add(group)
        row_count += 1
        for target in TARGETS:
            label = _label(row, target)
            if label is not None:
                label_counts[f"{target}_{label}"] += 1
        identity = {
            "group": group,
            "round": row.get("round_num"),
            "tick": row.get("anchor_tick", row.get("tick")),
            "player": row.get("player_id"),
        }
        digest.update(json.dumps(identity, sort_keys=True, separators=(",", ":"), default=str).encode())
        digest.update(b"\n")
    if row_count == 0:
        raise ValueError("engagement JSONL contains no rows")

    validation_groups = _split_groups(groups, validation_fraction=validation_fraction, seed=seed)
    model = EngagementModel(alpha=alpha, min_support=min_support)
    train_count = validation_count = 0
    train_labels: dict[str, list[int]] = {target: [] for target in TARGETS}
    validation_labels: dict[str, list[int]] = {target: [] for target in TARGETS}
    validation_probabilities: dict[str, list[float]] = {target: [] for target in TARGETS}
    for index, row in enumerate(_rows(source)):
        is_validation = _group(row, index) in validation_groups
        if not is_validation:
            model.observe(row)
            train_count += 1
            for target in TARGETS:
                value = _label(row, target)
                if value is not None:
                    train_labels[target].append(value)
            continue
        validation_count += 1
        prediction = model.predict_dict(row)
        for target in TARGETS:
            value = _label(row, target)
            if value is not None:
                validation_labels[target].append(value)
                validation_probabilities[target].append(float(prediction[f"{target}_probability"]))

    output = Path(output_path)
    model.save(output)
    metrics: dict[str, Any] = {
        "schema_version": TRAINING_SCHEMA_VERSION,
        "model_schema_version": "engagement_model_v1",
        "input": source.as_posix(),
        "output": output.as_posix(),
        "rows": {"total": row_count, "training": train_count, "validation": validation_count},
        "groups": {
            "total": len(groups),
            "training": len(groups - validation_groups),
            "validation": len(validation_groups),
            "validation_ids": sorted(validation_groups),
        },
        "seed": int(seed),
        "validation_fraction": float(validation_fraction),
        "dataset_fingerprint": digest.hexdigest(),
        "label_counts": dict(sorted(label_counts.items())),
        "state_count": model.state_count,
        "observation_count": model.observation_count,
        "targets": {},
    }
    for target in TARGETS:
        labels = validation_labels[target]
        probabilities = validation_probabilities[target]
        train_prior = (
            sum(train_labels[target]) / len(train_labels[target])
            if train_labels[target]
            else None
        )
        target_metrics: dict[str, Any] = {
            "training_rows": len(train_labels[target]),
            "validation_rows": len(labels),
            "training_prior": train_prior,
        }
        if labels:
            target_metrics["validation"] = binary_probability_metrics(
                probabilities,
                labels,
                baseline_probability=train_prior,
            )
        else:
            target_metrics["validation"] = None
        metrics["targets"][target] = target_metrics
    if metrics_path is not None:
        destination = Path(metrics_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "engagement_windows_2s.jsonl")
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/releases/v2/engagement_model.json"))
    parser.add_argument("--metrics", type=Path, default=Path("model/artifacts/releases/v2/engagement_metrics.json"))
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--min-support", type=int, default=5)
    args = parser.parse_args()
    metrics = train_engagement_model(
        args.input,
        args.output,
        metrics_path=args.metrics,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
        alpha=args.alpha,
        min_support=args.min_support,
    )
    print(json.dumps({"rows": metrics["rows"], "states": metrics["state_count"], "output": metrics["output"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

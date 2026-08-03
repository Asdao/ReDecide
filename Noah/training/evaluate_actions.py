"""Evaluate movement-tendency labels on match/source-held-out action rows.

The action artifact describes observed movement (``hold``/``move``), not a
strategically optimal CS2 decision.  This evaluator trains an in-memory
frequency model on development groups and reports only held-out rows.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from cs2_sim.core.model import ActionFrequencyModel
from Noah.training.dataset_split import dataset_fingerprint, grouped_split
from Noah.training.metrics import multiclass_probability_metrics
from Noah.training.replay_repository import ReplayRepository
from Noah.training.train_action_models import ACTION_SCHEMA_VERSION, action_state_key
from Noah.training.data_paths import DATA_PATHS


def _load_rows(input_path: Path | None, database_path: Path | None) -> list[dict[str, Any]]:
    if input_path is not None and database_path is not None:
        raise ValueError("input_path and database_path are mutually exclusive")
    if database_path is not None:
        with ReplayRepository(database_path) as repository:
            return list(repository.iter_actions())
    if input_path is None:
        raise ValueError("one of input_path or database_path is required")
    with input_path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def _legal_actions(row: dict[str, Any]) -> list[str]:
    values = row.get("legal_actions")
    if isinstance(values, str):
        values = [values]
    if not values:
        values = ["hold", "move"]
    return list(dict.fromkeys(str(value) for value in values))


def evaluate_actions(
    *,
    input_path: Path | None = None,
    database_path: Path | None = None,
    validation_fraction: float = 0.2,
    seed: int = 7,
    max_rows: int | None = None,
) -> dict[str, Any]:
    rows = _load_rows(input_path, database_path)
    if max_rows is not None:
        if max_rows <= 0:
            raise ValueError("max_rows must be positive")
        rows = rows[:max_rows]
    rows = [row for row in rows if str(row.get("action") or "") in {"hold", "move"}]
    if not rows:
        raise ValueError("no movement-tendency action rows found")
    train_rows, validation_rows, split = grouped_split(
        rows,
        validation_fraction=validation_fraction,
        seed=seed,
    )
    model = ActionFrequencyModel()
    global_counts: Counter[str] = Counter()
    for row in train_rows:
        action = str(row["action"])
        model.observe(action_state_key(row), action)
        global_counts[action] += 1
    if not global_counts:
        raise ValueError("training groups contain no movement-tendency labels")
    total = sum(global_counts.values())
    global_prior = {action: count / total for action, count in global_counts.items()}
    scores: list[dict[str, float]] = []
    labels: list[str] = []
    for row in validation_rows:
        legal = _legal_actions(row)
        scores.append(model.score_actions(action_state_key(row), legal))
        labels.append(str(row["action"]))
    metrics = multiclass_probability_metrics(
        scores,
        labels,
        baseline_probabilities=global_prior,
    )
    report = {
        "report_type": "movement_tendency_held_out",
        "label_semantics": "observed movement tendency (hold/move), not strategic best move",
        "schema_version": ACTION_SCHEMA_VERSION,
        "rows": len(rows),
        "train_rows": len(train_rows),
        "validation_rows": len(validation_rows),
        "action_states": model.state_count,
        "actions": sorted(global_counts),
        "metrics": metrics,
        "metadata": {
            "feature_schema_version": ACTION_SCHEMA_VERSION,
            "dataset_fingerprint": dataset_fingerprint(rows, schema_version=ACTION_SCHEMA_VERSION),
            "split_fingerprint": split["split_fingerprint"],
            "split_schema_version": split["schema_version"],
            "seed": seed,
            "validation_fraction": validation_fraction,
            "train_groups": split["train_groups"],
            "validation_groups": split["validation_groups"],
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "player_actions.jsonl")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/action_evaluation.json"))
    args = parser.parse_args()
    input_path = None if args.database is not None else args.input
    report = evaluate_actions(
        input_path=input_path,
        database_path=args.database,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
        max_rows=args.max_rows,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report["metrics"], sort_keys=True))
    print(f"[actions-evaluate] validation_rows={report['validation_rows']} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

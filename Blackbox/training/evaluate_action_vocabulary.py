"""Report action-vocabulary coverage and match-separated label rates."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from cs2_sim.action_vocabulary import ACTION_NAMES, canonical_action

from Blackbox.training.train_engagement_model import TARGETS, _group, _rows, _split_groups


def evaluate_action_vocabulary(
    input_path: str | Path,
    output_path: str | Path,
    *,
    validation_fraction: float = 0.2,
    seed: int = 7,
    min_samples: int = 100,
    model_metrics_path: str | Path | None = None,
) -> dict[str, Any]:
    rows = list(_rows(Path(input_path)))
    if not rows:
        raise ValueError("engagement JSONL contains no rows")
    groups = {_group(row, index) for index, row in enumerate(rows)}
    validation_groups = _split_groups(groups, validation_fraction=validation_fraction, seed=seed)
    action_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        action_rows[canonical_action(row.get("observed_action"))].append(row)

    actions: dict[str, Any] = {}
    for action in ACTION_NAMES:
        values = action_rows.get(action, [])
        train_values = [row for index, row in enumerate(values) if _group(row, index) not in validation_groups]
        validation_values = [row for index, row in enumerate(values) if _group(row, index) in validation_groups]
        outcome_rates: dict[str, float | None] = {}
        for target in TARGETS:
            labels = [row.get(f"label_{target}") for row in values]
            labels = [bool(value) for value in labels if value is not None]
            outcome_rates[target] = sum(labels) / len(labels) if labels else None
        actions[action] = {
            "rows": len(values),
            "training_rows": len(train_values),
            "validation_rows": len(validation_values),
            "match_groups": len({_group(row, index) for index, row in enumerate(values)}),
            "supported_for_training": len(train_values) >= min_samples,
            "outcome_rates": outcome_rates,
        }
    report: dict[str, Any] = {
        "report_type": "action_vocabulary_coverage",
        "schema_version": "action_vocabulary_evaluation_v1",
        "input": str(input_path),
        "rows": len(rows),
        "groups": len(groups),
        "validation_groups": sorted(validation_groups),
        "validation_fraction": validation_fraction,
        "seed": seed,
        "min_samples": min_samples,
        "actions": actions,
        "observed_action_counts": dict(Counter(canonical_action(row.get("observed_action")) for row in rows)),
    }
    if model_metrics_path is not None and Path(model_metrics_path).is_file():
        report["model_metrics"] = json.loads(Path(model_metrics_path).read_text(encoding="utf-8"))
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--min-samples", type=int, default=100)
    parser.add_argument("--model-metrics", type=Path, default=None)
    args = parser.parse_args()
    report = evaluate_action_vocabulary(
        args.input,
        args.output,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
        min_samples=args.min_samples,
        model_metrics_path=args.model_metrics,
    )
    print(json.dumps({"rows": report["rows"], "actions": report["observed_action_counts"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

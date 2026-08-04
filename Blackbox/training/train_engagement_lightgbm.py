"""Train optional shallow LightGBM engagement heads on grouped windows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cs2_sim.core.model import (
    ENGAGEMENT_LGBM_FEATURE_NAMES,
    ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION,
    ENGAGEMENT_TARGETS,
    EngagementLightGBMBundle,
    engagement_feature_vector,
)

from Blackbox.training.data_paths import DATA_PATHS
from Blackbox.training.metrics import binary_probability_metrics
from Blackbox.training.train_engagement_model import _group, _label, _rows, _split_groups


def train_engagement_lightgbm(
    input_path: str | Path,
    output_path: str | Path,
    *,
    metrics_path: str | Path | None = None,
    validation_fraction: float = 0.2,
    seed: int = 7,
    num_boost_round: int = 120,
) -> dict[str, Any]:
    try:
        import lightgbm as lgb
        import numpy as np
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("install the full dependencies with `pip install .[full]`") from exc
    rows = list(_rows(Path(input_path)))
    if not rows:
        raise ValueError("engagement JSONL contains no rows")
    groups = {_group(row, index) for index, row in enumerate(rows)}
    validation_groups = _split_groups(groups, validation_fraction=validation_fraction, seed=seed)
    train_rows = [row for index, row in enumerate(rows) if _group(row, index) not in validation_groups]
    validation_rows = [row for index, row in enumerate(rows) if _group(row, index) in validation_groups]
    if not train_rows or not validation_rows:
        raise ValueError("need at least two match/source groups for LightGBM validation")
    boosters: dict[str, Any] = {}
    metrics: dict[str, Any] = {}
    parameters = {
        "objective": "binary",
        "metric": "binary_logloss",
        "learning_rate": 0.05,
        "num_leaves": 7,
        "max_bin": 31,
        "min_data_in_leaf": 30,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 1,
        "verbosity": -1,
        "seed": seed,
        "feature_fraction_seed": seed,
        "bagging_seed": seed,
    }
    for target in ENGAGEMENT_TARGETS:
        train_labels = [_label(row, target) for row in train_rows]
        validation_labels = [_label(row, target) for row in validation_rows]
        train_pairs = [(row, label) for row, label in zip(train_rows, train_labels, strict=True) if label is not None]
        validation_pairs = [(row, label) for row, label in zip(validation_rows, validation_labels, strict=True) if label is not None]
        if not train_pairs or not validation_pairs or len({label for _, label in train_pairs}) < 2:
            continue
        train_matrix_target = np.asarray([engagement_feature_vector(row) for row, _ in train_pairs], dtype=float)
        train_y = np.asarray([label for _, label in train_pairs], dtype=int)
        valid_matrix_target = np.asarray([engagement_feature_vector(row) for row, _ in validation_pairs], dtype=float)
        valid_y = np.asarray([label for _, label in validation_pairs], dtype=int)
        train_set = lgb.Dataset(train_matrix_target, label=train_y, feature_name=list(ENGAGEMENT_LGBM_FEATURE_NAMES))
        valid_set = lgb.Dataset(valid_matrix_target, label=valid_y, reference=train_set, feature_name=list(ENGAGEMENT_LGBM_FEATURE_NAMES))
        booster = lgb.train(
            parameters,
            train_set,
            num_boost_round=num_boost_round,
            valid_sets=[valid_set],
            valid_names=["validation"],
            callbacks=[lgb.early_stopping(20, verbose=False)],
        )
        boosters[target] = booster
        probabilities = booster.predict(valid_matrix_target).tolist()
        prior = float(train_y.mean())
        metrics[target] = {
            "training_rows": len(train_y),
            "validation_rows": len(valid_y),
            "training_prior": prior,
            "validation": binary_probability_metrics(probabilities, valid_y.tolist(), baseline_probability=prior),
        }
    if not boosters:
        raise ValueError("no engagement target had both classes in the training groups")
    bundle = EngagementLightGBMBundle(boosters)
    bundle.save(output_path)
    result: dict[str, Any] = {
        "schema_version": "engagement_lightgbm_training_v3",
        "model_schema_version": ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION,
        "input": str(input_path),
        "output": str(output_path),
        "rows": {"total": len(rows), "training": len(train_rows), "validation": len(validation_rows)},
        "groups": {"total": len(groups), "validation": sorted(validation_groups)},
        "feature_names": list(ENGAGEMENT_LGBM_FEATURE_NAMES),
        "targets": metrics,
    }
    if metrics_path is not None:
        destination = Path(metrics_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "engagement_windows_v3_5s.jsonl")
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/releases/v4/engagement_lightgbm.json"))
    parser.add_argument("--metrics", type=Path, default=Path("model/artifacts/releases/v4/engagement_lightgbm_metrics.json"))
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--num-boost-round", type=int, default=120)
    args = parser.parse_args()
    result = train_engagement_lightgbm(
        args.input,
        args.output,
        metrics_path=args.metrics,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
        num_boost_round=args.num_boost_round,
    )
    print(json.dumps({"rows": result["rows"], "targets": sorted(result["targets"]), "output": result["output"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

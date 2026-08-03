"""Evaluate candidate-action probabilities on held-out rollout aggregates."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_NOAH_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _NOAH_ROOT.parent
for _path in (_NOAH_ROOT / "model" / "src", _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from cs2_sim.core.model import FullLightGBMModel, SmallStatisticalModel

from Noah.training.candidate_rollouts import (
    _action_from_name,
    deserialize_state,
    load_candidate_rows,
)

EVALUATION_SCHEMA_VERSION = "candidate_evaluation_v1"


def _load_rollouts(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise TypeError("rollout rows must be JSON objects")
            rows.append(row)
    return rows


def _state_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    group = row.get("record_index")
    group_value = str(group) if group is not None else str(row.get("source") or "")
    return (
        group_value,
        str((row.get("event") or {}).get("event_id") or row.get("event_id") or ""),
        str(row.get("actor_id") or ""),
    )


def _load_model(model_dir: str | Path) -> Any:
    root = Path(model_dir)
    full_path = root / "candidate_action_value.txt"
    if full_path.is_file():
        try:
            return FullLightGBMModel.load(full_path)
        except (ImportError, RuntimeError, ValueError):
            pass
    small_path = root / "small_statistical.json"
    return SmallStatisticalModel.load(small_path)


def _load_training_metrics(model_dir: str | Path) -> dict[str, Any] | None:
    path = Path(model_dir) / "candidate_training_metrics.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def evaluate_candidate_value(
    candidate_states_path: str | Path,
    rollout_path: str | Path,
    model_dir: str | Path,
    *,
    min_support: int = 5,
) -> dict[str, Any]:
    states = load_candidate_rows(candidate_states_path)
    rollouts = _load_rollouts(rollout_path)
    state_map = {
        _state_key(row): row
        for row in states
    }
    model = _load_model(model_dir)
    training_metrics = _load_training_metrics(model_dir)
    heldout_split_valid = (
        bool(training_metrics.get("heldout_split_valid"))
        if training_metrics is not None
        else None
    )
    total = 0
    brier_sum = 0.0
    logloss_sum = 0.0
    supported_rows = 0
    groups: dict[tuple[str, str], list[tuple[str, float, float]]] = defaultdict(list)
    for row in rollouts:
        key = _state_key(row)
        source = state_map.get(key)
        if source is None:
            continue
        state = deserialize_state(source.get("state") or {})
        action = _action_from_name(str(row.get("action") or ""))
        player_id = str(row.get("actor_id") or "")
        if hasattr(model, "predict_probability"):
            probability = float(model.predict_probability(state, player_id, action))
        else:
            probability = float(model.score_actions(state, player_id, (action,))[action])
        probability = min(1.0 - 1e-7, max(1e-7, probability))
        wins = max(0, int(row.get("wins", 0)))
        losses = max(0, int(row.get("losses", 0)))
        observations = wins + losses
        if observations <= 0:
            continue
        total += observations
        brier_sum += wins * (probability - 1.0) ** 2 + losses * probability**2
        logloss_sum += -wins * math.log(probability) - losses * math.log(1.0 - probability)
        support_info = getattr(getattr(model, "small_model", model), "action_support_info", None)
        support = support_info(state, player_id) if callable(support_info) else {"support": 0}
        supported_rows += int(int(support.get("support", 0)) >= min_support)
        empirical = wins / observations
        groups[key].append((str(row.get("action") or ""), probability, empirical))

    top1_matches = 0
    groups_with_empirical_variance = 0
    for candidates in groups.values():
        empirical_values = [item[2] for item in candidates]
        if not empirical_values or max(empirical_values) - min(empirical_values) <= 1e-9:
            continue
        groups_with_empirical_variance += 1
        predicted = max(candidates, key=lambda item: (item[1], item[0]))[0]
        empirical = max(candidates, key=lambda item: (item[2], item[0]))[0]
        top1_matches += int(predicted == empirical)
    quality_warnings: list[str] = []
    if heldout_split_valid is False:
        quality_warnings.append(
            "training_artifact_has_no_heldout_match_split: evaluation is not a generalisation estimate"
        )
    elif heldout_split_valid is None:
        quality_warnings.append(
            "training_metrics_missing: held-out separation cannot be verified"
        )
    if groups and groups_with_empirical_variance == 0:
        quality_warnings.append(
            "no_action_outcome_variance: held-out simulator labels cannot rank actions in these states"
        )
    comparable_groups = groups_with_empirical_variance
    evaluation_comparable = comparable_groups > 0 and heldout_split_valid is not False
    if rollouts and all(
        str(row.get("survival_target") or "") == "simulator_final_alive_no_combat"
        for row in rollouts
    ):
        quality_warnings.append(
            "survival_target_is_simulator_final_alive_no_combat: do not interpret it as weapon-level death risk"
        )
    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "model_type": type(model).__name__,
        "min_support": min_support,
        "rollout_rows": len(rollouts),
        "observations": total,
        "candidate_states": len(states),
        "evaluated_action_rows": sum(len(items) for items in groups.values()),
        "supported_action_rows": supported_rows,
        "support_rate": supported_rows / sum(len(items) for items in groups.values()) if groups else 0.0,
        "state_groups": len(groups),
        "comparable_state_groups": comparable_groups,
        "groups_with_empirical_action_variance": groups_with_empirical_variance,
        "empirical_action_variance_rate": groups_with_empirical_variance / len(groups) if groups else 0.0,
        "rollout_label_source": "simulator_round_winner",
        "quality_status": (
            "comparable"
            if evaluation_comparable
            else "not_comparable_no_heldout_split"
            if heldout_split_valid is False
            else "not_comparable_no_action_outcome_variance"
        ),
        "quality_warnings": quality_warnings,
        "heldout_split_valid": heldout_split_valid,
        "top1_empirical_match_rate": top1_matches / comparable_groups if evaluation_comparable else None,
        "brier": brier_sum / total if total else None,
        "log_loss": logloss_sum / total if total else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_states", type=Path)
    parser.add_argument("rollouts", type=Path)
    parser.add_argument("model_dir", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--min-support", type=int, default=5)
    args = parser.parse_args()
    result = evaluate_candidate_value(
        args.candidate_states,
        args.rollouts,
        args.model_dir,
        min_support=args.min_support,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["EVALUATION_SCHEMA_VERSION", "evaluate_candidate_value", "main"]

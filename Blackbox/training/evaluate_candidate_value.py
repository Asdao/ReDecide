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

from Blackbox.training.candidate_labels import (
    CANDIDATE_LABEL_SCHEMA_VERSION,
    TRAINING_LABELS,
    candidate_decision_key,
    load_candidate_labels,
)
from Blackbox.training.candidate_rollouts import (
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
    return candidate_decision_key(row)


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


def evaluate_candidate_labels(
    candidate_states_path: str | Path,
    labels_path: str | Path,
    model_dir: str | Path,
    *,
    min_support: int = 5,
) -> dict[str, Any]:
    """Evaluate candidate suitability probabilities against rubric labels."""

    states = load_candidate_rows(candidate_states_path)
    labels = load_candidate_labels(labels_path)
    model = _load_model(model_dir)
    training_metrics = _load_training_metrics(model_dir)
    heldout_split_valid = (
        bool(training_metrics.get("heldout_split_valid"))
        if training_metrics is not None
        else None
    )
    state_map = {_state_key(row): row for row in states}
    total = 0
    brier_sum = 0.0
    logloss_sum = 0.0
    supported_rows = 0
    label_counts: defaultdict[str, int] = defaultdict(int)
    groups: defaultdict[tuple[str, str, str], list[tuple[str, str, float]]] = defaultdict(list)
    for row in labels:
        label = str(row.get("label") or "")
        label_counts[label] += 1
        if label not in TRAINING_LABELS:
            continue
        state_row = state_map.get(_state_key(row))
        if state_row is None:
            continue
        state = deserialize_state(state_row.get("state") or {})
        action = _action_from_name(str(row.get("action") or ""))
        player_id = str(row.get("actor_id") or "")
        if hasattr(model, "predict_probability"):
            probability = float(model.predict_probability(state, player_id, action))
        else:
            probability = float(model.score_actions(state, player_id, (action,))[action])
        probability = min(1.0 - 1e-7, max(1e-7, probability))
        target = 1.0 if label == "preferred" else 0.0
        total += 1
        brier_sum += (probability - target) ** 2
        logloss_sum += -(target * math.log(probability) + (1.0 - target) * math.log(1.0 - probability))
        support_info = getattr(getattr(model, "small_model", model), "action_support_info", None)
        support = support_info(state, player_id) if callable(support_info) else {"support": 0}
        supported_rows += int(int(support.get("support", 0)) >= min_support)
        key = _state_key(row)
        groups[key].append((str(row.get("action") or ""), label, probability))

    comparable_groups = 0
    top1_matches = 0
    for candidates in groups.values():
        labels_in_group = {label for _action, label, _probability in candidates}
        if not TRAINING_LABELS.issubset(labels_in_group):
            continue
        comparable_groups += 1
        predicted = max(candidates, key=lambda item: (item[2], item[0]))[0]
        preferred = {action for action, label, _probability in candidates if label == "preferred"}
        top1_matches += int(predicted in preferred)

    if heldout_split_valid is False:
        quality_status = "not_comparable_no_heldout_split"
    elif comparable_groups == 0:
        quality_status = "not_comparable_no_label_variance"
    else:
        quality_status = "comparable"
    return {
        "schema_version": "candidate_evaluation_v2",
        "evaluation_target": "pre_event_suitability",
        "label_schema": CANDIDATE_LABEL_SCHEMA_VERSION,
        "model_type": type(model).__name__,
        "min_support": min_support,
        "candidate_states": len(states),
        "label_rows": len(labels),
        "evaluated_action_rows": total,
        "supported_action_rows": supported_rows,
        "support_rate": supported_rows / total if total else 0.0,
        "state_groups": len(groups),
        "comparable_state_groups": comparable_groups,
        "label_variance_rate": comparable_groups / len(groups) if groups else 0.0,
        "label_counts": dict(sorted(label_counts.items())),
        "quality_status": quality_status,
        "quality_warnings": (
            ["training_artifact_has_no_heldout_match_split"]
            if heldout_split_valid is False
            else ["no_action_label_variance: rubric labels cannot rank actions in these states"]
            if groups and comparable_groups == 0
            else []
        ),
        "heldout_split_valid": heldout_split_valid,
        "top1_label_match_rate": top1_matches / comparable_groups if comparable_groups else None,
        "brier": brier_sum / total if total else None,
        "log_loss": logloss_sum / total if total else None,
    }


def evaluate_candidate_value(
    candidate_states_path: str | Path,
    rollout_path: str | Path | None,
    model_dir: str | Path,
    *,
    labels_path: str | Path | None = None,
    min_support: int = 5,
) -> dict[str, Any]:
    if labels_path is not None:
        return evaluate_candidate_labels(
            candidate_states_path,
            labels_path,
            model_dir,
            min_support=min_support,
        )
    if rollout_path is None:
        raise ValueError("either rollout_path or labels_path is required")
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
    parser.add_argument("rollouts_or_model", type=Path)
    parser.add_argument("model_or_output", type=Path)
    parser.add_argument("output", type=Path, nargs="?")
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--min-support", type=int, default=5)
    args = parser.parse_args()
    if args.labels is not None and args.output is None:
        rollout_path = None
        model_dir = args.rollouts_or_model
        output_path = args.model_or_output
    elif args.output is not None:
        rollout_path = args.rollouts_or_model
        model_dir = args.model_or_output
        output_path = args.output
    else:
        parser.error("output is required unless --labels is supplied")
    result = evaluate_candidate_value(
        args.candidate_states,
        rollout_path,
        model_dir,
        min_support=args.min_support,
        labels_path=args.labels,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "EVALUATION_SCHEMA_VERSION",
    "evaluate_candidate_labels",
    "evaluate_candidate_value",
    "main",
]

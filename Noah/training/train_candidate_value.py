"""Train candidate-action value models from extracted states and rollouts.

The rollout file stores aggregate wins/losses.  This trainer expands those
counts only in memory for LightGBM and persists the compact Bayesian counts.
Input rows should already be split by complete demo before extraction.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

_NOAH_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _NOAH_ROOT.parent
for _path in (_NOAH_ROOT / "model" / "src", _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from cs2_sim.actions import Action, ActionType
from cs2_sim.core.model import FullLightGBMModel, SmallStatisticalModel, TrainingExample

from Noah.training.calibration import PlattCalibrator
from Noah.training.candidate_rollouts import deserialize_state, load_candidate_rows
from Noah.training.candidate_states import CANDIDATE_STATE_SCHEMA_VERSION

ROLLOUT_SCHEMA_VERSION = "candidate_rollout_v1"
TRAINING_SCHEMA_VERSION = "candidate_training_v1"


def _action_from_name(name: str) -> Action:
    action_name, separator, target = str(name).partition(":")
    return Action(ActionType(action_name), target if separator else None)


def _state_key(row: dict[str, Any]) -> tuple[str, str, str]:
    group = row.get("record_index")
    group_value = str(group) if group is not None else str(row.get("source") or "")
    return (
        group_value,
        str((row.get("event") or {}).get("event_id") or row.get("event_id") or ""),
        str(row.get("actor_id") or ""),
    )


def _load_rollouts(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    rows: list[dict[str, Any]] = []
    with source.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict) or row.get("schema_version") != ROLLOUT_SCHEMA_VERSION:
                raise ValueError("rollout input has an unsupported schema")
            rows.append(row)
    return rows


def _examples(
    candidate_rows: list[dict[str, Any]],
    rollout_rows: list[dict[str, Any]],
    *,
    max_examples: int | None = None,
) -> list[tuple[TrainingExample, str]]:
    states: dict[tuple[str, str], tuple[Any, str]] = {}
    for row in candidate_rows:
        key = _state_key(row)
        if key[1] and key[2]:
            states[key] = (deserialize_state(row.get("state") or {}), key[2])
    examples: list[tuple[TrainingExample, str]] = []
    for row in rollout_rows:
        key = _state_key(row)
        state_and_actor = states.get(key)
        if state_and_actor is None:
            continue
        state, actor = state_and_actor
        action = _action_from_name(str(row.get("action") or ""))
        wins = max(0, int(row.get("wins", 0)))
        losses = max(0, int(row.get("losses", 0)))
        group = str(row.get("record_index") if row.get("record_index") is not None else row.get("source") or "unknown")
        examples.extend((TrainingExample(state, actor, action, True), group) for _ in range(wins))
        examples.extend((TrainingExample(state, actor, action, False), group) for _ in range(losses))
        if max_examples is not None and len(examples) >= max_examples:
            return examples[:max_examples]
    return examples


def _log_loss(model: FullLightGBMModel, examples: list[TrainingExample]) -> float:
    if not examples:
        return 0.0
    values: list[float] = []
    for example in examples:
        probability = min(1.0 - 1e-7, max(1e-7, model.predict_probability(example.state, example.player_id, example.action)))
        label = 1.0 if example.success else 0.0
        values.append(-(label * math.log(probability) + (1.0 - label) * math.log(1.0 - probability)))
    return sum(values) / len(values)


def _rollout_signal_metrics(rollout_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measure whether action outcomes actually vary within a state group."""

    groups: defaultdict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rollout_rows:
        key = (str(row.get("event_id") or ""), str(row.get("actor_id") or ""))
        groups[key].append(float(row.get("round_win_probability", 0.0)))
    varying = sum(1 for values in groups.values() if values and max(values) - min(values) > 1e-9)
    warnings: list[str] = []
    if groups and varying == 0:
        warnings.append(
            "no_action_outcome_variance: simulator labels cannot distinguish actions in these states"
        )
    if rollout_rows and all(
        str(row.get("survival_target") or "") == "simulator_final_alive_no_combat"
        for row in rollout_rows
    ):
        warnings.append(
            "survival_target_is_simulator_final_alive_no_combat: do not interpret it as weapon-level death risk"
        )
    return {
        "rollout_state_groups": len(groups),
        "groups_with_action_outcome_variance": varying,
        "action_outcome_variance_rate": varying / len(groups) if groups else 0.0,
        "rollout_quality_warnings": warnings,
    }


def train_candidate_models(
    candidate_state_path: str | Path,
    rollout_path: str | Path,
    output_dir: str | Path,
    *,
    train_full: bool = True,
    max_examples: int | None = None,
    seed: int = 7,
) -> dict[str, Any]:
    candidate_rows = load_candidate_rows(candidate_state_path)
    rollout_rows = _load_rollouts(rollout_path)
    grouped_examples = _examples(candidate_rows, rollout_rows, max_examples=max_examples)
    if not grouped_examples:
        raise ValueError("no rollout rows matched candidate states")
    groups = sorted({group for _example, group in grouped_examples})
    random.Random(seed).shuffle(groups)
    if len(groups) > 1:
        validation_groups = set(groups[max(1, int(len(groups) * 0.8)) :])
        train_examples = [example for example, group in grouped_examples if group not in validation_groups]
        validation_examples = [example for example, group in grouped_examples if group in validation_groups]
        heldout_split_valid = bool(validation_examples)
    else:
        # Never split rows from one replay into train/validation.  That makes
        # the validation score look better without testing generalisation to a
        # new match.  A single-record input can still build a compact prior,
        # but it is not eligible for a promoted full model.
        train_examples = [example for example, _group in grouped_examples]
        validation_examples = []
        heldout_split_valid = False
    examples = [example for example, _group in grouped_examples]
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    small = SmallStatisticalModel()
    for example in train_examples:
        small.observe(example.state, example.player_id, example.action, success=example.success)
    small_path = output / "small_statistical.json"
    small.save(small_path)

    metrics: dict[str, Any] = {
        "schema_version": TRAINING_SCHEMA_VERSION,
        "candidate_state_schema": CANDIDATE_STATE_SCHEMA_VERSION,
        "rollout_schema": ROLLOUT_SCHEMA_VERSION,
        "candidate_rows": len(candidate_rows),
        "rollout_rows": len(rollout_rows),
        "examples": len(examples),
        "train_examples": len(train_examples),
        "validation_examples": len(validation_examples),
        "small_state_keys": len(small._action_counts),
        "full_trained": False,
        "split_strategy": "whole_record_group" if len(groups) > 1 else "single_record_prior_only",
        "heldout_split_valid": heldout_split_valid,
        "rollout_label_source": "simulator_round_winner",
        **_rollout_signal_metrics(rollout_rows),
    }
    has_counterfactual_signal = metrics["groups_with_action_outcome_variance"] > 0
    metrics["candidate_model_status"] = (
        "trainable_with_counterfactual_signal"
        if has_counterfactual_signal
        else "statistical_prior_only_no_counterfactual_signal"
    )
    metrics["promotable"] = has_counterfactual_signal and heldout_split_valid

    if train_full and not has_counterfactual_signal:
        metrics["full_error"] = (
            "no_action_outcome_variance: refusing to train a directional full candidate model"
        )
    elif train_full and not heldout_split_valid:
        metrics["full_error"] = (
            "heldout_match_split_required: provide candidate states from at least two complete demos"
        )
    elif train_full and len(train_examples) >= 2 and {example.success for example in train_examples} == {True, False}:
        full = FullLightGBMModel(small_model=small)
        try:
            full.fit(
                train_examples,
                validation_examples=validation_examples or None,
                num_boost_round=80,
            )
            validation_labels = [int(example.success) for example in validation_examples]
            if validation_examples and len(set(validation_labels)) == 2:
                raw_probabilities = [
                    full._lightgbm_score(example.state, example.player_id, example.action)
                    for example in validation_examples
                ]
                full.calibrator = PlattCalibrator().fit(raw_probabilities, validation_labels)
            full_path = output / "candidate_action_value.txt"
            full.save(full_path)
            metrics["full_trained"] = True
            metrics["calibrated"] = full.calibrator is not None
            metrics["full_log_loss"] = _log_loss(full, validation_examples)
        except (ImportError, RuntimeError) as exc:
            metrics["full_error"] = str(exc)

    (output / "candidate_training_metrics.json").write_text(
        json.dumps(metrics, indent=2) + "\n",
        encoding="utf-8",
    )
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_states", type=Path)
    parser.add_argument("rollouts", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--small-only", action="store_true")
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    metrics = train_candidate_models(
        args.candidate_states,
        args.rollouts,
        args.output_dir,
        train_full=not args.small_only,
        max_examples=args.max_examples,
        seed=args.seed,
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TRAINING_SCHEMA_VERSION", "main", "train_candidate_models"]

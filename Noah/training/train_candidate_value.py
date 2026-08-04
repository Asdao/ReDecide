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
from Noah.training.candidate_labels import (
    CANDIDATE_LABEL_SCHEMA_VERSION,
    CANDIDATE_RUBRIC_VERSION,
    TRAINING_LABELS,
    candidate_decision_key,
    load_candidate_labels,
)
from Noah.training.candidate_rollouts import deserialize_state, load_candidate_rows
from Noah.training.candidate_states import CANDIDATE_STATE_SCHEMA_VERSION

ROLLOUT_SCHEMA_VERSION = "candidate_rollout_v1"
TRAINING_SCHEMA_VERSION = "candidate_training_v2"


def _action_from_name(name: str) -> Action:
    action_name, separator, target = str(name).partition(":")
    return Action(ActionType(action_name), target if separator else None)


def _state_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return candidate_decision_key(row)


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


def _label_examples(
    candidate_rows: list[dict[str, Any]],
    label_rows: list[dict[str, Any]],
    *,
    max_examples: int | None = None,
) -> tuple[list[tuple[TrainingExample, str]], dict[str, Any]]:
    """Convert preferred/risky rubric labels into binary model examples."""

    states: dict[tuple[str, str, str], tuple[Any, str]] = {}
    for row in candidate_rows:
        key = _state_key(row)
        if key[1] and key[2]:
            states[key] = (deserialize_state(row.get("state") or {}), key[0])

    examples: list[tuple[TrainingExample, str]] = []
    label_counts: defaultdict[str, int] = defaultdict(int)
    group_labels: defaultdict[str, set[str]] = defaultdict(set)
    for row in label_rows:
        label = str(row.get("label") or "")
        label_counts[label] += 1
        if label not in TRAINING_LABELS:
            continue
        key = (
            str(row.get("group_id") or ""),
            str(row.get("event_id") or ""),
            str(row.get("actor_id") or ""),
        )
        state_and_group = states.get(key)
        if state_and_group is None:
            continue
        state, group = state_and_group
        action = _action_from_name(str(row.get("action") or ""))
        success = label == "preferred"
        examples.append((TrainingExample(state, key[2], action, success), group))
        group_labels["|".join(key[:2])].add(label)
        if max_examples is not None and len(examples) >= max_examples:
            break

    comparable_groups = sum(1 for labels in group_labels.values() if len(labels) > 1)
    return examples, {
        "label_rows": len(label_rows),
        "label_counts": dict(sorted(label_counts.items())),
        "label_state_groups": len(group_labels),
        "groups_with_label_variance": comparable_groups,
        "label_variance_rate": comparable_groups / len(group_labels) if group_labels else 0.0,
    }


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
    rollout_path: str | Path | None,
    output_dir: str | Path,
    *,
    labels_path: str | Path | None = None,
    train_full: bool = True,
    max_examples: int | None = None,
    seed: int = 7,
) -> dict[str, Any]:
    """Train from simulator rollouts or explicit rubric labels.

    Rubric labels are preferred for directional candidate training.  The
    simulator path remains supported for diagnostics and backwards
    compatibility, but it is not promoted when its action outcomes are
    constant within a state.
    """

    candidate_rows = load_candidate_rows(candidate_state_path)
    label_rows: list[dict[str, Any]] = []
    if labels_path is not None:
        label_rows = load_candidate_labels(labels_path)
        grouped_examples, label_metrics = _label_examples(
            candidate_rows,
            label_rows,
            max_examples=max_examples,
        )
        rollout_rows: list[dict[str, Any]] = []
    else:
        if rollout_path is None:
            raise ValueError("either rollout_path or labels_path is required")
        rollout_rows = _load_rollouts(rollout_path)
        grouped_examples = _examples(candidate_rows, rollout_rows, max_examples=max_examples)
        label_metrics = {}
    if not grouped_examples:
        raise ValueError("no trainable candidate labels matched candidate states")
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
        "candidate_label_schema": CANDIDATE_LABEL_SCHEMA_VERSION if labels_path is not None else None,
        "rollout_schema": ROLLOUT_SCHEMA_VERSION if labels_path is None else None,
        "candidate_rows": len(candidate_rows),
        "rollout_rows": len(rollout_rows),
        "examples": len(examples),
        "train_examples": len(train_examples),
        "validation_examples": len(validation_examples),
        "small_state_keys": len(small._action_counts),
        "full_trained": False,
        "split_strategy": "whole_record_group" if len(groups) > 1 else "single_record_prior_only",
        "heldout_split_valid": heldout_split_valid,
        "rollout_label_source": "simulator_round_winner" if labels_path is None else None,
    }
    if labels_path is not None:
        metrics.update(label_metrics)
        metrics["label_source"] = CANDIDATE_RUBRIC_VERSION
        metrics["training_target"] = "pre_event_suitability"
        has_directional_signal = metrics["groups_with_label_variance"] > 0
        metrics["candidate_model_status"] = (
            "trainable_with_rubric_signal"
            if has_directional_signal
            else "statistical_prior_only_no_rubric_signal"
        )
    else:
        metrics.update(_rollout_signal_metrics(rollout_rows))
        metrics["training_target"] = "simulator_round_win"
        has_directional_signal = metrics["groups_with_action_outcome_variance"] > 0
        metrics["candidate_model_status"] = (
            "trainable_with_counterfactual_signal"
            if has_directional_signal
            else "statistical_prior_only_no_counterfactual_signal"
        )
    metrics["promotable"] = has_directional_signal and heldout_split_valid

    if train_full and not has_directional_signal:
        metrics["full_error"] = (
            "no_directional_label_signal: refusing to train a directional full candidate model"
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
            metadata_path = full_path.with_suffix(full_path.suffix + ".json")
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["training_target"] = metrics["training_target"]
            metadata["training_label_source"] = metrics.get("label_source") or metrics["rollout_label_source"]
            metadata["training_schema_version"] = TRAINING_SCHEMA_VERSION
            metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
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
    parser.add_argument("rollouts_or_output", type=Path)
    parser.add_argument("output_dir", type=Path, nargs="?")
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--small-only", action="store_true")
    parser.add_argument("--max-examples", type=int, default=None)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if args.labels is not None and args.output_dir is None:
        rollout_path = None
        output_dir = args.rollouts_or_output
    elif args.output_dir is not None:
        rollout_path = args.rollouts_or_output
        output_dir = args.output_dir
    else:
        parser.error("output_dir is required unless --labels is supplied")
    metrics = train_candidate_models(
        args.candidate_states,
        rollout_path,
        output_dir,
        labels_path=args.labels,
        train_full=not args.small_only,
        max_examples=args.max_examples,
        seed=args.seed,
    )
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["TRAINING_SCHEMA_VERSION", "main", "train_candidate_models"]

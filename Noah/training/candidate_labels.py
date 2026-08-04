"""Create leakage-safe suitability labels for candidate actions.

The historical candidate dataset labels every alternative with the simulator's
round winner.  That signal is not action-sensitive in the current simulator,
so it cannot train a directional recommendation model.  This module provides a
small, inspectable rubric that scores only the state available at the
candidate decision boundary.  It is deliberately a weak-labeling step: the
labels describe rubric suitability and are not claims about a later round
outcome.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from Noah.training.candidate_rollouts import load_candidate_rows

CANDIDATE_LABEL_SCHEMA_VERSION = "candidate_label_v1"
CANDIDATE_RUBRIC_VERSION = "pre_event_suitability_v1"
TRAINING_LABELS = frozenset({"preferred", "risky"})
ALL_LABELS = frozenset({"preferred", "risky", "unknown"})
MIN_RUBRIC_SPREAD = 0.08


def candidate_decision_key(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Return the stable join key shared by states, labels, and evaluations."""

    group = row.get("group_id")
    if group is None:
        group = row.get("record_index")
    group_value = str(group) if group is not None else str(row.get("source") or "")
    event = row.get("event")
    event = event if isinstance(event, Mapping) else {}
    return (
        group_value,
        str(event.get("event_id") or row.get("event_id") or ""),
        str(row.get("actor_id") or ""),
    )


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _action_family(action: str) -> str:
    return str(action).partition(":")[0]


def _state_summary(row: Mapping[str, Any]) -> tuple[dict[str, float], str | None]:
    state = row.get("state")
    if not isinstance(state, Mapping):
        return {}, None
    players = [item for item in state.get("players") or () if isinstance(item, Mapping)]
    actor_id = str(row.get("actor_id") or "")
    actor = next((item for item in players if str(item.get("player_id") or "") == actor_id), None)
    if actor is None:
        return {}, None
    team = str(actor.get("team") or "").lower()
    alive = [item for item in players if bool(item.get("alive", True))]
    friendly = sum(1 for item in alive if str(item.get("team") or "").lower() == team)
    enemy = sum(1 for item in alive if str(item.get("team") or "").lower() != team)
    action_features = row.get("action_features")
    visible_enemies = 0.0
    if isinstance(action_features, Mapping):
        for features in action_features.values():
            if isinstance(features, Mapping):
                visible_enemies = max(visible_enemies, _number(features.get("visible_enemies")))
    summary = {
        "health": _number(actor.get("health"), 100.0),
        "utility_count": _number(actor.get("utility_count")),
        "alive_friendly": float(friendly),
        "alive_enemy": float(enemy),
        "alive_difference": float(friendly - enemy),
        "visible_enemies": visible_enemies,
        "bomb_time_remaining": _number(state.get("bomb_time_remaining")),
    }
    return summary, team or None


def _rubric_score(
    summary: Mapping[str, float],
    action: str,
) -> tuple[float | None, list[str]]:
    """Return a relative suitability score for one supported action family."""

    family = _action_family(action)
    health = float(summary["health"])
    difference = float(summary["alive_difference"])
    contact = float(summary["visible_enemies"]) > 0
    utility = float(summary["utility_count"]) > 0
    if family in {"plant", "defuse", "save"}:
        return None, ["objective_action_outside_post_contact_rubric"]
    if family == "move_to_adjacent_zone":
        score = 0.45
        reasons: list[str] = []
        if health <= 60:
            score += 0.25
            reasons.append("reset_when_low_health")
        if difference < 0:
            score += 0.20
            reasons.append("reset_when_outnumbered")
        if health >= 85 and difference > 0:
            score -= 0.20
            reasons.append("leave_advantageous_state")
        return score, reasons or ["movement_tradeoff"]
    if family == "peek":
        score = 0.45
        reasons = []
        if health >= 75 and contact:
            score += 0.25
            reasons.append("reengage_with_visible_contact_and_health")
        if difference >= 0:
            score += 0.10
        else:
            score -= 0.25
            reasons.append("reengage_when_outnumbered")
        if health <= 40:
            score -= 0.35
            reasons.append("reengage_at_critical_health")
        return score, reasons or ["reengagement_tradeoff"]
    if family == "hold":
        score = 0.45
        reasons = []
        if difference > 0 and not contact:
            score += 0.20
            reasons.append("hold_with_team_advantage_without_contact")
        if difference < 0:
            score -= 0.25
            reasons.append("hold_when_outnumbered")
        if health <= 40:
            score -= 0.30
            reasons.append("hold_at_critical_health")
        return score, reasons or ["hold_tradeoff"]
    if family == "use_utility":
        score = 0.20 if not utility else 0.45
        reasons = ["no_utility_available"] if not utility else []
        if contact or difference < 0:
            score += 0.15
            reasons.append("utility_when_contact_or_disadvantage_present")
        return score, reasons or ["utility_timing"]
    return None, ["unsupported_action_family"]


def label_candidate_action(
    row: Mapping[str, Any],
    action: str,
    *,
    low_health: float = 60.0,
    critical_health: float = 40.0,
) -> dict[str, Any]:
    """Label one legal action using only the serialized pre-event state.

    ``preferred`` and ``risky`` are intentionally conservative.  Ambiguous
    states are ``unknown`` and are excluded from directional training.
    """

    summary, _team = _state_summary(row)
    family = _action_family(action)
    reasons: list[str] = []
    label = "unknown"
    confidence = 0.0

    if not summary:
        reasons.append("missing_pre_event_state")
    elif family in {"plant", "defuse", "save"}:
        reasons.append("objective_action_outside_post_contact_rubric")
    elif family == "move_to_adjacent_zone":
        if summary["health"] <= low_health:
            label, confidence = "preferred", 0.85
            reasons.append("reset_when_low_health")
        elif summary["alive_difference"] < 0:
            label, confidence = "preferred", 0.80
            reasons.append("reset_when_outnumbered")
        elif summary["health"] >= 85 and summary["alive_difference"] > 0:
            label, confidence = "risky", 0.70
            reasons.append("leave_advantageous_state")
        else:
            reasons.append("movement_tradeoff_unclear")
    elif family == "peek":
        if summary["health"] <= critical_health:
            label, confidence = "risky", 0.90
            reasons.append("reengage_at_critical_health")
        elif summary["alive_difference"] < 0:
            label, confidence = "risky", 0.80
            reasons.append("reengage_when_outnumbered")
        elif summary["health"] >= 75 and summary["visible_enemies"] > 0:
            label, confidence = "preferred", 0.75
            reasons.append("reengage_with_visible_contact_and_health")
        else:
            reasons.append("reengagement_tradeoff_unclear")
    elif family == "hold":
        if summary["health"] <= critical_health:
            label, confidence = "risky", 0.70
            reasons.append("hold_at_critical_health")
        elif summary["alive_difference"] < 0:
            label, confidence = "risky", 0.65
            reasons.append("hold_when_outnumbered")
        elif summary["alive_difference"] > 0 and summary["visible_enemies"] == 0:
            label, confidence = "preferred", 0.70
            reasons.append("hold_with_team_advantage_without_contact")
        else:
            reasons.append("hold_tradeoff_unclear")
    elif family == "use_utility":
        if summary["utility_count"] <= 0:
            reasons.append("no_utility_available")
        elif summary["visible_enemies"] > 0 or summary["alive_difference"] < 0:
            label, confidence = "preferred", 0.65
            reasons.append("utility_when_contact_or_disadvantage_present")
        else:
            reasons.append("utility_timing_unclear")
    else:
        reasons.append("unsupported_action_family")

    if label not in ALL_LABELS:
        raise AssertionError(f"invalid candidate label: {label}")
    return {
        "action": str(action),
        "label": label,
        "confidence": confidence,
        "reason_codes": reasons,
        "rubric_version": CANDIDATE_RUBRIC_VERSION,
    }


def label_candidate_row(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return one compact rubric label per legal candidate action."""

    if not isinstance(row, Mapping):
        raise TypeError("candidate state must be a mapping")
    key = candidate_decision_key(row)
    event = row.get("event")
    event = event if isinstance(event, Mapping) else {}
    decision_id = "|".join(key)
    labels: list[dict[str, Any]] = []
    action_names = [str(action) for action in row.get("legal_actions") or ()]
    summary, _team = _state_summary(row)
    scored = {
        action: _rubric_score(summary, action)[0]
        for action in action_names
        if summary and _rubric_score(summary, action)[0] is not None
    }
    spread = max(scored.values()) - min(scored.values()) if len(scored) >= 2 else 0.0
    top_score = max(scored.values()) if scored else None
    bottom_score = min(scored.values()) if scored else None
    for action in action_names:
        raw_score, raw_reasons = _rubric_score(summary, action) if summary else (None, ["missing_pre_event_state"])
        if raw_score is None:
            label = "unknown"
            confidence = 0.0
            reasons = raw_reasons
        elif spread >= MIN_RUBRIC_SPREAD and raw_score == top_score:
            label = "preferred"
            confidence = min(0.95, 0.65 + spread)
            reasons = ["highest_relative_rubric_score", *raw_reasons]
        elif spread >= MIN_RUBRIC_SPREAD and raw_score == bottom_score:
            label = "risky"
            confidence = min(0.95, 0.65 + spread)
            reasons = ["lowest_relative_rubric_score", *raw_reasons]
        else:
            label = "unknown"
            confidence = 0.0
            reasons = ["relative_action_tradeoff_unclear", *raw_reasons]
        labels.append(
            {
                "schema_version": CANDIDATE_LABEL_SCHEMA_VERSION,
                "decision_id": decision_id,
                "group_id": key[0],
                "event_id": key[1],
                "actor_id": key[2],
                "source": row.get("source"),
                "decision_tick": row.get("decision_tick"),
                    "action": action,
                "label": label,
                "confidence": confidence,
                "rubric_score": raw_score,
                "reason_codes": list(dict.fromkeys(reasons)),
                "rubric_version": CANDIDATE_RUBRIC_VERSION,
                "knowledge_boundary": {
                    "cutoff_tick": row.get("decision_tick"),
                    "state_policy": "serialized_pre_event_state_only",
                    "post_event_outcomes_excluded": True,
                },
            }
        )
    return labels


def extract_candidate_labels(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Build a compact JSON-compatible label report from candidate states."""

    output: list[dict[str, Any]] = []
    for row in rows:
        output.extend(label_candidate_row(row))
    counts = Counter(str(row["label"]) for row in output)
    return {
        "schema_version": CANDIDATE_LABEL_SCHEMA_VERSION,
        "rubric_version": CANDIDATE_RUBRIC_VERSION,
        "label_semantics": "pre_event_suitability_weak_labels",
        "summary": {
            "candidate_state_count": len({row["decision_id"] for row in output}),
            "label_row_count": len(output),
            "label_counts": dict(sorted(counts.items())),
            "trainable_label_rows": sum(counts[label] for label in TRAINING_LABELS),
        },
        "rows": output,
    }


def load_candidate_labels(path: str | Path) -> list[dict[str, Any]]:
    """Load a label report or JSONL label sidecar."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"candidate label input is empty: {source}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(payload, Mapping):
        if payload.get("schema_version") != CANDIDATE_LABEL_SCHEMA_VERSION:
            raise ValueError("candidate label report has an unsupported schema")
        rows = payload.get("rows") or ()
    elif isinstance(payload, list):
        rows = payload
    else:
        raise TypeError("candidate labels must be a report object or JSONL rows")
    output = []
    for row in rows:
        if not isinstance(row, Mapping) or row.get("schema_version") != CANDIDATE_LABEL_SCHEMA_VERSION:
            raise ValueError("candidate label row has an unsupported schema")
        if row.get("label") not in ALL_LABELS:
            raise ValueError(f"candidate label is unsupported: {row.get('label')!r}")
        output.append(dict(row))
    return output


def write_candidate_labels(
    candidate_states_path: str | Path,
    output_path: str | Path,
    *,
    output_format: str | None = None,
) -> dict[str, Any]:
    """Generate a label sidecar atomically from candidate-state JSON/JSONL."""

    report = extract_candidate_labels(load_candidate_rows(candidate_states_path))
    output = Path(output_path)
    fmt = (output_format or ("jsonl" if output.suffix.lower() == ".jsonl" else "json")).lower()
    if fmt not in {"json", "jsonl"}:
        raise ValueError("output_format must be json or jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.name}.part")
    if fmt == "jsonl":
        payload = "".join(
            json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n"
            for row in report["rows"]
        )
    else:
        payload = json.dumps(report, indent=2) + "\n"
    partial.write_text(payload, encoding="utf-8")
    partial.replace(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_states", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--format", choices=("json", "jsonl"), default=None)
    args = parser.parse_args()
    report = write_candidate_labels(args.candidate_states, args.output, output_format=args.format)
    print(json.dumps(report["summary"], sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ALL_LABELS",
    "CANDIDATE_LABEL_SCHEMA_VERSION",
    "CANDIDATE_RUBRIC_VERSION",
    "MIN_RUBRIC_SPREAD",
    "TRAINING_LABELS",
    "candidate_decision_key",
    "extract_candidate_labels",
    "label_candidate_action",
    "label_candidate_row",
    "load_candidate_labels",
    "main",
    "write_candidate_labels",
]

"""Small, inspectable statistical model for player engagements.

This model estimates observed engagement outcomes rather than claiming to
prove that a different action would have been better.  It is deliberately
dependency-free and can serve as the runtime fallback while optional
LightGBM engagement heads are trained.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ENGAGEMENT_SCHEMA_VERSION = "engagement_model_v1"
_TARGETS = (
    "kill",
    "death",
    "trade",
    "survival",
    "damage",
    "round_win",
    "survived_after_kill",
)


def _text(value: Any, default: str = "unknown") -> str:
    return str(value if value not in (None, "") else default).strip().lower()


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _label(value: Any) -> bool | None:
    """Parse JSONL booleans without treating the string ``"false"`` as true."""

    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"", "none", "null", "unknown", "nan"}:
        return None
    if text in {"0", "false", "no", "dead", "negative"}:
        return False
    if text in {"1", "true", "yes", "alive", "positive"}:
        return True
    return bool(value)


def engagement_state_key(row: Mapping[str, Any]) -> str:
    """Create a stable, low-cardinality state key from pre-event fields."""

    features = row.get("features")
    features = features if isinstance(features, Mapping) else {}
    legacy = (
        _text(row.get("map_name")),
        _text(row.get("side")),
        _text(row.get("role")),
        _text(features.get("anchor_kind")),
        _text(features.get("weapon")),
        str(round(_number(row.get("horizon_seconds"), 5.0), 2)),
    )
    action = _text(row.get("observed_action"), "unknown")
    if str(row.get("schema_version") or "") != "engagement_windows_v2" and action == "unknown":
        return "|".join(legacy)
    if action.startswith(("move_to_", "move_to_adjacent_zone")):
        action = "move"
    health_bucket = int(max(0.0, min(100.0, _number(features.get("health")))) // 25)
    return "|".join(
        (
            _text(row.get("map_name")),
            _text(row.get("side")),
            _text(row.get("role")),
            action,
            _text(features.get("zone")),
            str(health_bucket),
            str(round(_number(row.get("horizon_seconds"), 5.0), 2)),
        )
    )


def _hierarchical_state_keys(row: Mapping[str, Any]) -> list[tuple[str, str]]:
    exact = engagement_state_key(row)
    parts = exact.split("|")
    if len(parts) != 7:
        return [(exact, "legacy")]
    map_name, side, role, action, _zone, _health, horizon = parts
    return [
        (exact, "exact"),
        (f"{map_name}|{side}|{role}|{action}|*|*|{horizon}", "map_side_role_action"),
        (f"{map_name}|{side}|*|{action}|*|*|{horizon}", "map_side_action"),
        (f"*|{side}|*|{action}|*|*|{horizon}", "side_action"),
        (f"*|*|*|{action}|*|*|{horizon}", "global_action"),
    ]


def _legacy_state_key(row: Mapping[str, Any]) -> str:
    features = row.get("features")
    features = features if isinstance(features, Mapping) else {}
    return "|".join(
        (
            _text(row.get("map_name")),
            _text(row.get("side")),
            _text(row.get("role")),
            _text(features.get("anchor_kind")),
            _text(features.get("weapon")),
            str(round(_number(row.get("horizon_seconds"), 5.0), 2)),
        )
    )


@dataclass(frozen=True, slots=True)
class EngagementPrediction:
    kill_probability: float
    death_probability: float
    trade_probability: float
    survival_probability: float | None
    damage_probability: float | None
    round_win_probability: float | None
    round_value_delta: float | None
    sample_count: int
    confidence: float
    entropy: float
    supported: bool
    state_key: str
    support_level: str


class EngagementModel:
    """Beta-smoothed outcome table for leakage-safe engagement windows."""

    def __init__(self, *, alpha: float = 1.0, min_support: int = 5) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        if min_support < 0:
            raise ValueError("min_support cannot be negative")
        self.alpha = float(alpha)
        self.min_support = int(min_support)
        self._counts: dict[str, dict[str, list[float]]] = {}
        self._deltas: dict[str, list[float]] = {}
        self._global_counts: dict[str, list[float]] = {
            target: [0.0, 0.0] for target in _TARGETS
        }

    @property
    def state_count(self) -> int:
        return len(self._counts)

    @property
    def observation_count(self) -> int:
        return sum(
            int(values["count"][0])
            for key, values in self._counts.items()
            if "*" not in key
        )

    def observe(self, row: Mapping[str, Any]) -> None:
        parsed_labels: dict[str, bool | None] = {}
        for target in _TARGETS:
            value = row.get(f"label_{target}")
            if value is None and target == "survived_after_kill":
                value = row.get(target)
            parsed_labels[target] = _label(value)
        keys = _hierarchical_state_keys(row)
        for key, _level in keys:
            state = self._counts.setdefault(
                key,
                {
                    "count": [0.0],
                    **{target: [0.0, 0.0] for target in _TARGETS},
                },
            )
            state["count"][0] += 1.0
            for target, label in parsed_labels.items():
                if label is None:
                    continue
                state[target][0] += 1.0 if label else 0.0
                state[target][1] += 0.0 if label else 1.0
        for target, label in parsed_labels.items():
            if label is None:
                continue
            self._global_counts[target][0] += 1.0 if label else 0.0
            self._global_counts[target][1] += 0.0 if label else 1.0
        delta = row.get("round_value_delta")
        if delta is not None:
            value = _number(delta, float("nan"))
            if math.isfinite(value):
                for key, _level in keys:
                    self._deltas.setdefault(key, []).append(value)

    def _probability(self, state: dict[str, list[float]], target: str) -> float:
        successes, failures = state.get(target, [0.0, 0.0])
        local = (successes + self.alpha) / (successes + failures + 2.0 * self.alpha)
        global_successes, global_failures = self._global_counts[target]
        global_probability = (global_successes + self.alpha) / (
            global_successes + global_failures + 2.0 * self.alpha
        )
        support = successes + failures
        # Trades and post-kill survival are sparse labels.  They need a
        # stronger hierarchical prior than common kill/death labels or the
        # state table will overfit a single scrim/demo.
        shrinkage = max(1, self.min_support)
        if target in {"trade", "survived_after_kill"}:
            shrinkage = max(shrinkage, 200)
        weight = support / (support + shrinkage)
        return weight * local + (1.0 - weight) * global_probability

    @staticmethod
    def _entropy(probabilities: list[float]) -> float:
        if not probabilities:
            return 1.0
        values: list[float] = []
        for probability in probabilities:
            p = min(1.0 - 1e-12, max(1e-12, probability))
            values.append(-(p * math.log2(p) + (1.0 - p) * math.log2(1.0 - p)))
        return sum(values) / len(values)

    def predict(self, row: Mapping[str, Any]) -> EngagementPrediction:
        key = engagement_state_key(row)
        support_level = "unseen"
        state = None
        available: list[tuple[int, str, str, dict[str, list[float]]]] = []
        for candidate_key, level in _hierarchical_state_keys(row):
            candidate_state = self._counts.get(candidate_key)
            if candidate_state is None:
                continue
            support = int(candidate_state.get("count", [0.0])[0])
            available.append((support, candidate_key, level, candidate_state))
            if support >= self.min_support:
                key, support_level, state = candidate_key, level, candidate_state
                break
        if state is None and available:
            _support, key, support_level, state = max(available, key=lambda item: item[0])
        if state is None:
            legacy_key = _legacy_state_key(row)
            state = self._counts.get(legacy_key)
            if state is not None:
                key, support_level = legacy_key, "legacy"
        if state is None:
            state = {
                "count": [0.0],
                **{target: [0.0, 0.0] for target in _TARGETS},
            }
        probabilities = [self._probability(state, target) for target in ("kill", "death", "trade")]
        survival_values = self._deltas.get(key, [])
        survival_counts = state.get("survival", [0.0, 0.0])
        survival_probability = (
            self._probability(state, "survival")
            if sum(survival_counts) > 0 or sum(self._global_counts["survival"]) > 0
            else 1.0 - probabilities[1]
        )
        damage_counts = state.get("damage", [0.0, 0.0])
        round_win_counts = state.get("round_win", [0.0, 0.0])
        damage_probability = (
            self._probability(state, "damage")
            if sum(damage_counts) > 0 or sum(self._global_counts["damage"]) > 0
            else None
        )
        round_win_probability = (
            self._probability(state, "round_win")
            if sum(round_win_counts) > 0 or sum(self._global_counts["round_win"]) > 0
            else None
        )
        round_value_delta = sum(survival_values) / len(survival_values) if survival_values else None
        sample_count = int(state["count"][0])
        confidence = sample_count / (sample_count + 2.0 * self.alpha)
        return EngagementPrediction(
            kill_probability=probabilities[0],
            death_probability=probabilities[1],
            trade_probability=probabilities[2],
            survival_probability=survival_probability,
            damage_probability=damage_probability,
            round_win_probability=round_win_probability,
            round_value_delta=round_value_delta,
            sample_count=sample_count,
            confidence=confidence,
            entropy=self._entropy(probabilities),
            supported=sample_count >= self.min_support,
            state_key=key,
            support_level=support_level,
        )

    def predict_dict(self, row: Mapping[str, Any]) -> dict[str, Any]:
        prediction = self.predict(row)
        return {
            "kill_probability": prediction.kill_probability,
            "death_probability": prediction.death_probability,
            "trade_probability": prediction.trade_probability,
            "survival_probability": prediction.survival_probability,
            "damage_probability": prediction.damage_probability,
            "round_win_probability": prediction.round_win_probability,
            "round_value_delta": prediction.round_value_delta,
            "sample_count": prediction.sample_count,
            "confidence": prediction.confidence,
            "entropy": prediction.entropy,
            "supported": prediction.supported,
            "state_key": prediction.state_key,
            "support_level": prediction.support_level,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": ENGAGEMENT_SCHEMA_VERSION,
            "alpha": self.alpha,
            "min_support": self.min_support,
            "counts": self._counts,
            "deltas": self._deltas,
            "global_counts": self._global_counts,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> EngagementModel:
        if payload.get("schema_version") != ENGAGEMENT_SCHEMA_VERSION:
            raise ValueError("unsupported engagement model schema version")
        model = cls(
            alpha=float(payload.get("alpha", 1.0)),
            min_support=int(payload.get("min_support", 5)),
        )
        counts = payload.get("counts") or {}
        if not isinstance(counts, Mapping):
            raise TypeError("engagement model counts must be an object")
        model._counts = {
            str(key): {str(target): [float(value) for value in values] for target, values in state.items()}
            for key, state in counts.items()
            if isinstance(state, Mapping)
        }
        for state in model._counts.values():
            state.setdefault("count", [0.0])
            for target in _TARGETS:
                state.setdefault(target, [0.0, 0.0])
        global_counts = payload.get("global_counts") or {}
        if isinstance(global_counts, Mapping):
            model._global_counts = {
                target: [float(value) for value in values]
                for target, values in global_counts.items()
                if target in _TARGETS and isinstance(values, list) and len(values) == 2
            }
        for target in _TARGETS:
            model._global_counts.setdefault(target, [0.0, 0.0])
        if not any(sum(values) for values in model._global_counts.values()):
            for state in model._counts.values():
                for target in _TARGETS:
                    if target in state:
                        model._global_counts[target][0] += float(state[target][0])
                        model._global_counts[target][1] += float(state[target][1])
        deltas = payload.get("deltas") or {}
        if isinstance(deltas, Mapping):
            model._deltas = {
                str(key): [float(value) for value in values]
                for key, values in deltas.items()
                if isinstance(values, list)
            }
        return model

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.part")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        temporary.replace(destination)

    @classmethod
    def load(cls, path: str | Path) -> EngagementModel:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("engagement model must be a JSON object")
        return cls.from_dict(payload)


__all__ = [
    "ENGAGEMENT_SCHEMA_VERSION",
    "EngagementModel",
    "EngagementPrediction",
    "engagement_state_key",
]

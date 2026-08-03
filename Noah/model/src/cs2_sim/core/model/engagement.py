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
_TARGETS = ("kill", "death", "trade", "survived_after_kill")


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
    round_value_delta: float | None
    sample_count: int
    confidence: float
    entropy: float
    supported: bool


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
        return sum(int(values["count"][0]) for values in self._counts.values())

    def observe(self, row: Mapping[str, Any]) -> None:
        key = engagement_state_key(row)
        state = self._counts.setdefault(
            key,
            {
                "count": [0.0],
                **{target: [0.0, 0.0] for target in _TARGETS},
            },
        )
        state["count"][0] += 1.0
        for target in _TARGETS:
            label = row.get(f"label_{target}")
            if label is None and target == "survived_after_kill":
                label = row.get(target)
            label = _label(label)
            if label is None:
                continue
            state[target][0] += 1.0 if bool(label) else 0.0
            state[target][1] += 0.0 if bool(label) else 1.0
            self._global_counts[target][0] += 1.0 if bool(label) else 0.0
            self._global_counts[target][1] += 0.0 if bool(label) else 1.0
        delta = row.get("round_value_delta")
        if delta is not None:
            value = _number(delta, float("nan"))
            if math.isfinite(value):
                self._deltas.setdefault(key, []).append(value)

    def _probability(self, state: dict[str, list[float]], target: str) -> float:
        successes, failures = state[target]
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
        state = self._counts.get(key)
        if state is None:
            state = {
                "count": [0.0],
                **{target: [0.0, 0.0] for target in _TARGETS},
            }
        probabilities = [self._probability(state, target) for target in _TARGETS[:3]]
        survival_values = self._deltas.get(key, [])
        survival_probability = self._probability(state, "survived_after_kill") if state["survived_after_kill"] != [0.0, 0.0] else None
        round_value_delta = sum(survival_values) / len(survival_values) if survival_values else None
        sample_count = int(state["count"][0])
        confidence = sample_count / (sample_count + 2.0 * self.alpha)
        return EngagementPrediction(
            kill_probability=probabilities[0],
            death_probability=probabilities[1],
            trade_probability=probabilities[2],
            survival_probability=survival_probability,
            round_value_delta=round_value_delta,
            sample_count=sample_count,
            confidence=confidence,
            entropy=self._entropy(probabilities),
            supported=sample_count >= self.min_support,
        )

    def predict_dict(self, row: Mapping[str, Any]) -> dict[str, Any]:
        prediction = self.predict(row)
        return {
            "kill_probability": prediction.kill_probability,
            "death_probability": prediction.death_probability,
            "trade_probability": prediction.trade_probability,
            "survival_probability": prediction.survival_probability,
            "round_value_delta": prediction.round_value_delta,
            "sample_count": prediction.sample_count,
            "confidence": prediction.confidence,
            "entropy": prediction.entropy,
            "supported": prediction.supported,
            "state_key": engagement_state_key(row),
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

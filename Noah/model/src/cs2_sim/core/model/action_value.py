"""Compact action-frequency model for inferred replay actions."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable


class ActionFrequencyModel:
    """Dirichlet-smoothed action probabilities conditioned on a state key."""

    def __init__(self, *, alpha: float = 1.0) -> None:
        if alpha <= 0:
            raise ValueError("alpha must be positive")
        self.alpha = alpha
        self._counts: dict[str, dict[str, int]] = {}

    def observe(self, state_key: str, action: str) -> None:
        state = self._counts.setdefault(str(state_key), {})
        action_key = str(action)
        state[action_key] = state.get(action_key, 0) + 1

    @property
    def state_count(self) -> int:
        return len(self._counts)

    @property
    def actions(self) -> tuple[str, ...]:
        return tuple(sorted({action for values in self._counts.values() for action in values}))

    def score_actions(self, state_key: str, legal_actions: Iterable[str]) -> dict[str, float]:
        actions = tuple(dict.fromkeys(str(action) for action in legal_actions))
        if not actions:
            raise ValueError("legal_actions cannot be empty")
        counts = self._counts.get(str(state_key), {})
        total = sum(counts.get(action, 0) for action in actions)
        denominator = total + self.alpha * len(actions)
        return {
            action: (counts.get(action, 0) + self.alpha) / denominator
            for action in actions
        }

    def choose_action(self, state_key: str, legal_actions: Iterable[str]) -> str:
        scores = self.score_actions(state_key, legal_actions)
        return max(scores, key=lambda action: (scores[action], action))

    def normalized_entropy(self, state_key: str, legal_actions: Iterable[str]) -> float:
        scores = self.score_actions(state_key, legal_actions)
        if len(scores) <= 1:
            return 0.0
        entropy = -sum(probability * math.log2(probability) for probability in scores.values() if probability > 0)
        return entropy / math.log2(len(scores))

    def to_dict(self) -> dict[str, object]:
        return {"version": 1, "alpha": self.alpha, "counts": self._counts}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ActionFrequencyModel":
        model = cls(alpha=float(payload.get("alpha", 1.0)))
        model._counts = {
            str(state): {str(action): int(count) for action, count in values.items()}
            for state, values in (payload.get("counts") or {}).items()
        }
        return model

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> "ActionFrequencyModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

"""Small, dependency-free statistical policy.

This model is intended for the current compact dataset and simulator.  It uses
Dirichlet-smoothed action counts plus Beta-smoothed action outcomes, so it can
make a safe prediction even when a state has only a few observations.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ...actions import Action
from ...bayesian_policy import BayesianPolicy
from ...policy import ActionPolicy
from ...state import GameState


class SmallStatisticalModel(ActionPolicy):
    """Fast action scorer for small data and offline simulation."""

    def __init__(
        self,
        *,
        alpha: float = 1.0,
        beta: float = 1.0,
        action_alpha: float = 1.0,
    ) -> None:
        if alpha <= 0 or beta <= 0 or action_alpha <= 0:
            raise ValueError("smoothing parameters must be positive")
        self.alpha = alpha
        self.beta = beta
        self.action_alpha = action_alpha
        self._action_counts: dict[str, dict[str, int]] = {}
        self._outcomes: dict[str, dict[str, list[int]]] = {}
        self._backoff_counts: dict[str, dict[str, int]] = {}
        self._backoff_outcomes: dict[str, dict[str, list[int]]] = {}

    @staticmethod
    def _backoff_keys(state_key: str) -> tuple[tuple[str, float], ...]:
        """Return progressively broader state keys and their support weights."""

        parts = state_key.split("|")
        if len(parts) != 5:
            return ()
        team, zone, _time, _alive_difference, bomb = parts
        return (
            (state_key, 1.0),
            (f"{team}|{zone}|*|*|{bomb}", 0.5),
            (f"{team}|*|*|*|{bomb}", 0.25),
            (f"{team}|*|*|*|*", 0.1),
            ("*|*|*|*|*", 0.05),
        )

    @staticmethod
    def _add_counts(target: dict[str, dict[str, int]], key: str, row: dict[str, int]) -> None:
        bucket = target.setdefault(key, {})
        for action, count in row.items():
            bucket[action] = bucket.get(action, 0) + int(count)

    @staticmethod
    def _add_outcomes(
        target: dict[str, dict[str, list[int]]],
        key: str,
        row: dict[str, list[int]],
    ) -> None:
        bucket = target.setdefault(key, {})
        for action, values in row.items():
            current = bucket.setdefault(action, [0, 0])
            current[0] += int(values[0])
            current[1] += int(values[1])

    def _rebuild_backoff(self) -> None:
        self._backoff_counts = {}
        self._backoff_outcomes = {}
        for state_key, row in self._action_counts.items():
            for key, _weight in self._backoff_keys(state_key)[1:]:
                self._add_counts(self._backoff_counts, key, row)
        for state_key, row in self._outcomes.items():
            for key, _weight in self._backoff_keys(state_key)[1:]:
                self._add_outcomes(self._backoff_outcomes, key, row)

    def _observe_backoff(self, state_key: str, action_key: str, success: bool | None) -> None:
        for key, _weight in self._backoff_keys(state_key)[1:]:
            counts = self._backoff_counts.setdefault(key, {})
            counts[action_key] = counts.get(action_key, 0) + 1
            if success is not None:
                outcomes = self._backoff_outcomes.setdefault(key, {})
                values = outcomes.setdefault(action_key, [0, 0])
                values[0 if success else 1] += 1

    def _lookup(
        self,
        state: GameState,
        player_id: str,
    ) -> tuple[dict[str, int], dict[str, list[int]], str, float]:
        state_key = self.state_key(state, player_id)
        for key, weight in self._backoff_keys(state_key):
            if key == state_key:
                counts = self._action_counts.get(key, {})
                outcomes = self._outcomes.get(key, {})
            else:
                counts = self._backoff_counts.get(key, {})
                outcomes = self._backoff_outcomes.get(key, {})
            if counts:
                return counts, outcomes, key, weight
        return {}, {}, state_key, 0.0

    def action_support_info(self, state: GameState, player_id: str) -> dict[str, Any]:
        """Return effective support and the exact/backoff level used."""

        counts, _outcomes, key, weight = self._lookup(state, player_id)
        raw_support = sum(counts.values())
        return {
            "support": round(raw_support * weight),
            "raw_support": raw_support,
            "level": "exact" if weight == 1.0 else "backoff" if weight else "unseen",
            "state_key": key,
        }

    def action_support(self, state: GameState, player_id: str) -> int:
        return int(self.action_support_info(state, player_id)["support"])

    def outcome_counts(self, state: GameState, player_id: str, action: Action) -> tuple[int, int] | None:
        _counts, outcomes, _key, _weight = self._lookup(state, player_id)
        values = outcomes.get(self.action_key(action))
        if values is None:
            return None
        return int(values[0]), int(values[1])

    @staticmethod
    def state_key(state: GameState, player_id: str) -> str:
        return BayesianPolicy.state_key(state, player_id)

    @staticmethod
    def action_key(action: Action) -> str:
        return BayesianPolicy.action_key(action)

    def observe(
        self,
        state: GameState,
        player_id: str,
        action: Action,
        *,
        success: bool | None = None,
    ) -> None:
        """Add an action observation and optionally its outcome label."""

        state_key = self.state_key(state, player_id)
        action_key = self.action_key(action)
        counts = self._action_counts.setdefault(state_key, {})
        counts[action_key] = counts.get(action_key, 0) + 1
        self._observe_backoff(state_key, action_key, success)
        if success is not None:
            outcomes = self._outcomes.setdefault(state_key, {})
            row = outcomes.setdefault(action_key, [0, 0])
            row[0 if success else 1] += 1

    def score_actions(
        self,
        state: GameState,
        player_id: str,
        legal: Iterable[Action],
    ) -> dict[Action, float]:
        legal_actions = tuple(legal)
        if not legal_actions:
            raise ValueError(f"no legal actions for {player_id}")
        counts, outcomes, _state_key, _weight = self._lookup(state, player_id)
        total = sum(counts.get(self.action_key(action), 0) for action in legal_actions)
        denominator = total + self.action_alpha * len(legal_actions)

        scores: dict[Action, float] = {}
        for action in legal_actions:
            key = self.action_key(action)
            count = counts.get(key, 0)
            action_probability = (count + self.action_alpha) / denominator
            wins, losses = outcomes.get(key, [0, 0])
            outcome_probability = (wins + self.alpha) / (
                wins + losses + self.alpha + self.beta
            )
            # Outcomes are more useful than imitation counts, but counts keep
            # the model sensible before outcome labels are available.
            scores[action] = 0.75 * outcome_probability + 0.25 * action_probability
        return scores

    def normalized_entropy(
        self,
        state: GameState,
        player_id: str,
        legal: Iterable[Action],
    ) -> float:
        """Return action-distribution entropy in the range [0, 1]."""

        scores = self.score_actions(state, player_id, legal)
        total = sum(scores.values())
        if len(scores) <= 1 or total <= 0:
            return 0.0
        probabilities = (score / total for score in scores.values())
        entropy = -sum(p * math.log2(p) for p in probabilities if p > 0)
        return entropy / math.log2(len(scores))

    def choose_action(self, state: GameState, player_id: str, legal: tuple[Action, ...]) -> Action:
        scores = self.score_actions(state, player_id, legal)
        return max(scores, key=lambda action: (scores[action], self.action_key(action)))

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serialisable model payload for ensemble bundling."""

        return {
            "version": 1,
            "alpha": self.alpha,
            "beta": self.beta,
            "action_alpha": self.action_alpha,
            "action_counts": self._action_counts,
            "outcomes": self._outcomes,
        }

    @classmethod
    def load(cls, path: str | Path) -> SmallStatisticalModel:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> SmallStatisticalModel:
        """Restore a model from :meth:`to_dict`."""

        model = cls(
            alpha=float(payload["alpha"]),
            beta=float(payload["beta"]),
            action_alpha=float(payload["action_alpha"]),
        )
        model._action_counts = {
            str(state): {str(action): int(count) for action, count in row.items()}
            for state, row in payload.get("action_counts", {}).items()
        }
        model._outcomes = {
            str(state): {
                str(action): [int(values[0]), int(values[1])]
                for action, values in row.items()
            }
            for state, row in payload.get("outcomes", {}).items()
        }
        model._rebuild_backoff()
        return model

"""Small, dependency-free statistical policy.

This model is intended for the current compact dataset and simulator.  It uses
Dirichlet-smoothed action counts plus Beta-smoothed action outcomes, so it can
make a safe prediction even when a state has only a few observations.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable

from ..actions import Action
from ..bayesian_policy import BayesianPolicy
from ..policy import ActionPolicy
from ..state import GameState


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
        state_key = self.state_key(state, player_id)
        counts = self._action_counts.get(state_key, {})
        outcomes = self._outcomes.get(state_key, {})
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
    def load(cls, path: str | Path) -> "SmallStatisticalModel":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "SmallStatisticalModel":
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
        return model

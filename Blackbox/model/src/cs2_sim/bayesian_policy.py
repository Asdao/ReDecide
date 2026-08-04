import json
import random
from collections import defaultdict
from pathlib import Path

from .actions import Action, ActionType
from .policy import ActionPolicy
from .state import GameState


class BayesianPolicy(ActionPolicy):
    """Smoothed action-frequency policy for compact offline models."""

    def __init__(self, counts: dict[str, dict[str, int]] | None = None, seed: int = 0) -> None:
        self._counts: dict[str, dict[str, int]] = defaultdict(dict, counts or {})
        self._random = random.Random(seed)

    @staticmethod
    def state_key(state: GameState, player_id: str) -> str:
        player = state.player(player_id)
        alive_difference = len(state.alive_players(player.team)) - len(
            state.alive_players(player.team.opponent)
        )
        bomb = state.bomb_state.value
        time_bucket = int(state.time_seconds // 10)
        return f"{player.team.value}|{player.zone}|{time_bucket}|{alive_difference}|{bomb}"

    @staticmethod
    def action_key(action: Action | ActionType) -> str:
        if isinstance(action, Action):
            if action.target_zone is not None:
                return f"{action.action_type.value}:{action.target_zone}"
            return action.action_type.value
        return action.value

    def observe(self, state: GameState, player_id: str, action: Action | ActionType) -> None:
        key = self.state_key(state, player_id)
        row = self._counts.setdefault(key, {})
        name = self.action_key(action)
        row[name] = row.get(name, 0) + 1

    def choose_action(
        self,
        state: GameState,
        player_id: str,
        legal: tuple[Action, ...],
    ) -> Action:
        if not legal:
            raise ValueError(f"no legal actions for {player_id}")
        row = self._counts.get(self.state_key(state, player_id), {})
        weights = [
            row.get(self.action_key(action), row.get(action.action_type.value, 0)) + 1
            for action in legal
        ]
        return self._random.choices(legal, weights=weights, k=1)[0]

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self._counts, indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path, seed: int = 0) -> "BayesianPolicy":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(counts=data, seed=seed)

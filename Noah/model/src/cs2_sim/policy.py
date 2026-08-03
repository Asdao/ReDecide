from typing import Protocol

from .actions import Action
from .state import GameState


class ActionPolicy(Protocol):
    def choose_action(
        self,
        state: GameState,
        player_id: str,
        legal: tuple[Action, ...],
    ) -> Action:
        """Choose one action from the legal action list."""


import random

from .actions import Action, ActionType
from .policy import ActionPolicy
from .state import BombState, GameState, Team


class BaselinePolicy(ActionPolicy):
    """Small, explainable policy used before learned behaviour is available."""

    def __init__(self, seed: int = 0) -> None:
        self._random = random.Random(seed)

    def choose_action(
        self,
        state: GameState,
        player_id: str,
        legal: tuple[Action, ...],
    ) -> Action:
        if not legal:
            raise ValueError(f"no legal actions for {player_id}")
        player = state.player(player_id)

        priorities: tuple[ActionType, ...]
        if player.team is Team.T and Action(ActionType.PLANT) in legal:
            priorities = (ActionType.PLANT, ActionType.USE_UTILITY, ActionType.HOLD)
        elif player.team is Team.CT and state.bomb_state is BombState.PLANTED:
            priorities = (ActionType.DEFUSE, ActionType.PEEK, ActionType.HOLD)
        elif player.visible_enemies:
            priorities = (ActionType.PEEK, ActionType.USE_UTILITY, ActionType.HOLD)
        else:
            priorities = (ActionType.MOVE_TO_ADJACENT_ZONE, ActionType.HOLD, ActionType.PEEK)

        for action_type in priorities:
            candidates = [a for a in legal if a.action_type is action_type]
            if candidates:
                return self._random.choice(candidates)
        return legal[0]


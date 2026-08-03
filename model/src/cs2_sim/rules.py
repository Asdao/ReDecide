from .actions import Action, ActionType
from .config import SimConfig
from .state import BombState, GameState, Team


def legal_actions(state: GameState, player_id: str) -> tuple[Action, ...]:
    player = state.player(player_id)
    if not player.alive or state.winner is not None:
        return ()

    actions = [Action(ActionType.HOLD), Action(ActionType.PEEK), Action(ActionType.SAVE)]
    if player.utility_count > 0:
        actions.append(Action(ActionType.USE_UTILITY))

    for zone in state.adjacency.get(player.zone, ()):
        actions.append(Action(ActionType.MOVE_TO_ADJACENT_ZONE, target_zone=zone))

    if (
        player.team is Team.T
        and player.has_bomb
        and state.bomb_state is BombState.CARRIED
        and player.zone == state.bomb_site
    ):
        actions.append(Action(ActionType.PLANT))

    if (
        player.team is Team.CT
        and state.bomb_state is BombState.PLANTED
        and player.zone == state.bomb_site
    ):
        actions.append(Action(ActionType.DEFUSE))

    return tuple(actions)


def round_winner(state: GameState, config: SimConfig) -> Team | None:
    if state.bomb_state is BombState.DETONATED:
        return Team.T
    if state.bomb_state is BombState.DEFUSED:
        return Team.CT
    if not state.alive_players(Team.T):
        return Team.CT if state.bomb_state is not BombState.PLANTED else None
    if not state.alive_players(Team.CT):
        return Team.T
    if state.bomb_state is BombState.PLANTED:
        if state.bomb_time_remaining is not None and state.bomb_time_remaining <= 0:
            return Team.T
        return None
    if state.time_seconds >= config.round_time_seconds:
        return Team.CT
    return None

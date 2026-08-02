"""Stable numeric features shared by the small and full models.

The feature set intentionally only uses information available at the decision
time.  Keeping it in one module prevents the training and inference paths from
silently drifting apart.
"""

from __future__ import annotations

from ._types import ActionLike
from ..actions import ActionType
from ..state import DEFAULT_ADJACENCY, BombState, GameState


_ZONES = tuple(
    sorted(
        {zone for zone, neighbours in DEFAULT_ADJACENCY.items() for zone in (zone, *neighbours)}
    )
)
_BOMB_STATES = tuple(BombState)
_ACTION_TYPES = tuple(ActionType)

FEATURE_NAMES = (
    "health",
    "utility_count",
    "time_seconds",
    "alive_friendly",
    "alive_enemy",
    "alive_difference",
    "visible_enemies",
    "bomb_planted",
    "bomb_time_remaining",
    "player_zone_index",
    "target_zone_index",
    "action_type_index",
    *tuple(bomb_state.value for bomb_state in _BOMB_STATES),
)


def _index(value: object, values: tuple[object, ...]) -> float:
    try:
        return float(values.index(value))
    except ValueError:
        return -1.0


def state_action_features(state: GameState, player_id: str, action: ActionLike) -> list[float]:
    """Return the fixed-width feature vector for one candidate action."""

    player = state.player(player_id)
    friendly = len(state.alive_players(player.team))
    enemy = len(state.alive_players(player.team.opponent))
    bomb_timer = state.bomb_time_remaining
    if bomb_timer is None:
        bomb_timer = 0.0

    values = [
        float(player.health),
        float(player.utility_count),
        float(state.time_seconds),
        float(friendly),
        float(enemy),
        float(friendly - enemy),
        float(len(player.visible_enemies)),
        float(state.bomb_state is BombState.PLANTED),
        float(bomb_timer),
        _index(player.zone, _ZONES),
        _index(action.target_zone, _ZONES),
        _index(action.action_type, _ACTION_TYPES),
    ]
    values.extend(float(state.bomb_state is bomb_state) for bomb_state in _BOMB_STATES)
    return values


def feature_dict(state: GameState, player_id: str, action: ActionLike) -> dict[str, float]:
    """Return named features, useful for debugging and tabular exporters."""

    return dict(zip(FEATURE_NAMES, state_action_features(state, player_id, action), strict=True))

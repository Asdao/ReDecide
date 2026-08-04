from dataclasses import dataclass
from enum import StrEnum

from .config import SimConfig


class ActionType(StrEnum):
    HOLD = "hold"
    PEEK = "peek"
    MOVE_TO_ADJACENT_ZONE = "move_to_adjacent_zone"
    USE_UTILITY = "use_utility"
    PLANT = "plant"
    DEFUSE = "defuse"
    SAVE = "save"


@dataclass(frozen=True, slots=True)
class Action:
    action_type: ActionType
    target_zone: str | None = None


@dataclass(slots=True)
class ActionExecution:
    action: Action
    elapsed_seconds: float = 0.0
    starting_health: int | None = None


def action_duration(action: Action, config: SimConfig) -> float:
    if action.action_type is ActionType.PLANT:
        return config.plant_duration_seconds
    if action.action_type is ActionType.DEFUSE:
        return config.defuse_duration_seconds
    if action.action_type is ActionType.USE_UTILITY:
        return config.utility_duration_seconds
    if action.action_type is ActionType.SAVE:
        return config.action_limit_seconds
    return min(config.action_limit_seconds, 1.0)

from dataclasses import dataclass, field
from enum import StrEnum


class Team(StrEnum):
    CT = "ct"
    T = "t"

    @property
    def opponent(self) -> "Team":
        return Team.T if self is Team.CT else Team.CT


class BombState(StrEnum):
    NONE = "none"
    CARRIED = "carried"
    DROPPED = "dropped"
    PLANTED = "planted"
    DEFUSED = "defused"
    DETONATED = "detonated"


DEFAULT_ADJACENCY: dict[str, tuple[str, ...]] = {
    "T_SPAWN": ("A_MAIN", "B_MAIN", "MID"),
    "A_MAIN": ("T_SPAWN", "A_SITE", "MID"),
    "B_MAIN": ("T_SPAWN", "B_SITE", "MID"),
    "MID": ("T_SPAWN", "A_MAIN", "B_MAIN", "A_SITE", "B_SITE"),
    "A_SITE": ("A_MAIN", "MID", "CT_SPAWN"),
    "B_SITE": ("B_MAIN", "MID", "CT_SPAWN"),
    "CT_SPAWN": ("A_SITE", "B_SITE"),
}


@dataclass(slots=True)
class PlayerState:
    player_id: str
    team: Team
    zone: str
    health: int = 100
    alive: bool = True
    has_bomb: bool = False
    utility_count: int = 2
    visible_enemies: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if not 0 <= self.health <= 100:
            raise ValueError("health must be between 0 and 100")
        if self.health == 0:
            self.alive = False


@dataclass(slots=True)
class GameState:
    players: dict[str, PlayerState]
    bomb_state: BombState = BombState.NONE
    bomb_site: str = "A_SITE"
    bomb_carrier: str | None = None
    bomb_zone: str | None = None
    bomb_time_remaining: float | None = None
    time_seconds: float = 0.0
    winner: Team | None = None
    adjacency: dict[str, tuple[str, ...]] = field(
        default_factory=lambda: dict(DEFAULT_ADJACENCY)
    )

    def __post_init__(self) -> None:
        if self.bomb_carrier is None:
            carriers = [p.player_id for p in self.players.values() if p.has_bomb]
            self.bomb_carrier = carriers[0] if carriers else None
        if self.bomb_state is BombState.PLANTED and self.bomb_time_remaining is None:
            raise ValueError("a planted bomb needs a remaining timer")

    def alive_players(self, team: Team | None = None) -> tuple[PlayerState, ...]:
        return tuple(
            player
            for player in self.players.values()
            if player.alive and (team is None or player.team is team)
        )

    def player(self, player_id: str) -> PlayerState:
        try:
            return self.players[player_id]
        except KeyError as exc:
            raise KeyError(f"unknown player: {player_id}") from exc

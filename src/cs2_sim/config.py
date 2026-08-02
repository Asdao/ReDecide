from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimConfig:
    """Timing and safety limits for the virtual clock."""

    tick_seconds: float = 0.25
    decision_interval_seconds: float = 1.0
    round_time_seconds: float = 115.0
    bomb_time_seconds: float = 40.0
    plant_duration_seconds: float = 3.2
    defuse_duration_seconds: float = 5.0
    utility_duration_seconds: float = 1.0
    action_limit_seconds: float = 3.0

    def __post_init__(self) -> None:
        if self.tick_seconds <= 0:
            raise ValueError("tick_seconds must be positive")
        if self.decision_interval_seconds < self.tick_seconds:
            raise ValueError("decision interval cannot be shorter than a tick")
        if self.round_time_seconds <= 0 or self.bomb_time_seconds <= 0:
            raise ValueError("round and bomb timers must be positive")


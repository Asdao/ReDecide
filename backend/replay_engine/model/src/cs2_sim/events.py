from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class Event:
    time_seconds: float
    kind: str
    player_id: str | None = None
    details: dict[str, str | float | int] = field(default_factory=dict)


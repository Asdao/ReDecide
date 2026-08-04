"""Canonical records shared by extraction, segmentation, and storage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ReplayMetadata:
    replay_id: str
    source_path: str
    demo_file: str
    parser: str
    map_name: str
    tick_rate: float
    checksum: str
    header: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RoundRecord:
    replay_id: str
    round_num: int
    start_tick: int | None
    end_tick: int | None
    winner: str | None
    reason: str | None = None
    bomb_plant_tick: int | None = None
    bomb_site: str | None = None


@dataclass(frozen=True, slots=True)
class EventRecord:
    replay_id: str
    event_id: str
    round_num: int | None
    tick: int | None
    event_type: str
    attacker_id: str | None = None
    victim_id: str | None = None
    actor_id: str | None = None
    side: str | None = None
    site: str | None = None
    weapon: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PlayerTick:
    replay_id: str
    round_num: int
    tick: int
    player_id: str
    player_name: str | None
    side: str | None
    x: float | None
    y: float | None
    z: float | None
    health: int | None
    armor: int | None
    alive: bool | None
    zone: str | None
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReplayRecord:
    metadata: ReplayMetadata
    rounds: tuple[RoundRecord, ...]
    events: tuple[EventRecord, ...]
    player_ticks: tuple[PlayerTick, ...]


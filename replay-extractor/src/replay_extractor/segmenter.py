"""Logical segmentation and heatmap projections for normalized replays."""

from __future__ import annotations

from dataclasses import dataclass

from .models import EventRecord, PlayerTick, ReplayRecord, RoundRecord


@dataclass(frozen=True, slots=True)
class HeatmapPoint:
    replay_id: str
    round_num: int
    tick: int
    player_id: str
    side: str | None
    map_name: str
    cell_x: int | None
    cell_y: int | None
    x: float | None
    y: float | None


@dataclass(frozen=True, slots=True)
class SegmentedReplay:
    replay: ReplayRecord
    rounds: tuple[RoundRecord, ...]
    events: tuple[EventRecord, ...]
    player_ticks: tuple[PlayerTick, ...]
    heatmap_points: tuple[HeatmapPoint, ...]


def segment_replay(replay: ReplayRecord, *, heatmap_cell_size: int = 256) -> SegmentedReplay:
    if heatmap_cell_size <= 0:
        raise ValueError("heatmap_cell_size must be positive")
    ticks = tuple(sorted(replay.player_ticks, key=lambda row: (row.round_num, row.tick, row.player_id)))
    events = tuple(sorted(replay.events, key=lambda row: (row.round_num or -1, row.tick or -1, row.event_id)))
    points = tuple(
        _heatmap_point(replay, row, heatmap_cell_size)
        for row in ticks
        if row.x is not None and row.y is not None
    )
    return SegmentedReplay(replay, replay.rounds, events, ticks, points)


def events_for_round(segments: SegmentedReplay, round_num: int) -> tuple[EventRecord, ...]:
    return tuple(row for row in segments.events if row.round_num == round_num)


def ticks_for_round(segments: SegmentedReplay, round_num: int) -> tuple[PlayerTick, ...]:
    return tuple(row for row in segments.player_ticks if row.round_num == round_num)


def _heatmap_point(replay: ReplayRecord, row: PlayerTick, cell_size: int) -> HeatmapPoint:
    assert row.x is not None and row.y is not None
    return HeatmapPoint(
        replay.metadata.replay_id,
        row.round_num,
        row.tick,
        row.player_id,
        row.side,
        replay.metadata.map_name,
        int(row.x // cell_size),
        int(row.y // cell_size),
        row.x,
        row.y,
    )

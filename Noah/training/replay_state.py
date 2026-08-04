"""Replay snapshot indexing and simulator-state reconstruction helpers.

The analysis harness and candidate-state extractor both need the same small
set of replay interpretation primitives.  Keeping them here gives callers a
dependency-free state boundary: this module only consumes normalized replay
mappings and returns immutable-ish lookup data or a :class:`GameState`.

All lookups are explicitly tick-bounded.  ``strict_before=True`` excludes
same-tick rows, which is required when a kill/event is used as the decision
anchor so that the event outcome cannot leak into the reconstructed state.
"""

from __future__ import annotations

from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Mapping
from typing import Any

from cs2_sim.state import BombState, GameState, PlayerState, Team

DEFAULT_BOMB_TIME_SECONDS = 40.0
UNKNOWN_BOMB_SITE = "UNKNOWN_SITE"


type TickIndex = dict[int, dict[str, tuple[list[int], list[dict[str, Any]]]]]
"""Round -> player identity -> sorted ticks and corresponding snapshot rows."""


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _side(value: Any) -> Team | None:
    text = str(value or "").strip().lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return Team.CT
    if text in {"t", "terrorist"}:
        return Team.T
    return None


def _identity(row: Mapping[str, Any], ordinal: int) -> str:
    for key in ("steamid", "steam_id", "player_steamid", "name", "player_name"):
        if row.get(key) not in (None, ""):
            return str(row[key])
    return f"anonymous:{ordinal}"


def _zone(row: Mapping[str, Any]) -> str:
    return str(row.get("last_place_name") or row.get("place") or row.get("zone") or "unknown")


def nearest_tick_rows(
    record: Mapping[str, Any],
    *,
    round_num: int,
    tick: int,
    strict_before: bool = False,
    tick_index: Mapping[int, Mapping[str, tuple[list[int], list[dict[str, Any]]]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return the latest player snapshot at or before an event.

    If ``strict_before`` is true, a snapshot at ``tick`` is deliberately
    ignored.  Rows are copied so a caller cannot mutate the source replay or
    the cached index through the returned mapping.
    """

    if tick_index is not None:
        output: dict[str, dict[str, Any]] = {}
        for player_id, (ticks, rows) in tick_index.get(round_num, {}).items():
            position = bisect_left(ticks, tick) if strict_before else bisect_right(ticks, tick)
            if position:
                output[player_id] = dict(rows[position - 1])
        return output

    latest: dict[str, tuple[int, dict[str, Any]]] = {}
    for ordinal, row in enumerate(record.get("ticks") or []):
        if not isinstance(row, Mapping) or _int(row.get("round_num")) != round_num:
            continue
        row_tick = _int(row.get("tick"))
        if row_tick < 0 or row_tick > tick or (strict_before and row_tick >= tick):
            continue
        player_id = _identity(row, ordinal)
        previous = latest.get(player_id)
        if previous is None or row_tick >= previous[0]:
            latest[player_id] = (row_tick, dict(row))
    return {player_id: row for player_id, (_, row) in latest.items()}


def build_tick_index(record: Mapping[str, Any]) -> TickIndex:
    """Index one replay's player snapshots for repeated event lookups."""

    grouped: dict[int, dict[str, list[tuple[int, dict[str, Any]]]]] = defaultdict(dict)
    for ordinal, raw in enumerate(record.get("ticks") or ()):
        if not isinstance(raw, Mapping):
            continue
        round_num = _int(raw.get("round_num"))
        tick = _int(raw.get("tick"))
        if round_num < 0 or tick < 0:
            continue
        player_id = _identity(raw, ordinal)
        grouped.setdefault(round_num, {}).setdefault(player_id, []).append((tick, dict(raw)))

    indexed: TickIndex = {}
    for round_num, players in grouped.items():
        indexed[round_num] = {}
        for player_id, values in players.items():
            values.sort(key=lambda item: item[0])
            # Keep the last parser row when duplicate identities share a tick.
            deduplicated: dict[int, dict[str, Any]] = {}
            for tick, row in values:
                deduplicated[tick] = row
            ticks = sorted(deduplicated)
            indexed[round_num][player_id] = (ticks, [deduplicated[tick] for tick in ticks])
    return indexed


def round_start_tick(record: Mapping[str, Any], round_num: int) -> int | None:
    """Return the normalized round start tick, when supplied by the parser."""

    for row in record.get("rounds") or ():
        if not isinstance(row, Mapping) or _int(row.get("round_num")) != round_num:
            continue
        value = _int(row.get("start"), -1)
        return value if value >= 0 else None
    return None


def tick_rate(record: Mapping[str, Any]) -> float:
    """Return a positive parser tick rate, falling back to the CS2 default."""

    header = record.get("header")
    header = header if isinstance(header, Mapping) else {}
    value = _number(header.get("tick_rate") or record.get("tick_rate"), 64.0)
    return value if value > 0 else 64.0


def bomb_state(
    record: Mapping[str, Any],
    *,
    round_num: int,
    tick: int,
    strict_before: bool = False,
) -> tuple[BombState, str, float | None]:
    """Resolve the bomb state using only events visible at ``tick``.

    ``strict_before`` excludes events at the anchor tick.  This matters for
    candidate states reconstructed before a kill or other same-tick event.
    The planted timer is derived from the plant tick instead of resetting to
    the full forty seconds at every later snapshot.
    """

    state = BombState.NONE
    site = UNKNOWN_BOMB_SITE
    event_tick = -1
    plant_tick: int | None = None
    for event in record.get("bomb") or []:
        if not isinstance(event, Mapping):
            continue
        current_tick = _int(event.get("tick"))
        if (
            _int(event.get("round_num")) != round_num
            or current_tick > tick
            or (strict_before and current_tick >= tick)
        ):
            continue
        if current_tick < event_tick:
            continue
        event_tick = current_tick
        name = str(event.get("event") or event.get("type") or "").lower()
        if "plant" in name:
            state = BombState.PLANTED
            plant_tick = current_tick
        elif "defus" in name:
            state = BombState.DEFUSED
            plant_tick = None
        elif "drop" in name:
            state = BombState.DROPPED
            plant_tick = None
        elif "pick" in name or "carry" in name:
            state = BombState.CARRIED
            plant_tick = None
        elif "deton" in name or "explode" in name:
            state = BombState.DETONATED
            plant_tick = None
        site_value = str(event.get("bombsite") or event.get("site") or "").upper()
        if site_value in {"A", "B"}:
            site = f"{site_value}_SITE"
        elif site_value.endswith("A"):
            site = "A_SITE"
        elif site_value.endswith("B"):
            site = "B_SITE"
    if state is not BombState.PLANTED:
        return state, site, None
    rate = tick_rate(record)
    elapsed = 0.0 if plant_tick is None else max(0.0, (tick - plant_tick) / rate)
    return state, site, max(0.0, DEFAULT_BOMB_TIME_SECONDS - elapsed)


def reconstruct_game_state(
    record: Mapping[str, Any],
    *,
    round_num: int,
    tick: int,
    before_event: bool = False,
    tick_index: Mapping[int, Mapping[str, tuple[list[int], list[dict[str, Any]]]]] | None = None,
) -> GameState | None:
    """Build a simulator state, optionally excluding same-tick event outcomes."""

    rows = nearest_tick_rows(
        record,
        round_num=round_num,
        tick=tick,
        strict_before=before_event,
        tick_index=tick_index,
    )
    if before_event and not rows:
        # Without a strictly earlier snapshot, using an event-tick row can
        # leak the kill/death outcome into the candidate state.  The caller
        # must abstain and report missing pre-event evidence instead.
        return None

    players: dict[str, PlayerState] = {}
    for player_id, row in rows.items():
        team = _side(row.get("team_name") or row.get("team") or row.get("side"))
        if team is None:
            continue
        health = max(0, min(100, int(_number(row.get("health"), 100.0))))
        utility = row.get("utility_count", row.get("utility", row.get("grenades", 0)))
        has_bomb = bool(row.get("has_bomb") or row.get("bomb_carrier"))
        players[player_id] = PlayerState(
            player_id=player_id,
            team=team,
            zone=_zone(row),
            health=health,
            alive=bool(row.get("alive", health > 0)),
            has_bomb=has_bomb,
            utility_count=max(0, int(_number(utility))),
        )
    if not players:
        return None

    current_bomb, bomb_site, bomb_time = bomb_state(
        record,
        round_num=round_num,
        tick=tick,
        strict_before=before_event,
    )
    start_tick = round_start_tick(record, round_num)
    rate = tick_rate(record)
    elapsed_seconds = (
        max(0.0, (tick - start_tick) / rate)
        if start_tick is not None
        else max(0.0, tick / rate)
    )
    return GameState(
        players,
        bomb_state=current_bomb,
        bomb_site=bomb_site,
        bomb_time_remaining=bomb_time,
        time_seconds=elapsed_seconds,
    )


# Temporary private aliases keep the extracted module easy to adopt from
# code that used the old helpers while the harness facade is being migrated.
_nearest_tick_rows = nearest_tick_rows
_build_tick_index = build_tick_index
_round_start_tick = round_start_tick
_tick_rate = tick_rate
_bomb_state = bomb_state


__all__ = [
    "BombState",
    "DEFAULT_BOMB_TIME_SECONDS",
    "GameState",
    "PlayerState",
    "Team",
    "TickIndex",
    "UNKNOWN_BOMB_SITE",
    "bomb_state",
    "build_tick_index",
    "nearest_tick_rows",
    "reconstruct_game_state",
    "round_start_tick",
    "tick_rate",
]

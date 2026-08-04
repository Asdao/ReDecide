"""Deterministic replay action labels for the engagement pipeline.

Labels are observations from the short action window after a decision cutoff.
They are not claims that the observed action was strategically optimal.
Parser-specific event names are handled here so the model contract can remain
small and stable.
"""

from __future__ import annotations

import math
from collections import defaultdict
from collections.abc import Iterable, Mapping
from typing import Any

from cs2_sim.action_vocabulary import canonical_action

_UTILITY_WEAPONS = {
    "flashbang",
    "hegrenade",
    "smokegrenade",
    "molotov",
    "incgrenade",
    "decoy",
    "tagrenade",
    "breachcharge",
    "firebomb",
}


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _player_id(row: Mapping[str, Any]) -> str | None:
    for key in (
        "steamid",
        "steam_id",
        "player_steamid",
        "player_steam_id",
        "userid",
        "user_id",
        "player_id",
        "actor_id",
        "attacker_steamid",
        "attacker_id",
        "player_name",
        "name",
    ):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _event_name(name: Any, event: Mapping[str, Any]) -> str:
    return str(event.get("event") or event.get("event_type") or name or "").strip().lower().replace("-", "_")


def _events_in_window(
    record: Mapping[str, Any],
    *,
    round_num: int,
    player_id: str,
    start_tick: int,
    end_tick: int,
    event_index: Mapping[tuple[int, str], list[tuple[str, dict[str, Any]]]] | None = None,
) -> list[tuple[str, dict[str, Any]]]:
    index = event_index if event_index is not None else build_action_event_index(record)
    values = [
        (name, event)
        for name, event in index.get((round_num, player_id), ())
        if start_tick < _int(event.get("tick")) <= end_tick
    ]
    return sorted(values, key=lambda item: _int(item[1].get("tick")))


def build_action_event_index(
    record: Mapping[str, Any],
) -> dict[tuple[int, str], list[tuple[str, dict[str, Any]]]]:
    """Index only parser streams that can provide a precise action label."""

    index: dict[tuple[int, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    streams = record.get("events") or {}
    if isinstance(streams, Mapping):
        for stream_name, stream in streams.items():
            normalized_name = str(stream_name).strip().lower().replace("-", "_")
            if normalized_name not in {"weapon_fire", "bomb_planted", "bomb_defused", "bomb"}:
                continue
            for raw in stream or ():
                if not isinstance(raw, Mapping):
                    continue
                event = dict(raw)
                round_num = _int(event.get("round_num"))
                actor = _player_id(event)
                if round_num < 0 or actor is None or _int(event.get("tick")) < 0:
                    continue
                index[(round_num, actor)].append((_event_name(stream_name, event), event))
    for raw in record.get("bomb") or ():
        if not isinstance(raw, Mapping):
            continue
        event = dict(raw)
        round_num = _int(event.get("round_num"))
        actor = _player_id(event)
        if round_num < 0 or actor is None or _int(event.get("tick")) < 0:
            continue
        index[(round_num, actor)].append((_event_name("bomb", event), event))
    for values in index.values():
        values.sort(key=lambda item: _int(item[1].get("tick")))
    return dict(index)


def _movement_summary(
    series: list[Mapping[str, Any]],
    *,
    decision_tick: int,
    action_end_tick: int,
    tick_rate: float,
) -> tuple[float, float, str | None, str | None]:
    rows = sorted(series, key=lambda row: _int(row.get("tick")))
    before = [row for row in rows if _int(row.get("tick")) <= decision_tick]
    after = [row for row in rows if decision_tick < _int(row.get("tick")) <= action_end_tick]
    if not before or not after:
        return 0.0, 0.0, None, None
    start = before[-1]
    end = after[-1]
    position = lambda row: (
        _number(row.get("X", row.get("x"))),
        _number(row.get("Y", row.get("y"))),
        _number(row.get("Z", row.get("z"))),
    )
    displacement = math.dist(position(start), position(end))
    seconds = max((_int(end.get("tick")) - _int(start.get("tick"))) / max(tick_rate, 1.0), 1.0 / max(tick_rate, 1.0))
    speed = displacement / seconds
    zone = lambda row: str(row.get("place") or row.get("last_place_name") or row.get("zone") or "unknown")
    return displacement, speed, zone(start), zone(end)


def classify_action(
    record: Mapping[str, Any],
    *,
    player_id: str,
    round_num: int,
    decision_tick: int,
    action_end_tick: int,
    tick_series: Iterable[Mapping[str, Any]],
    tick_rate: float,
    movement_threshold_per_second: float = 20.0,
    contact_actor: str | None = None,
    event_index: Mapping[tuple[int, str], list[tuple[str, dict[str, Any]]]] | None = None,
) -> dict[str, Any]:
    """Classify one observed action with evidence and confidence.

    The priority order deliberately prefers exact objective/utility events,
    then a conservative combat-movement heuristic, then movement/hold.
    """

    series = list(tick_series)
    events = _events_in_window(
        record,
        round_num=round_num,
        player_id=player_id,
        start_tick=decision_tick,
        end_tick=action_end_tick,
        event_index=event_index,
    )
    displacement, speed, start_zone, end_zone = _movement_summary(
        series,
        decision_tick=decision_tick,
        action_end_tick=action_end_tick,
        tick_rate=tick_rate,
    )
    movement = speed >= movement_threshold_per_second
    evidence: list[str] = []
    parameters: dict[str, Any] = {}

    if not series and not events:
        return _result("unknown", 0.0, ["no_action_window_observation"], parameters, events)

    for name, event in events:
        if "plant" in name:
            evidence.append("bomb_plant_event")
            return _result("plant", 0.99, evidence, parameters, events, displacement=displacement, speed=speed)
        if "defus" in name:
            evidence.append("bomb_defuse_event")
            return _result("defuse", 0.99, evidence, parameters, events, displacement=displacement, speed=speed)

    for name, event in events:
        weapon = str(event.get("weapon") or event.get("weapon_name") or "").lower().removeprefix("weapon_")
        if "fire" in name and weapon in _UTILITY_WEAPONS:
            parameters["utility_type"] = weapon
            evidence.extend(("weapon_fire_event", "utility_weapon"))
            return _result("use_utility", 0.98, evidence, parameters, events, displacement=displacement, speed=speed)

    if movement:
        if end_zone not in (None, "", "unknown"):
            parameters["target_zone"] = end_zone
        if contact_actor == player_id:
            evidence.extend(("displacement_above_threshold", "contact_initiator"))
            return _result("peek", 0.72, evidence, parameters, events, displacement=displacement, speed=speed)
        evidence.append("displacement_above_threshold")
        if start_zone != end_zone:
            evidence.append("zone_changed")
        return _result(
            "move_to_adjacent_zone",
            0.90 if start_zone != end_zone else 0.70,
            evidence,
            parameters,
            events,
            displacement=displacement,
            speed=speed,
        )

    evidence.append("displacement_below_threshold")
    return _result("hold", 0.88, evidence, parameters, events, displacement=displacement, speed=speed)


def _result(
    action: str,
    confidence: float,
    evidence: list[str],
    parameters: Mapping[str, Any],
    events: Iterable[tuple[str, Mapping[str, Any]]],
    displacement: float = 0.0,
    speed: float = 0.0,
) -> dict[str, Any]:
    return {
        "action": canonical_action(action),
        "action_family": {
            "hold": "stationary",
            "peek": "combat_movement",
            "move_to_adjacent_zone": "movement",
            "use_utility": "utility",
            "plant": "objective",
            "defuse": "objective",
        }.get(action, "unknown"),
        "parameters": dict(parameters),
        "confidence": min(1.0, max(0.0, float(confidence))),
        "evidence": list(dict.fromkeys(evidence)),
        "event_ticks": [_int(event.get("tick")) for _name, event in events],
        "displacement": float(displacement),
        "speed": float(speed),
    }


__all__ = ["build_action_event_index", "classify_action"]

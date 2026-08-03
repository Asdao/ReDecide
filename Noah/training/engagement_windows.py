"""Extract deterministic, leakage-safe combat engagement windows.

The replay schema contains damage and kill events with attacker/victim IDs.
This module turns those events into short, player-centric windows.  A window's
features are computed from the anchor event at ``anchor_tick``; labels only
inspect events with ``anchor_tick < tick <= label_end_tick``.  Consequently a
kill or death at the cutoff cannot leak into its own label.

The labels describe observed outcomes (kill, death, and trade), not whether a
player made a strategically good decision.  They are intentionally additive
to the existing snapshot/action pipelines and do not modify the database.
"""

from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Callable, Iterator
from itertools import pairwise
from pathlib import Path
from typing import Any

from Noah.training.data_paths import DATA_PATHS

SCHEMA_VERSION = "engagement_windows_v2"
DEFAULT_TICK_RATE = 64.0


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _side(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return None


def _event_player(event: dict[str, Any], prefix: str) -> str | None:
    for key in (
        f"{prefix}_steamid",
        f"{prefix}_steam_id",
        f"{prefix}_id",
        f"{prefix}_name",
    ):
        value = event.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _event_round(event: dict[str, Any]) -> int:
    return _int(event.get("round_num"), -1)


def _event_tick(event: dict[str, Any]) -> int:
    return _int(event.get("tick"), -1)


def _real_event(event: dict[str, Any]) -> bool:
    attacker = _event_player(event, "attacker")
    victim = _event_player(event, "victim")
    if not attacker or not victim or attacker == victim:
        return False
    if str(event.get("weapon") or "").strip().lower() == "world":
        return False
    if bool(event.get("is_freeze_period")):
        return False
    return _event_round(event) >= 0 and _event_tick(event) >= 0


def _event_kind(value: Any) -> str:
    text = str(value or "").strip().lower().replace("-", "_")
    if text in {"player_hurt", "hurt", "damage", "damages"}:
        return "damage"
    if text in {"player_death", "death", "kill", "kills"}:
        return "kill"
    return text


def _iter_events(record: dict[str, Any]) -> Iterator[tuple[str, dict[str, Any]]]:
    """Yield de-duplicated damage/kill events from all supported record forms."""

    candidates: list[tuple[str, dict[str, Any]]] = []
    for event in record.get("damages") or []:
        if isinstance(event, dict):
            candidates.append(("damage", event))
    for event in record.get("kills") or []:
        if isinstance(event, dict):
            candidates.append(("kill", event))
    for event_type, values in (record.get("events") or {}).items():
        kind = _event_kind(event_type)
        if kind not in {"damage", "kill"}:
            continue
        for event in values or []:
            if isinstance(event, dict):
                candidates.append((kind, event))

    seen: set[tuple[Any, ...]] = set()
    for kind, event in candidates:
        if not _real_event(event):
            continue
        signature = (
            kind,
            _event_round(event),
            _event_tick(event),
            _event_player(event, "attacker"),
            _event_player(event, "victim"),
            str(event.get("weapon") or ""),
        )
        if signature in seen:
            continue
        seen.add(signature)
        yield kind, event


def _round_end_ticks(record: dict[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    for round_info in record.get("rounds") or []:
        if not isinstance(round_info, dict):
            continue
        number = _int(round_info.get("round_num"), -1)
        end = round_info.get("end")
        if end is None:
            end = round_info.get("official_end")
        if number >= 0 and end is not None:
            value = _int(end, -1)
            if value >= 0:
                result[number] = value
    return result


def _round_start_ticks(record: dict[str, Any]) -> dict[int, int]:
    result: dict[int, int] = {}
    for round_info in record.get("rounds") or []:
        if not isinstance(round_info, dict):
            continue
        number = _int(round_info.get("round_num"), -1)
        value = _int(round_info.get("start"), -1)
        if number >= 0 and value >= 0:
            result[number] = value
    return result


def _round_winners(record: dict[str, Any]) -> dict[int, str | None]:
    result: dict[int, str | None] = {}
    for round_info in record.get("rounds") or []:
        if not isinstance(round_info, dict):
            continue
        number = _int(round_info.get("round_num"), -1)
        if number >= 0:
            result[number] = _side(round_info.get("winner"))
    return result


def _side_for(event: dict[str, Any], prefix: str) -> str | None:
    return _side(event.get(f"{prefix}_side")) or _side(event.get("side"))


def _anchor_feature(event: dict[str, Any], anchor_kind: str) -> dict[str, Any]:
    """Extract only parser fields available at the engagement cutoff."""

    attacker_x = _number(event.get("attacker_X"), 0.0)
    attacker_y = _number(event.get("attacker_Y"), 0.0)
    victim_x = _number(event.get("victim_X"), 0.0)
    victim_y = _number(event.get("victim_Y"), 0.0)
    return {
        "anchor_kind": anchor_kind,
        "weapon": event.get("weapon"),
        "damage_health": _number(event.get("dmg_health_real", event.get("dmg_health")), 0.0),
        "damage_armor": _number(event.get("dmg_armor"), 0.0),
        "distance": _number(event.get("distance"), math.hypot(attacker_x - victim_x, attacker_y - victim_y)),
        "attacker_health": _number(event.get("attacker_health"), 0.0),
        "attacker_armor": _number(event.get("attacker_armor"), 0.0),
        "victim_health": _number(event.get("victim_health"), _number(event.get("health"), 0.0)),
        "victim_armor": _number(event.get("victim_armor"), _number(event.get("armor"), 0.0)),
        "attacker_zone": event.get("attacker_place"),
        "victim_zone": event.get("victim_place"),
        "headshot": bool(event.get("headshot")),
        "through_smoke": bool(event.get("thrusmoke", event.get("through_smoke"))),
    }


def _tick_player(row: dict[str, Any], ordinal: int = 0) -> str | None:
    for key in ("steamid", "steam_id", "player_steamid", "name", "player_name"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None if ordinal < 0 else f"anonymous:{ordinal}"


def _tick_side(row: dict[str, Any]) -> str | None:
    return _side(row.get("side") or row.get("team") or row.get("team_name"))


def _tick_position(row: dict[str, Any]) -> tuple[float, float, float]:
    return (
        _number(row.get("X", row.get("x"))),
        _number(row.get("Y", row.get("y"))),
        _number(row.get("Z", row.get("z"))),
    )


def _tick_zone(row: dict[str, Any]) -> str:
    return str(row.get("place") or row.get("last_place_name") or row.get("zone") or "unknown")


def _tick_alive(row: dict[str, Any]) -> bool:
    if row.get("alive") is not None:
        return str(row.get("alive")).strip().lower() not in {"0", "false", "dead", "no", "none"}
    return _number(row.get("health"), 100.0) > 0


def _tick_index(record: dict[str, Any]) -> dict[tuple[int, str], list[dict[str, Any]]]:
    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for ordinal, row in enumerate(record.get("ticks") or []):
        if not isinstance(row, dict):
            continue
        round_num = _int(row.get("round_num"), -1)
        tick = _int(row.get("tick"), -1)
        player = _tick_player(row, ordinal)
        if round_num >= 0 and tick >= 0 and player:
            grouped[(round_num, player)].append(row)
    for series in grouped.values():
        series.sort(key=lambda row: _event_tick(row))
    return grouped


def _row_at_or_before(series: list[dict[str, Any]], tick: int) -> dict[str, Any] | None:
    if not series:
        return None
    ticks = [_event_tick(row) for row in series]
    index = bisect_right(ticks, tick) - 1
    return series[index] if index >= 0 else None


def _history_features(
    *,
    focal_player: str,
    focal_side: str | None,
    round_num: int,
    decision_tick: int,
    lookback_ticks: int,
    rate: float,
    tick_rows: dict[tuple[int, str], list[dict[str, Any]]],
    round_damages: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build player-centric features using ticks/events no later than cutoff."""

    series = tick_rows.get((round_num, focal_player), [])
    ticks = [_event_tick(row) for row in series]
    start_index = bisect_left(ticks, decision_tick - lookback_ticks)
    end_index = bisect_right(ticks, decision_tick)
    history = series[start_index:end_index]
    current = history[-1] if history else _row_at_or_before(series, decision_tick)
    distance_moved = 0.0
    zone_changes = 0
    for previous, following in pairwise(history):
        p1 = _tick_position(previous)
        p2 = _tick_position(following)
        distance_moved += math.dist(p1, p2)
        zone_changes += int(_tick_zone(previous) != _tick_zone(following))
    elapsed = (
        max(0.0, (_event_tick(history[-1]) - _event_tick(history[0])) / rate)
        if len(history) >= 2
        else 0.0
    )
    recent_damage_dealt = 0.0
    recent_damage_taken = 0.0
    for event in round_damages:
        event_tick = _event_tick(event)
        if not decision_tick - lookback_ticks <= event_tick <= decision_tick:
            continue
        amount = _number(event.get("dmg_health_real", event.get("dmg_health")))
        if _event_player(event, "attacker") == focal_player:
            recent_damage_dealt += amount
        if _event_player(event, "victim") == focal_player:
            recent_damage_taken += amount

    nearest_teammate = math.inf
    nearest_enemy = math.inf
    alive_teammates = 0
    alive_enemies = 0
    if current is not None:
        focal_position = _tick_position(current)
        for (candidate_round, player), candidate_series in tick_rows.items():
            if candidate_round != round_num or player == focal_player:
                continue
            candidate = _row_at_or_before(candidate_series, decision_tick)
            if candidate is None or not _tick_alive(candidate):
                continue
            distance = math.dist(focal_position, _tick_position(candidate))
            if focal_side is not None and _tick_side(candidate) == focal_side:
                alive_teammates += 1
                nearest_teammate = min(nearest_teammate, distance)
            else:
                alive_enemies += 1
                nearest_enemy = min(nearest_enemy, distance)

    first = history[0] if history else current
    inventory = list(current.get("inventory") or []) if current is not None else []
    return {
        "history_available": current is not None,
        "history_sample_count": len(history),
        "lookback_seconds": lookback_ticks / rate,
        "distance_moved": distance_moved,
        "average_speed": distance_moved / elapsed if elapsed > 0 else 0.0,
        "displacement": math.dist(_tick_position(first), _tick_position(current)) if first and current else 0.0,
        "zone_changes": zone_changes,
        "health": _number(current.get("health")) if current else 0.0,
        "armor": _number(current.get("armor_value", current.get("armor"))) if current else 0.0,
        "health_delta": (_number(current.get("health")) - _number(first.get("health"))) if first and current else 0.0,
        "armor_delta": (
            _number(current.get("armor_value", current.get("armor")))
            - _number(first.get("armor_value", first.get("armor")))
        ) if first and current else 0.0,
        "zone": _tick_zone(current) if current else "unknown",
        "inventory_size": len(inventory),
        "has_defuser": bool(current.get("has_defuser")) if current else False,
        "recent_damage_dealt": recent_damage_dealt,
        "recent_damage_taken": recent_damage_taken,
        "alive_teammates": alive_teammates,
        "alive_enemies": alive_enemies,
        "nearest_teammate_distance": 0.0 if math.isinf(nearest_teammate) else nearest_teammate,
        "nearest_enemy_distance": 0.0 if math.isinf(nearest_enemy) else nearest_enemy,
    }


def _observed_action_after_cutoff(
    *,
    series: list[dict[str, Any]],
    decision_tick: int,
    action_end_tick: int,
    rate: float,
    movement_threshold_per_second: float,
) -> tuple[str | None, str | None, float]:
    """Measure the observed movement after the decision; never use it as history."""

    if not series or action_end_tick <= decision_tick:
        return None, None, 0.0
    ticks = [_event_tick(row) for row in series]
    start_index = bisect_right(ticks, decision_tick) - 1
    end_index = bisect_left(ticks, action_end_tick)
    if start_index < 0 or end_index >= len(series) or end_index <= start_index:
        return None, None, 0.0
    start = series[start_index]
    end = series[end_index]
    seconds = max((_event_tick(end) - _event_tick(start)) / rate, 1.0 / rate)
    displacement = math.dist(_tick_position(start), _tick_position(end))
    action = "move" if displacement >= movement_threshold_per_second * seconds else "hold"
    return action, _tick_zone(end), displacement


def _label_for_player(
    focal_player: str,
    focal_side: str | None,
    *,
    anchor_tick: int,
    label_end_tick: int,
    round_kills: list[dict[str, Any]],
    round_damages: list[dict[str, Any]],
    trade_window_ticks: int,
) -> dict[str, Any]:
    future_kills = [
        event
        for event in round_kills
        if anchor_tick < _event_tick(event) <= label_end_tick
    ]
    focal_kill = next(
        (event for event in future_kills if _event_player(event, "attacker") == focal_player),
        None,
    )
    focal_death = next(
        (event for event in future_kills if _event_player(event, "victim") == focal_player),
        None,
    )
    trade_event = None
    if focal_death is not None and focal_side in {"ct", "t"}:
        killer = _event_player(focal_death, "attacker")
        death_tick = _event_tick(focal_death)
        if killer:
            for event in future_kills:
                if not death_tick < _event_tick(event) <= min(label_end_tick, death_tick + trade_window_ticks):
                    continue
                if _event_player(event, "victim") != killer:
                    continue
                if _side_for(event, "attacker") == focal_side:
                    trade_event = event
                    break
    future_damages = [
        event
        for event in round_damages
        if anchor_tick < _event_tick(event) <= label_end_tick
    ]
    damage_dealt = sum(
        _number(event.get("dmg_health_real", event.get("dmg_health")))
        for event in future_damages
        if _event_player(event, "attacker") == focal_player
    )
    damage_taken = sum(
        _number(event.get("dmg_health_real", event.get("dmg_health")))
        for event in future_damages
        if _event_player(event, "victim") == focal_player
    )
    return {
        "label_kill": focal_kill is not None,
        "label_death": focal_death is not None,
        "label_trade": trade_event is not None,
        "label_survival": focal_death is None,
        "label_damage": damage_dealt > 0.0,
        "future_damage_dealt": damage_dealt,
        "future_damage_taken": damage_taken,
        "kill_tick": _event_tick(focal_kill) if focal_kill is not None else None,
        "death_tick": _event_tick(focal_death) if focal_death is not None else None,
        "trade_tick": _event_tick(trade_event) if trade_event is not None else None,
        "outcome": (
            "trade"
            if trade_event is not None
            else "kill"
            if focal_kill is not None
            else "death"
            if focal_death is not None
            else "none"
        ),
    }


def extract_engagement_windows(
    record: dict[str, Any],
    *,
    horizon_seconds: float = 5.0,
    trade_window_seconds: float = 3.0,
    lookback_seconds: float = 3.0,
    decision_lead_seconds: float = 1.0,
    action_window_seconds: float = 1.0,
    movement_threshold_per_second: float = 20.0,
    tick_rate: float | None = None,
    max_windows: int | None = None,
    round_value_predictor: Callable[[dict[str, Any]], float | None] | None = None,
) -> list[dict[str, Any]]:
    """Extract player-centric combat windows with strict future-only labels."""

    if horizon_seconds <= 0 or trade_window_seconds <= 0 or lookback_seconds <= 0:
        raise ValueError("horizon_seconds, trade_window_seconds, and lookback_seconds must be positive")
    if decision_lead_seconds < 0 or action_window_seconds <= 0 or movement_threshold_per_second < 0:
        raise ValueError("decision lead cannot be negative; action window and movement threshold must be valid")
    if max_windows is not None and max_windows <= 0:
        raise ValueError("max_windows must be positive")
    header = record.get("header") or {}
    match = record.get("match") or {}
    rate = _number(tick_rate if tick_rate is not None else header.get("tick_rate") or match.get("tick_rate"), DEFAULT_TICK_RATE)
    if rate <= 0:
        raise ValueError("tick_rate must be positive")
    horizon_ticks = max(1, round(horizon_seconds * rate))
    trade_ticks = max(1, round(trade_window_seconds * rate))
    lookback_ticks = max(1, round(lookback_seconds * rate))
    lead_ticks = max(0, round(decision_lead_seconds * rate))
    action_ticks = max(1, round(action_window_seconds * rate))
    start_ticks = _round_start_ticks(record)
    end_ticks = _round_end_ticks(record)
    winners = _round_winners(record)
    tick_rows = _tick_index(record)
    events = sorted(_iter_events(record), key=lambda item: (_event_round(item[1]), _event_tick(item[1]), item[0]))
    if not events:
        return []
    by_round: dict[int, list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for kind, event in events:
        by_round[_event_round(event)].append((kind, event))
    # Prefer damage contacts. If a replay has no damage table, kill events are
    # still useful anchors, but the anchor kill itself is never its own label.
    contacts = [(kind, event) for kind, event in events if kind == "damage"]
    if not contacts:
        contacts = [(kind, event) for kind, event in events if kind == "kill"]
    anchors: list[tuple[str, dict[str, Any]]] = []
    last_anchor: dict[tuple[int, str, str], int] = {}
    for kind, event in contacts:
        round_num = _event_round(event)
        attacker = _event_player(event, "attacker")
        victim = _event_player(event, "victim")
        if not attacker or not victim:
            continue
        key = (round_num, attacker, victim)
        tick = _event_tick(event)
        if tick - last_anchor.get(key, -10**18) < horizon_ticks:
            continue
        last_anchor[key] = tick
        anchors.append((kind, event))

    output: list[dict[str, Any]] = []
    for anchor_kind, anchor in anchors:
        round_num = _event_round(anchor)
        contact_tick = _event_tick(anchor)
        anchor_tick = max(start_ticks.get(round_num, 0), contact_tick - lead_ticks)
        round_end = end_ticks.get(round_num)
        label_end = anchor_tick + horizon_ticks
        if round_end is not None:
            label_end = min(label_end, round_end)
        if label_end <= anchor_tick:
            continue
        round_kills = [event for kind, event in by_round[round_num] if kind == "kill"]
        round_damages = [event for kind, event in by_round[round_num] if kind == "damage"]
        attacker = _event_player(anchor, "attacker")
        victim = _event_player(anchor, "victim")
        participants = (
            (attacker, _side_for(anchor, "attacker"), victim, "attacker"),
            (victim, _side_for(anchor, "victim"), attacker, "victim"),
        )
        for focal_player, focal_side, opponent, role in participants:
            if focal_player is None:
                continue
            labels = _label_for_player(
                focal_player,
                focal_side,
                anchor_tick=anchor_tick,
                label_end_tick=label_end,
                round_kills=round_kills,
                round_damages=round_damages,
                trade_window_ticks=trade_ticks,
            )
            survived_after_kill = (
                bool(labels["label_kill"] and not labels["label_death"])
                if labels["label_kill"]
                else None
            )
            round_won = (
                winners[round_num] == focal_side
                if winners.get(round_num) in {"ct", "t"} and focal_side in {"ct", "t"}
                else None
            )
            history = _history_features(
                focal_player=focal_player,
                focal_side=focal_side,
                round_num=round_num,
                decision_tick=anchor_tick,
                lookback_ticks=lookback_ticks,
                rate=rate,
                tick_rows=tick_rows,
                round_damages=round_damages,
            )
            observed_action, action_destination, action_displacement = _observed_action_after_cutoff(
                series=tick_rows.get((round_num, focal_player), []),
                decision_tick=anchor_tick,
                action_end_tick=min(contact_tick, anchor_tick + action_ticks),
                rate=rate,
                movement_threshold_per_second=movement_threshold_per_second,
            )
            # Contact fields are safe at a zero-lead cutoff (the historical
            # compatibility mode), but must not leak a future hit when the
            # coaching decision is intentionally placed before contact.
            features = (
                _anchor_feature(anchor, anchor_kind)
                if anchor_tick >= contact_tick
                else {"anchor_kind": f"pre_{anchor_kind}", "weapon": None}
            )
            features.update(history)
            row = {
                "schema_version": SCHEMA_VERSION,
                "source": record.get("source_path") or record.get("demo_file") or "unknown",
                "match_id": record.get("match_id") or (record.get("match") or {}).get("match_id"),
                "map_name": header.get("map_name") or match.get("map_name") or "unknown",
                "round_num": round_num,
                "player_id": focal_player,
                "side": focal_side or "unknown",
                "opponent_id": opponent,
                "role": role,
                "anchor_tick": anchor_tick,
                "contact_tick": contact_tick,
                "decision_lead_seconds": (contact_tick - anchor_tick) / rate,
                "label_end_tick": label_end,
                "horizon_ticks": label_end - anchor_tick,
                "horizon_seconds": (label_end - anchor_tick) / rate,
                "tick_rate": rate,
                "label_cutoff_tick": anchor_tick,
                "label_horizon_ticks": label_end - anchor_tick,
                "label_horizon_seconds": (label_end - anchor_tick) / rate,
                "label_horizon": {
                    "cutoff_tick": anchor_tick,
                    "end_tick": label_end,
                    "ticks": label_end - anchor_tick,
                    "seconds": (label_end - anchor_tick) / rate,
                },
                "features": features,
                "observed_action": observed_action,
                "observed_action_destination": action_destination,
                "observed_action_displacement": action_displacement,
                "survived_after_kill": survived_after_kill,
                "round_won": round_won,
                "label_round_win": round_won,
                "round_value_delta": None,
                **labels,
            }
            if round_value_predictor is not None:
                # Keep outcome labels out of the predictor input as well.  A
                # caller-supplied predictor must not be able to accidentally
                # turn a post-window label into a feature.
                predictor_input = {
                    key: value
                    for key, value in row.items()
                    if not key.startswith("label_")
                    and key
                    not in {
                        "kill_tick",
                        "death_tick",
                        "trade_tick",
                        "contact_tick",
                        "future_damage_dealt",
                        "future_damage_taken",
                        "observed_action_destination",
                        "observed_action_displacement",
                        "outcome",
                        "survived_after_kill",
                        "round_won",
                        "round_value_delta",
                    }
                }
                value = round_value_predictor(predictor_input)
                row["round_value_delta"] = float(value) if value is not None else None
            output.append(row)
            if max_windows is not None and len(output) >= max_windows:
                return output
    return output


def extract_file(
    input_path: Path,
    output_path: Path,
    *,
    horizon_seconds: float = 5.0,
    trade_window_seconds: float = 3.0,
    lookback_seconds: float = 3.0,
    decision_lead_seconds: float = 1.0,
    action_window_seconds: float = 1.0,
    limit: int | None = None,
) -> int:
    """Stream replay JSONL into engagement-window JSONL atomically."""

    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    partial = output_path.with_name(f"{output_path.name}.part")
    try:
        with input_path.open(encoding="utf-8") as source, partial.open("w", encoding="utf-8") as target:
            processed_records = 0
            for line in source:
                if not line.strip():
                    continue
                if limit is not None and processed_records >= limit:
                    break
                processed_records += 1
                record = json.loads(line)
                for row in extract_engagement_windows(
                    record,
                    horizon_seconds=horizon_seconds,
                    trade_window_seconds=trade_window_seconds,
                    lookback_seconds=lookback_seconds,
                    decision_lead_seconds=decision_lead_seconds,
                    action_window_seconds=action_window_seconds,
                ):
                    target.write(json.dumps(row, separators=(",", ":")) + "\n")
                    count += 1
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return count


def _records_from_database(database_path: Path) -> Iterator[dict[str, Any]]:
    """Adapt canonical event rows into record-shaped inputs without writes."""

    from Noah.training.replay_repository import ReplayRepository

    with ReplayRepository(database_path) as repository:
        replay_meta = {
            int(row["replay_id"]): dict(row)
            for row in repository.connection.execute(
                "SELECT replay_id,source_path,map_name,tick_rate,match_id FROM replays"
            )
        }
        events_by_replay: dict[int, list[dict[str, Any]]] = defaultdict(list)
        rounds_by_replay: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for round_info in repository.iter_rounds():
            rounds_by_replay[int(round_info["replay_id"])].append(
                {
                    "round_num": round_info.get("round_num"),
                    "start": round_info.get("start_tick"),
                    "end": round_info.get("end_tick"),
                    "winner": round_info.get("winner"),
                }
            )
        for event in repository.iter_events():
            item = dict(event.get("payload") or {})
            item.update({key: event.get(key) for key in ("round_num", "tick", "event_type") if event.get(key) is not None})
            events_by_replay[int(event["replay_id"])].append(item)
        for replay_id in sorted(events_by_replay):
            meta = replay_meta.get(replay_id, {})
            kills: list[dict[str, Any]] = []
            damages: list[dict[str, Any]] = []
            for event in events_by_replay[replay_id]:
                kind = _event_kind(event.get("event_type"))
                if kind == "kill":
                    kills.append(event)
                elif kind == "damage":
                    damages.append(event)
            yield {
                "source_path": meta.get("source_path") or f"replay:{replay_id}",
                "demo_file": meta.get("source_path") or f"replay:{replay_id}",
                "header": {"map_name": meta.get("map_name"), "tick_rate": meta.get("tick_rate")},
                "match_id": meta.get("match_id"),
                "kills": kills,
                "damages": damages,
                "rounds": rounds_by_replay.get(replay_id, []),
            }


def extract_database(
    database_path: Path,
    output_path: Path,
    *,
    horizon_seconds: float = 5.0,
    trade_window_seconds: float = 3.0,
    lookback_seconds: float = 3.0,
    decision_lead_seconds: float = 1.0,
    action_window_seconds: float = 1.0,
) -> int:
    """Extract windows from canonical SQLite events without rebuilding it."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    partial = output_path.with_name(f"{output_path.name}.part")
    try:
        with partial.open("w", encoding="utf-8") as target:
            for record in _records_from_database(database_path):
                for row in extract_engagement_windows(
                    record,
                    horizon_seconds=horizon_seconds,
                    trade_window_seconds=trade_window_seconds,
                    lookback_seconds=lookback_seconds,
                    decision_lead_seconds=decision_lead_seconds,
                    action_window_seconds=action_window_seconds,
                ):
                    target.write(json.dumps(row, separators=(",", ":")) + "\n")
                    count += 1
        partial.replace(output_path)
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "full_replays.jsonl")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DATA_PATHS.private_processed / "engagement_windows.jsonl")
    parser.add_argument(
        "--horizon-seconds",
        type=float,
        nargs="+",
        default=[5.0],
        help="one or more label horizons in seconds (for example: --horizon-seconds 1 2 5)",
    )
    parser.add_argument("--trade-window-seconds", type=float, default=3.0)
    parser.add_argument("--lookback-seconds", type=float, default=3.0)
    parser.add_argument("--decision-lead-seconds", type=float, default=1.0)
    parser.add_argument("--action-window-seconds", type=float, default=1.0)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()
    horizons = [float(value) for value in args.horizon_seconds]
    if any(value <= 0 for value in horizons):
        raise ValueError("--horizon-seconds values must be positive")
    totals: list[tuple[float, int, Path]] = []
    for horizon in horizons:
        output = args.output
        if len(horizons) > 1:
            output = args.output.with_name(f"{args.output.stem}_{horizon:g}s{args.output.suffix}")
        if args.database is not None:
            count = extract_database(
                args.database,
                output,
                horizon_seconds=horizon,
                trade_window_seconds=args.trade_window_seconds,
                lookback_seconds=args.lookback_seconds,
                decision_lead_seconds=args.decision_lead_seconds,
                action_window_seconds=args.action_window_seconds,
            )
        else:
            count = extract_file(
                args.input,
                output,
                horizon_seconds=horizon,
                trade_window_seconds=args.trade_window_seconds,
                lookback_seconds=args.lookback_seconds,
                decision_lead_seconds=args.decision_lead_seconds,
                action_window_seconds=args.action_window_seconds,
                limit=args.limit,
            )
        totals.append((horizon, count, output))
    for horizon, count, output in totals:
        print(f"[engagement] horizon={horizon:g}s extracted {count} windows -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

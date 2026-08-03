"""Feature extraction for full replay records produced by Awpy."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from cs2_sim.core.model.replay_value import REPLAY_FEATURE_NAMES
from training.extract_features import extract_snapshots

FULL_FEATURE_NAMES = REPLAY_FEATURE_NAMES
_MAP_NAMES = tuple(name.removeprefix("map_is_") for name in FULL_FEATURE_NAMES if name.startswith("map_is_"))
_BOMB_SITES = tuple(
    name.removeprefix("bomb_site_is_") for name in FULL_FEATURE_NAMES if name.startswith("bomb_site_is_")
)


def _code(value: Any) -> float:
    """Stable categorical encoding without persisting a category dictionary."""

    digest = hashlib.blake2b(str(value or "unknown").encode(), digest_size=4).digest()
    return float(int.from_bytes(digest, "big") % 100_000)


def _side(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return None


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _real_kill(kill: dict[str, Any]) -> bool:
    return kill.get("weapon") != "world" and kill.get("attacker_steamid") != kill.get("victim_steamid")


def _average(players: list[dict[str, Any]], field: str) -> float:
    values = [
        _number(player.get(field))
        for player in players
        if _number(player.get("health"), 100.0) > 0
    ]
    return sum(values) / len(values) if values else 0.0


def _total(players: list[dict[str, Any]], field: str) -> float:
    return sum(_number(player.get(field)) for player in players if _number(player.get("health"), 100.0) > 0)


def _events_before(events: list[dict[str, Any]], tick: int) -> list[dict[str, Any]]:
    return [event for event in events if int(_number(event.get("tick"))) <= tick]


def _event_rows_before(event_groups: dict[str, list[dict[str, Any]]], tick: int) -> list[tuple[str, dict[str, Any]]]:
    return [
        (str(name), event)
        for name, values in event_groups.items()
        for event in _events_before(values or [], tick)
    ]


def _feature_row(
    *,
    snapshot: dict[str, Any],
    map_name: str,
    bomb_site: str,
    sides: dict[str, list[dict[str, Any]]],
    kills_seen: int,
    damage_events_seen: int,
    shots_seen: int,
    utility_events_seen: int,
    bomb_time_remaining: float,
) -> dict[str, float]:
    ct_players = sides["ct"]
    t_players = sides["t"]
    values: dict[str, float] = {
        "map_code": _code(map_name),
        "time_seconds": float(snapshot["elapsed_seconds"]),
        "ct_alive": float(snapshot["ct_alive"]),
        "t_alive": float(snapshot["t_alive"]),
        "alive_difference": float(snapshot["ct_alive"] - snapshot["t_alive"]),
        "ct_avg_health": _average(ct_players, "health"),
        "t_avg_health": _average(t_players, "health"),
        "kills_seen": float(kills_seen),
        "bomb_planted": float(snapshot["bomb_planted"]),
        "bomb_site_code": _code(bomb_site),
        "ct_avg_x": _average(ct_players, "X"),
        "ct_avg_y": _average(ct_players, "Y"),
        "t_avg_x": _average(t_players, "X"),
        "t_avg_y": _average(t_players, "Y"),
        "ct_total_health": _total(ct_players, "health"),
        "t_total_health": _total(t_players, "health"),
        "ct_avg_armor": _average(ct_players, "armor_value"),
        "t_avg_armor": _average(t_players, "armor_value"),
        "damage_events_seen": float(damage_events_seen),
        "shots_seen": float(shots_seen),
        "utility_events_seen": float(utility_events_seen),
        "bomb_time_remaining": float(bomb_time_remaining),
        "ct_avg_z": _average(ct_players, "Z"),
        "t_avg_z": _average(t_players, "Z"),
        "ct_norm_x": _average(ct_players, "X") / 10_000.0,
        "ct_norm_y": _average(ct_players, "Y") / 10_000.0,
        "t_norm_x": _average(t_players, "X") / 10_000.0,
        "t_norm_y": _average(t_players, "Y") / 10_000.0,
    }
    values.update({f"map_is_{name}": float(map_name == name) for name in _MAP_NAMES})
    values.update({f"bomb_site_is_{name}": float(bomb_site == name) for name in _BOMB_SITES})
    return {name: values.get(name, 0.0) for name in FULL_FEATURE_NAMES}


def record_to_rows(
    record: dict[str, Any],
    *,
    sample_every: int = 1,
    decision_window_seconds: float | None = None,
    include_terminal: bool = True,
) -> list[dict[str, Any]]:
    """Convert one parsed replay record into labelled round-state rows."""

    ticks = record.get("ticks") or []
    if not ticks:
        return []
    if sample_every <= 0:
        raise ValueError("sample_every must be positive")
    if decision_window_seconds is not None and decision_window_seconds <= 0:
        raise ValueError("decision_window_seconds must be positive")
    header = record.get("header") or {}
    tick_rate = _number(header.get("tick_rate") or record.get("tick_rate"), 128.0)
    map_name = header.get("map_name") or "unknown"
    kills = [kill for kill in record.get("kills") or [] if _real_kill(kill)]
    damages = [damage for damage in record.get("damages") or [] if _real_kill(damage)]
    bomb_events = record.get("bomb") or []
    event_groups = record.get("events") or {}
    ticks_by_round: dict[int, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for tick_row in ticks:
        round_num = int(_number(tick_row.get("round_num")))
        tick = int(_number(tick_row.get("tick")))
        ticks_by_round[round_num][tick].append(tick_row)

    rows: list[dict[str, Any]] = []
    for round_info in record.get("rounds") or []:
        round_num = int(_number(round_info.get("round_num")))
        winner = _side(round_info.get("winner"))
        if winner is None:
            continue
        start_tick = int(_number(round_info.get("start")))
        selected_ticks = sorted(ticks_by_round.get(round_num, {}))[::sample_every]
        round_kills = [kill for kill in kills if int(_number(kill.get("round_num"))) == round_num]
        round_damages = [damage for damage in damages if int(_number(damage.get("round_num"))) == round_num]
        round_bombs = [event for event in bomb_events if int(_number(event.get("round_num"))) == round_num]
        contact_events = round_damages or round_kills
        first_contact_tick = min(
            (int(_number(event.get("tick"))) for event in contact_events),
            default=None,
        )
        for tick in selected_ticks:
            if decision_window_seconds is not None:
                if first_contact_tick is None:
                    continue
                window_end = first_contact_tick + decision_window_seconds * tick_rate
                if tick < first_contact_tick or tick > window_end:
                    continue
            player_rows = ticks_by_round[round_num][tick]
            sides: dict[str, list[dict[str, Any]]] = {"ct": [], "t": []}
            for player in player_rows:
                side = _side(player.get("team_name") or player.get("team") or player.get("side"))
                if side is not None:
                    sides[side].append(player)
            if not sides["ct"] and not sides["t"]:
                continue
            ct_alive = sum(_number(player.get("health"), 100.0) > 0 for player in sides["ct"])
            t_alive = sum(_number(player.get("health"), 100.0) > 0 for player in sides["t"])
            if not include_terminal and (ct_alive <= 0 or t_alive <= 0):
                continue

            prior_bombs = [event for event in round_bombs if int(_number(event.get("tick"))) <= tick]
            bomb_planted = any("plant" in str(event.get("event") or "").lower() for event in prior_bombs)
            bomb_site = "none"
            if prior_bombs:
                bomb_site = str(prior_bombs[-1].get("bombsite") or prior_bombs[-1].get("site") or "none")
            kills_seen = sum(int(_number(kill.get("tick"))) <= tick for kill in round_kills)
            damage_seen = len(_events_before(round_damages, tick))
            prior_event_rows = _event_rows_before(event_groups, tick)
            shots_seen = sum("fire" in name.lower() for name, _ in prior_event_rows)
            utility_seen = sum(
                any(token in (name.lower() + " " + str(event.get("weapon") or "").lower())
                    for token in ("grenade", "flash", "smoke", "molotov", "incendiary", "inferno", "decoy"))
                for name, event in prior_event_rows
            )
            plant_ticks = [
                int(_number(event.get("tick")))
                for event in round_bombs
                if "plant" in str(event.get("event") or "").lower()
                and int(_number(event.get("tick"))) <= tick
            ]
            bomb_time_remaining = (
                max(0.0, 40.0 - (tick - max(plant_ticks)) / max(tick_rate, 1.0))
                if plant_ticks
                else 0.0
            )
            snapshot = {
                "map_name": map_name,
                "event_type": "tick",
                "ct_alive": ct_alive,
                "t_alive": t_alive,
                "bomb_planted": bomb_planted,
                "bomb_site": bomb_site,
                "elapsed_seconds": max(0.0, (tick - start_tick) / tick_rate),
                "kills_seen": kills_seen,
                "ct_avg_health": _average(sides["ct"], "health"),
                "t_avg_health": _average(sides["t"], "health"),
                "ct_avg_x": _average(sides["ct"], "X"),
                "ct_avg_y": _average(sides["ct"], "Y"),
                "t_avg_x": _average(sides["t"], "X"),
                "t_avg_y": _average(sides["t"], "Y"),
            }
            rows.append(
                {
                    "source": record.get("demo_file") or "unknown",
                    "round_num": round_num,
                    "tick": tick,
                    "label_ct_win": int(winner == "ct"),
                    "snapshot": snapshot,
                    "features": _feature_row(
                        snapshot=snapshot,
                        map_name=str(map_name),
                        bomb_site=bomb_site,
                        sides=sides,
                        kills_seen=kills_seen,
                        damage_events_seen=damage_seen,
                        shots_seen=shots_seen,
                        utility_events_seen=utility_seen,
                        bomb_time_remaining=bomb_time_remaining,
                    ),
                }
            )
    return rows


def record_to_event_rows(
    record: dict[str, Any],
    *,
    decision_window_seconds: float | None = None,
    include_terminal: bool = True,
) -> list[dict[str, Any]]:
    """Build event-only rows when positional tick parsing is unavailable.

    These rows are useful for a provisional round-value model, but their
    position features are zero and they must not be described as movement
    action training data.
    """

    rows: list[dict[str, Any]] = []
    for snapshot in extract_snapshots(
        record,
        str(record.get("demo_file") or "unknown"),
        decision_window_seconds=decision_window_seconds,
        include_round_start=decision_window_seconds is None,
        include_round_end=decision_window_seconds is None,
        include_terminal=include_terminal,
    ):
        winner = snapshot.get("label_round_winner")
        if winner not in {"ct", "t"}:
            continue
        rows.append(snapshot_to_event_row(snapshot))
    return rows


def snapshot_to_event_row(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Convert one already-extracted lightweight snapshot for LightGBM."""

    winner = snapshot.get("label_round_winner")
    if winner not in {"ct", "t"}:
        raise ValueError("snapshot has no valid round winner label")
    map_name = str(snapshot.get("map_name") or "unknown")
    bomb_site = str(snapshot.get("bomb_site") or "none").lower()
    features = {name: 0.0 for name in FULL_FEATURE_NAMES}
    features.update(
        {
            "map_code": _code(map_name),
            "time_seconds": _number(snapshot.get("elapsed_seconds")),
            "ct_alive": float(snapshot.get("ct_alive") or 0),
            "t_alive": float(snapshot.get("t_alive") or 0),
            "alive_difference": float(snapshot.get("alive_difference") or 0),
            "ct_avg_health": 100.0,
            "t_avg_health": 100.0,
            "kills_seen": float(snapshot.get("kills_seen") or 0),
            "bomb_planted": float(bool(snapshot.get("bomb_planted"))),
            "bomb_site_code": _code(bomb_site),
        }
    )
    for name in _MAP_NAMES:
        features[f"map_is_{name}"] = float(map_name == name)
    for name in _BOMB_SITES:
        features[f"bomb_site_is_{name}"] = float(bomb_site == name)
    return {
        "source": snapshot.get("source") or "unknown",
        "round_num": snapshot.get("round_num"),
        "tick": snapshot.get("tick"),
        "label_ct_win": int(winner == "ct"),
        "snapshot": snapshot,
        "features": features,
    }

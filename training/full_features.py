"""Feature extraction for full replay records produced by Awpy."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Any

from training.extract_features import extract_snapshots

FULL_FEATURE_NAMES = (
    "map_code",
    "time_seconds",
    "ct_alive",
    "t_alive",
    "alive_difference",
    "ct_avg_health",
    "t_avg_health",
    "kills_seen",
    "bomb_planted",
    "bomb_site_code",
    "ct_avg_x",
    "ct_avg_y",
    "t_avg_x",
    "t_avg_y",
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
    values = [_number(player.get(field)) for player in players]
    return sum(values) / len(values) if values else 0.0


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
    bomb_events = record.get("bomb") or []
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
        round_bombs = [event for event in bomb_events if int(_number(event.get("round_num"))) == round_num]
        first_contact_tick = min(
            (int(_number(kill.get("tick"))) for kill in round_kills),
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
            snapshot = {
                "map_name": map_name,
                "event_type": "tick",
                "ct_alive": ct_alive,
                "t_alive": t_alive,
                "bomb_planted": bomb_planted,
                "bomb_site": bomb_site,
                "elapsed_seconds": max(0.0, (tick - start_tick) / tick_rate),
                "kills_seen": kills_seen,
            }
            rows.append(
                {
                    "source": record.get("demo_file") or "unknown",
                    "round_num": round_num,
                    "tick": tick,
                    "label_ct_win": int(winner == "ct"),
                    "snapshot": snapshot,
                    "features": {
                        "map_code": _code(map_name),
                        "time_seconds": snapshot["elapsed_seconds"],
                        "ct_alive": float(ct_alive),
                        "t_alive": float(t_alive),
                        "alive_difference": float(ct_alive - t_alive),
                        "ct_avg_health": _average(sides["ct"], "health"),
                        "t_avg_health": _average(sides["t"], "health"),
                        "kills_seen": float(kills_seen),
                        "bomb_planted": float(bomb_planted),
                        "bomb_site_code": _code(bomb_site),
                        "ct_avg_x": _average(sides["ct"], "X"),
                        "ct_avg_y": _average(sides["ct"], "Y"),
                        "t_avg_x": _average(sides["t"], "X"),
                        "t_avg_y": _average(sides["t"], "Y"),
                    },
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
    return {
        "source": snapshot.get("source") or "unknown",
        "round_num": snapshot.get("round_num"),
        "tick": snapshot.get("tick"),
        "label_ct_win": int(winner == "ct"),
        "snapshot": snapshot,
        "features": {
            "map_code": _code(snapshot.get("map_name")),
            "time_seconds": _number(snapshot.get("elapsed_seconds")),
            "ct_alive": float(snapshot.get("ct_alive") or 0),
            "t_alive": float(snapshot.get("t_alive") or 0),
            "alive_difference": float(snapshot.get("alive_difference") or 0),
            "ct_avg_health": 100.0,
            "t_avg_health": 100.0,
            "kills_seen": float(snapshot.get("kills_seen") or 0),
            "bomb_planted": float(bool(snapshot.get("bomb_planted"))),
            "bomb_site_code": _code(snapshot.get("bomb_site")),
            "ct_avg_x": 0.0,
            "ct_avg_y": 0.0,
            "t_avg_x": 0.0,
            "t_avg_y": 0.0,
        },
    }

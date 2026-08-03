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
from collections import defaultdict
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

from Noah.training.data_paths import DATA_PATHS

SCHEMA_VERSION = "engagement_windows_v1"
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


def _label_for_player(
    focal_player: str,
    focal_side: str | None,
    *,
    anchor_tick: int,
    label_end_tick: int,
    round_kills: list[dict[str, Any]],
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
    return {
        "label_kill": focal_kill is not None,
        "label_death": focal_death is not None,
        "label_trade": trade_event is not None,
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
    tick_rate: float | None = None,
    max_windows: int | None = None,
    round_value_predictor: Callable[[dict[str, Any]], float | None] | None = None,
) -> list[dict[str, Any]]:
    """Extract player-centric combat windows with strict future-only labels."""

    if horizon_seconds <= 0 or trade_window_seconds <= 0:
        raise ValueError("horizon_seconds and trade_window_seconds must be positive")
    if max_windows is not None and max_windows <= 0:
        raise ValueError("max_windows must be positive")
    header = record.get("header") or {}
    match = record.get("match") or {}
    rate = _number(tick_rate if tick_rate is not None else header.get("tick_rate") or match.get("tick_rate"), DEFAULT_TICK_RATE)
    if rate <= 0:
        raise ValueError("tick_rate must be positive")
    horizon_ticks = max(1, round(horizon_seconds * rate))
    trade_ticks = max(1, round(trade_window_seconds * rate))
    end_ticks = _round_end_ticks(record)
    winners = _round_winners(record)
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
        anchor_tick = _event_tick(anchor)
        round_end = end_ticks.get(round_num)
        label_end = anchor_tick + horizon_ticks
        if round_end is not None:
            label_end = min(label_end, round_end)
        if label_end <= anchor_tick:
            continue
        round_kills = [event for kind, event in by_round[round_num] if kind == "kill"]
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
                "features": _anchor_feature(anchor, anchor_kind),
                "survived_after_kill": survived_after_kill,
                "round_won": round_won,
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
            )
        else:
            count = extract_file(
                args.input,
                output,
                horizon_seconds=horizon,
                trade_window_seconds=args.trade_window_seconds,
                limit=args.limit,
            )
        totals.append((horizon, count, output))
    for horizon, count, output in totals:
        print(f"[engagement] horizon={horizon:g}s extracted {count} windows -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

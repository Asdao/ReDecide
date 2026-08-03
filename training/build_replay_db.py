"""Build a queryable SQLite database from parsed CS2 replay JSONL records."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from pathlib import Path
from typing import Any

from training.full_features import record_to_rows
from training.infer_actions import infer_actions
from training.replay_cleaning import CLEANING_VERSION, CleaningOptions, clean_records


SCHEMA = """
CREATE TABLE IF NOT EXISTS matches (
    match_id TEXT PRIMARY KEY,
    map_name TEXT,
    event_name TEXT,
    event_date TEXT,
    patch TEXT,
    team_one TEXT,
    team_two TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS replays (
    replay_id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    demo_file TEXT NOT NULL,
    parser TEXT NOT NULL,
    map_name TEXT,
    tick_rate REAL,
    tick_count INTEGER NOT NULL,
    round_count INTEGER NOT NULL,
    checksum TEXT NOT NULL,
    match_id TEXT REFERENCES matches(match_id),
    header_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rounds (
    replay_id INTEGER NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
    round_num INTEGER NOT NULL,
    start_tick INTEGER,
    end_tick INTEGER,
    winner TEXT,
    reason TEXT,
    bomb_plant_tick INTEGER,
    bomb_site TEXT,
    PRIMARY KEY (replay_id, round_num)
);
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id INTEGER PRIMARY KEY,
    replay_id INTEGER NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
    round_num INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    map_name TEXT,
    elapsed_seconds REAL NOT NULL,
    ct_alive INTEGER NOT NULL,
    t_alive INTEGER NOT NULL,
    alive_difference INTEGER NOT NULL,
    kills_seen INTEGER NOT NULL,
    bomb_planted INTEGER NOT NULL,
    bomb_site TEXT,
    label_ct_win INTEGER NOT NULL,
    features_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS players (
    replay_id INTEGER NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
    steamid TEXT NOT NULL,
    player_name TEXT,
    side TEXT,
    first_tick INTEGER,
    last_tick INTEGER,
    PRIMARY KEY (replay_id, steamid)
);
CREATE TABLE IF NOT EXISTS player_ticks (
    replay_id INTEGER NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
    round_num INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    steamid TEXT NOT NULL,
    player_name TEXT,
    side TEXT,
    x REAL,
    y REAL,
    z REAL,
    health REAL,
    armor REAL,
    alive INTEGER NOT NULL,
    zone TEXT,
    payload_json TEXT NOT NULL,
    PRIMARY KEY (replay_id, round_num, tick, steamid)
);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY,
    replay_id INTEGER NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
    round_num INTEGER,
    tick INTEGER,
    event_type TEXT NOT NULL,
    attacker_steamid TEXT,
    victim_steamid TEXT,
    actor_steamid TEXT,
    side TEXT,
    site TEXT,
    weapon TEXT,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS inferred_actions (
    action_id INTEGER PRIMARY KEY,
    replay_id INTEGER NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
    round_num INTEGER NOT NULL,
    tick INTEGER NOT NULL,
    next_tick INTEGER NOT NULL,
    player_id TEXT NOT NULL,
    side TEXT,
    current_zone TEXT,
    next_zone TEXT,
    action TEXT NOT NULL,
    horizon_ticks INTEGER NOT NULL,
    legal_actions_json TEXT NOT NULL,
    outcome_json TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dataset_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS snapshots_map_round_idx
    ON snapshots(map_name, round_num, tick);
CREATE INDEX IF NOT EXISTS snapshots_replay_idx
    ON snapshots(replay_id, round_num, tick);
CREATE INDEX IF NOT EXISTS player_ticks_replay_idx
    ON player_ticks(replay_id, round_num, tick);
CREATE INDEX IF NOT EXISTS events_replay_tick_idx
    ON events(replay_id, round_num, tick);
CREATE INDEX IF NOT EXISTS events_type_idx
    ON events(event_type, round_num);
CREATE UNIQUE INDEX IF NOT EXISTS snapshots_unique_tick_idx
    ON snapshots(replay_id, round_num, tick);
CREATE INDEX IF NOT EXISTS inferred_actions_player_idx
    ON inferred_actions(replay_id, player_id, round_num, tick);
CREATE INDEX IF NOT EXISTS inferred_actions_action_idx
    ON inferred_actions(action, side);
"""


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _side(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return None


def _player_id(row: dict[str, Any], ordinal: int) -> str:
    for key in ("steamid", "steam_id", "player_steamid", "name", "player_name"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return f"anonymous:{ordinal}"


def _player_name(row: dict[str, Any]) -> str | None:
    for key in ("name", "player_name", "player_name_text"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _number_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _zone(row: dict[str, Any]) -> str | None:
    named = row.get("last_place_name") or row.get("zone")
    if named not in (None, ""):
        return str(named)
    x = _number_or_none(row.get("X") if "X" in row else row.get("x"))
    y = _number_or_none(row.get("Y") if "Y" in row else row.get("y"))
    if x is not None and y is not None and math.isfinite(x) and math.isfinite(y):
        return f"grid:{math.floor(x / 1000.0)}:{math.floor(y / 1000.0)}"
    return None


def _event_rows(record: dict[str, Any]):
    """Yield normalized event rows while retaining the original payload."""

    for event in record.get("kills") or []:
        yield "kill", event
    for event in record.get("damages") or []:
        yield "damage", event
    for event in record.get("bomb") or []:
        yield str(event.get("event") or "bomb").lower(), event
    for event_type, values in (record.get("events") or {}).items():
        for event in values or []:
            yield str(event_type), event


def _record_checksum(record: dict[str, Any]) -> str:
    payload = json.dumps(record, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _match_id(record: dict[str, Any], source_path: str) -> str:
    match = record.get("match") or {}
    return str(record.get("match_id") or match.get("match_id") or source_path)


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def build_database(
    input_path: Path,
    output_path: Path,
    *,
    sample_every: int = 4,
    decision_window_seconds: float = 5.0,
    action_window_seconds: float = 2.0,
    replace: bool = False,
    clean: bool = False,
    cleaning_options: CleaningOptions | None = None,
) -> dict[str, int]:
    """Materialize parsed records, rounds, and positional decision snapshots."""

    if sample_every <= 0:
        raise ValueError("sample_every must be positive")
    if decision_window_seconds <= 0:
        raise ValueError("decision_window_seconds must be positive")
    if action_window_seconds <= 0:
        raise ValueError("action_window_seconds must be positive")
    records = _read_records(input_path)
    if not records:
        raise ValueError("input JSONL contains no replay records")
    cleaning_report = None
    if clean:
        records, cleaning_report = clean_records(records, options=cleaning_options)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        if replace:
            connection.executescript(
                "DROP TABLE IF EXISTS inferred_actions; DROP TABLE IF EXISTS events; "
                "DROP TABLE IF EXISTS player_ticks; "
                "DROP TABLE IF EXISTS players; DROP TABLE IF EXISTS snapshots; "
                "DROP TABLE IF EXISTS rounds; DROP TABLE IF EXISTS replays; DROP TABLE IF EXISTS matches; "
                "DROP TABLE IF EXISTS dataset_metadata;"
            )
        connection.executescript(SCHEMA)
        replay_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(replays)")
        }
        if "checksum" not in replay_columns:
            connection.execute("ALTER TABLE replays ADD COLUMN checksum TEXT NOT NULL DEFAULT ''")
        if "match_id" not in replay_columns:
            connection.execute("ALTER TABLE replays ADD COLUMN match_id TEXT")
        metadata = {
            "schema_version": "2",
            "cleaning_version": CLEANING_VERSION if clean else "raw",
            "input_path": str(input_path),
        }
        if cleaning_report is not None:
            metadata["cleaning_report"] = json.dumps(cleaning_report, separators=(",", ":"))
        connection.executemany(
            "INSERT OR REPLACE INTO dataset_metadata(key,value) VALUES (?,?)",
            metadata.items(),
        )
        replay_count = round_count = snapshot_count = 0
        player_count = player_tick_count = event_count = inferred_action_count = 0
        for record in records:
            source_path = str(record.get("source_path") or record.get("demo_file") or "unknown")
            header = record.get("header") or {}
            match = record.get("match") or {}
            map_name = str(header.get("map_name") or match.get("map_name") or "unknown")
            ticks = record.get("ticks") or []
            demo_file = str(record.get("demo_file") or source_path)
            match_id = _match_id(record, source_path)
            connection.execute(
                "INSERT OR IGNORE INTO matches "
                "(match_id,map_name,event_name,event_date,patch,team_one,team_two,payload_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    match_id,
                    map_name,
                    match.get("event") or match.get("event_name"),
                    match.get("date") or match.get("event_date"),
                    match.get("patch"),
                    match.get("team_one") or match.get("team1"),
                    match.get("team_two") or match.get("team2"),
                    json.dumps(match, separators=(",", ":")),
                ),
            )
            cursor = connection.execute(
                "INSERT OR IGNORE INTO replays "
                "(source_path,demo_file,parser,map_name,tick_rate,tick_count,round_count,checksum,match_id,header_json) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    source_path,
                    demo_file,
                    str(record.get("parser") or "unknown"),
                    map_name,
                    _number(header.get("tick_rate") or match.get("tick_rate"), 128.0),
                    len(ticks),
                    len(record.get("rounds") or []),
                    _record_checksum(record),
                    match_id,
                    json.dumps(header, separators=(",", ":")),
                ),
            )
            replay_id_row = connection.execute(
                "SELECT replay_id FROM replays WHERE source_path=?", (source_path,)
            ).fetchone()
            if replay_id_row is None:
                raise RuntimeError(f"could not create replay row for {source_path}")
            replay_id = int(replay_id_row[0])
            if cursor.rowcount == 1:
                replay_count += 1
            connection.execute(
                "UPDATE replays SET checksum=?, match_id=? WHERE replay_id=?",
                (_record_checksum(record), match_id, replay_id),
            )

            for ordinal, player_row in enumerate(record.get("ticks") or []):
                round_num = int(_number(player_row.get("round_num")))
                tick = int(_number(player_row.get("tick")))
                steamid = _player_id(player_row, ordinal)
                side = _side(
                    player_row.get("team_name")
                    or player_row.get("team")
                    or player_row.get("side")
                )
                player_name = _player_name(player_row)
                connection.execute(
                    "INSERT OR IGNORE INTO players "
                    "(replay_id,steamid,player_name,side,first_tick,last_tick) VALUES (?,?,?,?,?,?)",
                    (replay_id, steamid, player_name, side, tick, tick),
                )
                connection.execute(
                    "UPDATE players SET first_tick=MIN(COALESCE(first_tick,?),?), "
                    "last_tick=MAX(COALESCE(last_tick,?),?) "
                    "WHERE replay_id=? AND steamid=?",
                    (tick, tick, tick, tick, replay_id, steamid),
                )
                cursor_tick = connection.execute(
                    "INSERT OR IGNORE INTO player_ticks "
                    "(replay_id,round_num,tick,steamid,player_name,side,x,y,z,health,armor,alive,zone,payload_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        replay_id,
                        round_num,
                        tick,
                        steamid,
                        player_name,
                        side,
                        _number_or_none(player_row.get("X") if "X" in player_row else player_row.get("x")),
                        _number_or_none(player_row.get("Y") if "Y" in player_row else player_row.get("y")),
                        _number_or_none(player_row.get("Z") if "Z" in player_row else player_row.get("z")),
                        _number_or_none(player_row.get("health")),
                        _number_or_none(player_row.get("armor_value") or player_row.get("armor")),
                        int(_number(player_row.get("health"), 100.0) > 0),
                        _zone(player_row),
                        json.dumps(player_row, separators=(",", ":")),
                    ),
                )
                if cursor_tick.rowcount == 1:
                    player_tick_count += 1
            player_count += int(
                connection.execute(
                    "SELECT COUNT(*) FROM players WHERE replay_id=?", (replay_id,)
                ).fetchone()[0]
            )

            for event_type, event in _event_rows(record):
                connection.execute(
                    "INSERT INTO events "
                    "(replay_id,round_num,tick,event_type,attacker_steamid,victim_steamid,actor_steamid,side,site,weapon,payload_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        replay_id,
                        int(_number(event.get("round_num"))) if event.get("round_num") is not None else None,
                        int(_number(event.get("tick"))) if event.get("tick") is not None else None,
                        event_type,
                        event.get("attacker_steamid"),
                        event.get("victim_steamid"),
                        event.get("steamid") or event.get("player_steamid"),
                        _side(event.get("attacker_side") or event.get("side") or event.get("team_name")),
                        event.get("bombsite") or event.get("site") or event.get("which_bomb_zone"),
                        event.get("weapon"),
                        json.dumps(event, separators=(",", ":")),
                    ),
                )
                event_count += 1

            for action_row in infer_actions(
                record,
                window_seconds=action_window_seconds,
                movement_threshold=20.0,
            ):
                connection.execute(
                    "INSERT INTO inferred_actions "
                    "(replay_id,round_num,tick,next_tick,player_id,side,current_zone,next_zone,action,"
                    "horizon_ticks,legal_actions_json,outcome_json,payload_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        replay_id,
                        int(action_row["round_num"]),
                        int(action_row["tick"]),
                        int(action_row["next_tick"]),
                        str(action_row["player_id"]),
                        action_row.get("side"),
                        action_row.get("current_zone"),
                        action_row.get("next_zone"),
                        action_row["action"],
                        int(action_row["horizon_ticks"]),
                        json.dumps(action_row.get("legal_actions") or ["hold", "move"], separators=(",", ":")),
                        json.dumps(action_row.get("outcome") or {}, separators=(",", ":")),
                        json.dumps(action_row, separators=(",", ":")),
                    ),
                )
                inferred_action_count += 1

            for round_info in record.get("rounds") or []:
                round_num = int(_number(round_info.get("round_num")))
                connection.execute(
                    "INSERT OR REPLACE INTO rounds "
                    "(replay_id,round_num,start_tick,end_tick,winner,reason,bomb_plant_tick,bomb_site) "
                    "VALUES (?,?,?,?,?,?,?,?)",
                    (
                        replay_id,
                        round_num,
                        int(_number(round_info.get("start"))),
                        int(_number(round_info.get("end") or round_info.get("official_end"))),
                        _side(round_info.get("winner")),
                        round_info.get("reason"),
                        int(_number(round_info.get("bomb_plant")))
                        if round_info.get("bomb_plant") is not None
                        else None,
                        round_info.get("bomb_site") if round_info.get("bomb_site") != "not_planted" else None,
                    ),
                )
                round_count += 1

            for row in record_to_rows(
                record,
                sample_every=sample_every,
                decision_window_seconds=decision_window_seconds,
                include_terminal=False,
            ):
                snapshot = row["snapshot"]
                features = row["features"]
                connection.execute(
                    "INSERT INTO snapshots "
                    "(replay_id,round_num,tick,map_name,elapsed_seconds,ct_alive,t_alive,"
                    "alive_difference,kills_seen,bomb_planted,bomb_site,label_ct_win,features_json,snapshot_json) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        replay_id,
                        int(row["round_num"]),
                        int(row["tick"]),
                        snapshot.get("map_name"),
                        _number(snapshot.get("elapsed_seconds")),
                        int(snapshot.get("ct_alive") or 0),
                        int(snapshot.get("t_alive") or 0),
                        int(snapshot.get("alive_difference") or 0),
                        int(snapshot.get("kills_seen") or 0),
                        int(bool(snapshot.get("bomb_planted"))),
                        snapshot.get("bomb_site"),
                        int(row["label_ct_win"]),
                        json.dumps(features, separators=(",", ":")),
                        json.dumps(snapshot, separators=(",", ":")),
                    ),
                )
                snapshot_count += 1
        connection.commit()
    finally:
        connection.close()
    return {
        "replays": replay_count,
        "rounds": round_count,
        "snapshots": snapshot_count,
        "players": player_count,
        "player_ticks": player_tick_count,
        "events": event_count,
        "inferred_actions": inferred_action_count,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/full_replays.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/full/processed/cs2_replays.sqlite"))
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    parser.add_argument("--action-window-seconds", type=float, default=2.0)
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--clean", action="store_true", help="apply the versioned cleaning policy before loading")
    parser.add_argument("--max-round-seconds", type=float, default=180.0)
    args = parser.parse_args()
    stats = build_database(
        args.input,
        args.output,
        sample_every=args.sample_every,
        decision_window_seconds=args.decision_window_seconds,
        action_window_seconds=args.action_window_seconds,
        replace=args.replace,
        clean=args.clean,
        cleaning_options=CleaningOptions(max_round_seconds=args.max_round_seconds),
    )
    print(f"[db] saved {args.output}: {json.dumps(stats, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

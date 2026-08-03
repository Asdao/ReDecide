"""Build a queryable SQLite database from parsed CS2 replay JSONL records."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

from training.full_features import record_to_rows


SCHEMA = """
CREATE TABLE IF NOT EXISTS replays (
    replay_id INTEGER PRIMARY KEY,
    source_path TEXT NOT NULL UNIQUE,
    demo_file TEXT NOT NULL,
    parser TEXT NOT NULL,
    map_name TEXT,
    tick_rate REAL,
    tick_count INTEGER NOT NULL,
    round_count INTEGER NOT NULL,
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
CREATE INDEX IF NOT EXISTS snapshots_map_round_idx
    ON snapshots(map_name, round_num, tick);
CREATE INDEX IF NOT EXISTS snapshots_replay_idx
    ON snapshots(replay_id, round_num, tick);
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


def _read_records(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def build_database(
    input_path: Path,
    output_path: Path,
    *,
    sample_every: int = 4,
    decision_window_seconds: float = 5.0,
    replace: bool = False,
) -> dict[str, int]:
    """Materialize parsed records, rounds, and positional decision snapshots."""

    if sample_every <= 0:
        raise ValueError("sample_every must be positive")
    if decision_window_seconds <= 0:
        raise ValueError("decision_window_seconds must be positive")
    records = _read_records(input_path)
    if not records:
        raise ValueError("input JSONL contains no replay records")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(output_path)
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        if replace:
            connection.executescript(
                "DROP TABLE IF EXISTS snapshots; DROP TABLE IF EXISTS rounds; DROP TABLE IF EXISTS replays;"
            )
        connection.executescript(SCHEMA)
        replay_count = round_count = snapshot_count = 0
        for record in records:
            source_path = str(record.get("demo_file") or "unknown")
            header = record.get("header") or {}
            match = record.get("match") or {}
            map_name = str(header.get("map_name") or match.get("map_name") or "unknown")
            ticks = record.get("ticks") or []
            demo_file = str(record.get("demo_file") or source_path)
            cursor = connection.execute(
                "INSERT OR IGNORE INTO replays "
                "(source_path,demo_file,parser,map_name,tick_rate,tick_count,round_count,header_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (
                    source_path,
                    demo_file,
                    str(record.get("parser") or "unknown"),
                    map_name,
                    _number(header.get("tick_rate") or match.get("tick_rate"), 128.0),
                    len(ticks),
                    len(record.get("rounds") or []),
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
    return {"replays": replay_count, "rounds": round_count, "snapshots": snapshot_count}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/full_replays.jsonl"))
    parser.add_argument("--output", type=Path, default=Path("data/full/processed/cs2_replays.sqlite"))
    parser.add_argument("--sample-every", type=int, default=4)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    parser.add_argument("--replace", action="store_true")
    args = parser.parse_args()
    stats = build_database(
        args.input,
        args.output,
        sample_every=args.sample_every,
        decision_window_seconds=args.decision_window_seconds,
        replace=args.replace,
    )
    print(f"[db] saved {args.output}: {json.dumps(stats, sort_keys=True)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""SQLite replay-vault projection with bounded lookup methods."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .segmenter import SegmentedReplay


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS replays (
  replay_id TEXT PRIMARY KEY, source_path TEXT NOT NULL, demo_file TEXT NOT NULL,
  parser TEXT NOT NULL, map_name TEXT NOT NULL, tick_rate REAL NOT NULL,
  checksum TEXT NOT NULL, header_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS rounds (
  replay_id TEXT NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
  round_num INTEGER NOT NULL, start_tick INTEGER, end_tick INTEGER,
  winner TEXT, reason TEXT, bomb_plant_tick INTEGER, bomb_site TEXT,
  PRIMARY KEY (replay_id, round_num)
);
CREATE TABLE IF NOT EXISTS events (
  event_id TEXT PRIMARY KEY, replay_id TEXT NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
  round_num INTEGER, tick INTEGER, event_type TEXT NOT NULL,
  attacker_id TEXT, victim_id TEXT, actor_id TEXT, side TEXT, site TEXT, weapon TEXT,
  payload_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS player_ticks (
  replay_id TEXT NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
  round_num INTEGER NOT NULL, tick INTEGER NOT NULL, player_id TEXT NOT NULL,
  player_name TEXT, side TEXT, x REAL, y REAL, z REAL, health INTEGER, armor INTEGER,
  alive INTEGER, zone TEXT, payload_json TEXT NOT NULL,
  PRIMARY KEY (replay_id, round_num, tick, player_id)
);
CREATE TABLE IF NOT EXISTS heatmap_points (
  replay_id TEXT NOT NULL REFERENCES replays(replay_id) ON DELETE CASCADE,
  round_num INTEGER NOT NULL, tick INTEGER NOT NULL, player_id TEXT NOT NULL,
  side TEXT, map_name TEXT NOT NULL, cell_x INTEGER, cell_y INTEGER, x REAL, y REAL,
  PRIMARY KEY (replay_id, round_num, tick, player_id)
);
CREATE INDEX IF NOT EXISTS events_lookup ON events(replay_id, round_num, tick);
CREATE INDEX IF NOT EXISTS events_type_lookup ON events(event_type, round_num);
CREATE INDEX IF NOT EXISTS heatmap_lookup ON heatmap_points(map_name, side, cell_x, cell_y);
CREATE INDEX IF NOT EXISTS ticks_lookup ON player_ticks(replay_id, round_num, tick);
"""


class ReplayRepository:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def write(self, segments: SegmentedReplay) -> None:
        replay = segments.replay
        metadata = replay.metadata
        with self.connection:
            self.connection.execute(
                "INSERT OR REPLACE INTO replays VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (metadata.replay_id, metadata.source_path, metadata.demo_file, metadata.parser,
                 metadata.map_name, metadata.tick_rate, metadata.checksum, json.dumps(metadata.header)),
            )
            self.connection.execute("DELETE FROM rounds WHERE replay_id=?", (metadata.replay_id,))
            self.connection.execute("DELETE FROM events WHERE replay_id=?", (metadata.replay_id,))
            self.connection.execute("DELETE FROM player_ticks WHERE replay_id=?", (metadata.replay_id,))
            self.connection.execute("DELETE FROM heatmap_points WHERE replay_id=?", (metadata.replay_id,))
            self.connection.executemany(
                "INSERT INTO rounds VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [(r.replay_id, r.round_num, r.start_tick, r.end_tick, r.winner, r.reason, r.bomb_plant_tick, r.bomb_site) for r in segments.rounds],
            )
            self.connection.executemany(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(e.event_id, e.replay_id, e.round_num, e.tick, e.event_type, e.attacker_id, e.victim_id, e.actor_id, e.side, e.site, e.weapon, json.dumps(e.payload)) for e in segments.events],
            )
            self.connection.executemany(
                "INSERT INTO player_ticks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(t.replay_id, t.round_num, t.tick, t.player_id, t.player_name, t.side, t.x, t.y, t.z, t.health, t.armor, None if t.alive is None else int(t.alive), t.zone, json.dumps(t.payload)) for t in segments.player_ticks],
            )
            self.connection.executemany(
                "INSERT INTO heatmap_points VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [(p.replay_id, p.round_num, p.tick, p.player_id, p.side, p.map_name, p.cell_x, p.cell_y, p.x, p.y) for p in segments.heatmap_points],
            )

    def stats(self) -> dict[str, int]:
        return {
            table: int(self.connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in ("replays", "rounds", "events", "player_ticks", "heatmap_points")
        }

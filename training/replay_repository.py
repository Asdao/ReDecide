"""Read-only queries for the canonical replay SQLite database."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class ReplayRepository:
    """Small query layer that keeps trainers independent of SQL details."""

    def __init__(self, path: Path, *, read_only: bool = True) -> None:
        self.path = Path(path)
        if read_only:
            uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
            self.connection = sqlite3.connect(uri, uri=True)
        else:
            self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "ReplayRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def metadata(self) -> dict[str, str]:
        try:
            rows = self.connection.execute("SELECT key,value FROM dataset_metadata").fetchall()
        except sqlite3.OperationalError:
            return {}
        return {str(row["key"]): str(row["value"]) for row in rows}

    def replay_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM replays").fetchone()[0])

    def match_count(self) -> int:
        try:
            return int(self.connection.execute("SELECT COUNT(*) FROM matches").fetchone()[0])
        except sqlite3.OperationalError:
            return self.replay_count()

    def snapshot_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0])

    def iter_snapshot_rows(self, *, include_terminal: bool = True) -> Iterator[dict[str, Any]]:
        query = (
            "SELECT s.snapshot_id,s.replay_id,r.source_path,s.round_num,s.tick,s.map_name,"
            "s.elapsed_seconds,s.ct_alive,s.t_alive,s.alive_difference,s.kills_seen,"
            "s.bomb_planted,s.bomb_site,s.label_ct_win,s.features_json,s.snapshot_json "
            "FROM snapshots s JOIN replays r ON r.replay_id=s.replay_id "
        )
        if not include_terminal:
            query += "WHERE s.ct_alive > 0 AND s.t_alive > 0 "
        query += "ORDER BY s.replay_id,s.round_num,s.tick,s.snapshot_id"
        for row in self.connection.execute(query):
            features = json.loads(row["features_json"])
            snapshot = json.loads(row["snapshot_json"])
            # Position/health features are also copied into the snapshot view
            # so runtime scorers can consume repository rows directly.
            for name, value in features.items():
                if name not in {"map_code", "bomb_site_code"}:
                    snapshot.setdefault(name, value)
            yield {
                "source": str(row["source_path"]),
                "replay_id": int(row["replay_id"]),
                "snapshot_id": int(row["snapshot_id"]),
                "round_num": int(row["round_num"]),
                "tick": int(row["tick"]),
                "label_ct_win": int(row["label_ct_win"]),
                "snapshot": snapshot,
                "features": features,
            }

    def iter_rounds(self) -> Iterator[dict[str, Any]]:
        query = (
            "SELECT r.replay_id,p.source_path,r.round_num,r.start_tick,r.end_tick,"
            "r.winner,r.reason,r.bomb_plant_tick,r.bomb_site "
            "FROM rounds r JOIN replays p ON p.replay_id=r.replay_id "
            "ORDER BY r.replay_id,r.round_num"
        )
        for row in self.connection.execute(query):
            yield dict(row)

    def iter_player_ticks(self, *, replay_id: int | None = None) -> Iterator[dict[str, Any]]:
        query = "SELECT * FROM player_ticks"
        params: tuple[Any, ...] = ()
        if replay_id is not None:
            query += " WHERE replay_id=?"
            params = (replay_id,)
        query += " ORDER BY replay_id,round_num,tick,steamid"
        for row in self.connection.execute(query, params):
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            yield item

    def iter_events(self, *, replay_id: int | None = None) -> Iterator[dict[str, Any]]:
        query = "SELECT * FROM events"
        params: tuple[Any, ...] = ()
        if replay_id is not None:
            query += " WHERE replay_id=?"
            params = (replay_id,)
        query += " ORDER BY replay_id,round_num,tick,event_id"
        for row in self.connection.execute(query, params):
            item = dict(row)
            item["payload"] = json.loads(item.pop("payload_json"))
            yield item

    def iter_actions(self, *, replay_id: int | None = None) -> Iterator[dict[str, Any]]:
        query = "SELECT * FROM inferred_actions"
        params: tuple[Any, ...] = ()
        if replay_id is not None:
            query += " WHERE replay_id=?"
            params = (replay_id,)
        query += " ORDER BY replay_id,round_num,tick,action_id"
        for row in self.connection.execute(query, params):
            item = dict(row)
            item["legal_actions"] = json.loads(item.pop("legal_actions_json"))
            item["outcome"] = json.loads(item.pop("outcome_json"))
            item["payload"] = json.loads(item.pop("payload_json"))
            yield item

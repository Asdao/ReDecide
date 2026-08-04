"""Extract leakage-safe pre-kill candidate states from normalized replays.

This module is intentionally separate from :mod:`analysis_harness`.  The
harness produces a user-facing analysis report; this extractor produces the
small, portable rows used to inspect or build candidate-action datasets.

Only information available strictly before the kill tick is copied into the
model-facing ``state`` and ``action_features`` fields.  Kill metadata is kept
as an anchor for traceability, but round winners, post-kill snapshots, and
other outcome labels are never included in those fields.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Keep the direct CLI usable from a clean checkout, matching
# ``backend/replay_engine/training/test_harness.py``. Installed-package callers already have
# these paths available, so this is a no-op for them.
_ENGINE_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _ENGINE_ROOT.parent
for _path in (_ENGINE_ROOT / "model" / "src", _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from cs2_sim.bayesian_policy import BayesianPolicy
from cs2_sim.core.model import feature_dict
from cs2_sim.rules import legal_actions

from backend.replay_engine.training.replay_state import (
    build_tick_index,
    nearest_tick_rows,
    reconstruct_game_state,
)

# Keep local private names for the extractor's existing implementation while
# exposing the shared state module as the dependency boundary.
_build_tick_index = build_tick_index
_nearest_tick_rows = nearest_tick_rows

CANDIDATE_STATE_SCHEMA_VERSION = "candidate_state_v1"


def _number(value: Any, default: float = -1.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _first(event: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = event.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _map_name(record: Mapping[str, Any]) -> str:
    header = record.get("header")
    header = header if isinstance(header, Mapping) else {}
    return str(header.get("map_name") or record.get("map_name") or "unknown")


def _tick_rate(record: Mapping[str, Any]) -> float:
    header = record.get("header")
    header = header if isinstance(header, Mapping) else {}
    value = _number(header.get("tick_rate") or record.get("tick_rate"), 64.0)
    return value if value > 0 else 64.0


def _round_start(record: Mapping[str, Any], round_num: int) -> int | None:
    for item in record.get("rounds") or ():
        if not isinstance(item, Mapping) or _int(item.get("round_num")) != round_num:
            continue
        value = _int(item.get("start"), -1)
        return value if value >= 0 else None
    return None


def _event_id(event: Mapping[str, Any], *, round_num: int, tick: int, ordinal: int) -> str:
    explicit = _first(event, "event_id", "id")
    if explicit:
        return explicit
    attacker = _first(event, "attacker_id", "attacker_steamid", "attacker_steam_id") or "unknown"
    victim = _first(
        event,
        "victim_id",
        "victim_steamid",
        "victim_steam_id",
        "user_id",
        "user_steamid",
        "user_steam_id",
    ) or "unknown"
    return f"kill-{round_num}-{tick}-{attacker}-{victim}-{ordinal}"


def _iter_kill_events(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return sorted, de-duplicated kill events from common extractor shapes."""

    streams: list[Iterable[Any]] = []
    kills = record.get("kills")
    if isinstance(kills, Sequence) and not isinstance(kills, (str, bytes)):
        streams.append(kills)
    events = record.get("events")
    if isinstance(events, Mapping):
        for name in ("kill", "kills", "player_death"):
            value = events.get(name)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                streams.append(value)

    output: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for stream in streams:
        for raw in stream:
            if not isinstance(raw, Mapping):
                continue
            event = dict(raw)
            round_num = _int(event.get("round_num"))
            tick = _int(event.get("tick"))
            if round_num < 0 or tick < 0:
                continue
            attacker = _first(event, "attacker_id", "attacker_steamid", "attacker_steam_id")
            victim = _first(
                event,
                "victim_id",
                "victim_steamid",
                "victim_steam_id",
                "user_id",
                "user_steamid",
                "user_steam_id",
            )
            weapon = _first(event, "weapon", "weapon_name") or "unknown"
            key = (round_num, tick, attacker, victim, weapon)
            if key in seen:
                continue
            seen.add(key)
            event["_attacker_id"] = attacker
            event["_victim_id"] = victim
            event["_weapon"] = weapon
            output.append(event)
    output.sort(
        key=lambda event: (
            _int(event.get("round_num")),
            _int(event.get("tick")),
            str(event.get("_attacker_id") or ""),
            str(event.get("_victim_id") or ""),
        )
    )
    return output


def _serialize_state(state: Any) -> dict[str, Any]:
    """Serialize only decision-time simulator state (never ``winner``)."""

    players = []
    for player_id, player in sorted(state.players.items()):
        players.append(
            {
                "player_id": str(player_id),
                "team": player.team.value,
                "zone": str(player.zone),
                "health": int(player.health),
                "alive": bool(player.alive),
                "has_bomb": bool(player.has_bomb),
                "utility_count": int(player.utility_count),
            }
        )
    return {
        "players": players,
        "bomb_state": state.bomb_state.value,
        "bomb_site": str(state.bomb_site),
        "bomb_carrier": state.bomb_carrier,
        "bomb_zone": state.bomb_zone,
        "bomb_time_remaining": state.bomb_time_remaining,
        "time_seconds": float(state.time_seconds),
    }


def _candidate_row(
    record: Mapping[str, Any],
    event: Mapping[str, Any],
    *,
    ordinal: int,
    tick_index: Mapping[int, Mapping[str, tuple[list[int], list[dict[str, Any]]]]] | None = None,
) -> tuple[dict[str, Any] | None, str | None]:
    round_num = _int(event.get("round_num"))
    tick = _int(event.get("tick"))
    attacker = event.get("_attacker_id")
    if attacker in (None, ""):
        return None, "missing_attacker"
    # Guard the fallback in reconstruct_game_state: no strict pre-event row
    # means we cannot prove that the state is free of same-tick kill outcomes.
    pre_rows = _nearest_tick_rows(
        record,
        round_num=round_num,
        tick=tick,
        strict_before=True,
        tick_index=tick_index,
    )
    if not pre_rows:
        return None, "missing_strict_pre_event_snapshot"
    state = reconstruct_game_state(
        record,
        round_num=round_num,
        tick=tick,
        before_event=True,
        tick_index=tick_index,
    )
    if state is None or attacker not in state.players:
        return None, "attacker_missing_from_pre_event_state"
    if not state.players[attacker].alive:
        return None, "attacker_not_alive_before_event"
    actions = legal_actions(state, attacker)
    if not actions:
        return None, "no_legal_actions"

    action_names: list[str] = []
    action_features: dict[str, dict[str, float]] = {}
    for action in actions:
        name = action.action_type.value
        if action.target_zone is not None:
            name = f"{name}:{action.target_zone}"
        action_names.append(name)
        action_features[name] = feature_dict(state, attacker, action)

    start_tick = _round_start(record, round_num)
    elapsed_seconds = None
    if start_tick is not None:
        elapsed_seconds = max(0.0, (tick - start_tick) / _tick_rate(record))
    source = record.get("source_path") or record.get("demo_file") or "unknown"
    return (
        {
            "schema_version": CANDIDATE_STATE_SCHEMA_VERSION,
            "source": str(source),
            "map_name": _map_name(record),
            "round_num": round_num,
            "decision_tick": tick,
            "decision_seconds": elapsed_seconds,
            "event": {
                "event_id": _event_id(event, round_num=round_num, tick=tick, ordinal=ordinal),
                "kind": "kill",
                "round_num": round_num,
                "tick": tick,
                "attacker_id": attacker,
                "victim_id": event.get("_victim_id"),
                "weapon": event.get("_weapon"),
            },
            "actor_id": attacker,
            "state_key": BayesianPolicy.state_key(state, attacker),
            "state": _serialize_state(state),
            "legal_actions": action_names,
            "action_features": action_features,
            "knowledge_boundary": {
                "cutoff_tick": tick,
                "snapshot_policy": "strictly_before_event",
                "post_event_outcomes_excluded": True,
            },
        },
        None,
    )


@dataclass(frozen=True, slots=True)
class CandidateStateExtraction:
    """Rows and diagnostics for one or more normalized replay records."""

    rows: tuple[dict[str, Any], ...]
    kills_seen: int
    skipped: tuple[dict[str, Any], ...]

    def summary(self) -> dict[str, Any]:
        return {
            "schema_version": CANDIDATE_STATE_SCHEMA_VERSION,
            "kills_seen": self.kills_seen,
            "rows_emitted": len(self.rows),
            "kills_skipped": len(self.skipped),
            "skip_reasons": dict(sorted(Counter(str(item["reason"]) for item in self.skipped).items())),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": CANDIDATE_STATE_SCHEMA_VERSION,
            "summary": self.summary(),
            "rows": list(self.rows),
            "skipped": list(self.skipped),
        }


def extract_candidate_states(
    record: Mapping[str, Any],
    *,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Extract one JSON-compatible pre-event row for each usable kill."""

    if not isinstance(record, Mapping):
        raise TypeError("replay record must be a mapping")
    if max_rows is not None and max_rows <= 0:
        raise ValueError("max_rows must be positive when provided")
    result: list[dict[str, Any]] = []
    tick_index = _build_tick_index(record)
    for ordinal, event in enumerate(_iter_kill_events(record)):
        row, _reason = _candidate_row(record, event, ordinal=ordinal, tick_index=tick_index)
        if row is None:
            continue
        result.append(row)
        if max_rows is not None and len(result) >= max_rows:
            break
    return result


def extract_candidate_state_report(
    records: Iterable[Mapping[str, Any]],
    *,
    max_rows: int | None = None,
) -> CandidateStateExtraction:
    """Extract rows and retain skip diagnostics for coverage evaluation."""

    if max_rows is not None and max_rows <= 0:
        raise ValueError("max_rows must be positive when provided")
    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    kills_seen = 0
    for record_index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise TypeError("each replay record must be a mapping")
        tick_index = _build_tick_index(record)
        for ordinal, event in enumerate(_iter_kill_events(record)):
            kills_seen += 1
            if max_rows is not None and len(rows) >= max_rows:
                break
            row, reason = _candidate_row(
                record, event, ordinal=ordinal, tick_index=tick_index
            )
            if row is None:
                skipped.append(
                    {
                        "record_index": record_index,
                        "round_num": _int(event.get("round_num")),
                        "tick": _int(event.get("tick")),
                        "reason": reason or "unknown",
                    }
                )
            else:
                row["record_index"] = record_index
                rows.append(row)
        if max_rows is not None and len(rows) >= max_rows:
            break
    return CandidateStateExtraction(tuple(rows), kills_seen, tuple(skipped))


def iter_replay_records(path: str | Path) -> Iterator[dict[str, Any]]:
    """Yield replay objects without materializing a large JSONL dataset."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"replay input does not exist: {source}")
    with source.open(encoding="utf-8") as handle:
        first_line = next((line for line in handle if line.strip()), None)
        if first_line is None:
            raise ValueError(f"replay input is empty: {source}")
        if first_line.lstrip().startswith("["):
            payload = json.loads(first_line + handle.read())
            records = payload if isinstance(payload, list) else [payload]
            if not all(isinstance(item, dict) for item in records):
                raise TypeError("replay input must contain JSON objects")
            yield from records
            return
        try:
            first = json.loads(first_line)
        except json.JSONDecodeError:
            # Support a pretty-printed JSON object as a small-file fallback.
            payload = json.loads(first_line + handle.read())
            records = payload if isinstance(payload, list) else [payload]
            if not all(isinstance(item, dict) for item in records):
                raise TypeError("replay input must contain JSON objects")
            yield from records
            return
        if not isinstance(first, dict):
            raise TypeError("replay input must contain JSON objects")
        yield first
        for line_number, line in enumerate(handle, start=2):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if not isinstance(record, dict):
                raise TypeError("replay input must contain JSON objects")
            yield record


def load_replay_records(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON object/list or compact JSONL replay input."""

    return list(iter_replay_records(path))


def write_candidate_states(
    input_path: str | Path,
    output_path: str | Path,
    *,
    output_format: str | None = None,
    max_rows: int | None = None,
) -> CandidateStateExtraction:
    """Extract a file and write either a JSON report or JSONL rows."""

    report = extract_candidate_state_report(iter_replay_records(input_path), max_rows=max_rows)
    output = Path(output_path)
    fmt = (output_format or ("jsonl" if output.suffix.lower() == ".jsonl" else "json")).lower()
    if fmt not in {"json", "jsonl"}:
        raise ValueError("output_format must be json or jsonl")
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(f"{output.name}.part")
    if fmt == "jsonl":
        payload = "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in report.rows)
    else:
        payload = json.dumps(report.to_dict(), indent=2) + "\n"
    partial.write_text(payload, encoding="utf-8")
    partial.replace(output)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="normalized replay JSON or JSONL")
    parser.add_argument("output", type=Path, help="candidate-state JSON or JSONL output")
    parser.add_argument("--format", choices=("json", "jsonl"), default=None)
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args()
    report = write_candidate_states(
        args.input,
        args.output,
        output_format=args.format,
        max_rows=args.max_rows,
    )
    print(json.dumps(report.summary(), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CANDIDATE_STATE_SCHEMA_VERSION",
    "CandidateStateExtraction",
    "extract_candidate_state_report",
    "extract_candidate_states",
    "iter_replay_records",
    "load_replay_records",
    "main",
    "write_candidate_states",
]

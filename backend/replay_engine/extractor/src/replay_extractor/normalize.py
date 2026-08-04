"""Convert parser-specific JSON records to the stable replay schema."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .models import EventRecord, PlayerTick, ReplayMetadata, ReplayRecord, RoundRecord


SCHEMA_VERSION = 2
"""Version of the canonical extractor contract.

Version 2 makes the tick-rate and field normalisation rules explicit.  The
normaliser still accepts schema 1 records so existing sidecars can be tested
without rewriting them first.
"""

DEFAULT_TICK_RATE = 64.0
SUPPORTED_SCHEMA_VERSIONS = frozenset({1, SCHEMA_VERSION})
REQUIRED_V2_FIELDS = frozenset({"header", "rounds", "ticks"})


def normalize_record(
    raw: dict[str, Any],
    *,
    source_path: str | None = None,
    default_tick_rate: float = DEFAULT_TICK_RATE,
) -> ReplayRecord:
    """Normalize one parsed record without mutating the input payload."""

    _validate_raw(raw, default_tick_rate=default_tick_rate)

    header = dict(raw.get("header") or {})
    match = dict(raw.get("match") or {})
    source = str(source_path or raw.get("source_path") or raw.get("demo_file") or "unknown")
    demo_file = str(raw.get("demo_file") or Path(source).name)
    parser = str(raw.get("parser") or "unknown")
    map_name = _map_name(header.get("map_name") or match.get("map_name"))
    tick_rate = _number(
        header.get("tick_rate") or match.get("tick_rate") or raw.get("tick_rate"),
        default_tick_rate,
    )
    # Keep the effective rate in the canonical metadata/header.  Existing
    # header keys are never overwritten, which preserves parser metadata.
    header.setdefault("tick_rate", tick_rate)
    checksum = str(raw.get("checksum") or hashlib.sha256(_stable_json(raw).encode()).hexdigest())
    replay_id = str(raw.get("replay_id") or hashlib.sha256(f"{source}:{checksum}".encode()).hexdigest()[:24])
    metadata = ReplayMetadata(replay_id, source, demo_file, parser, map_name, tick_rate, checksum, header)

    rounds = tuple(_rounds(replay_id, raw.get("rounds") or []))
    events = tuple(_events(replay_id, raw))
    player_ticks = tuple(_ticks(replay_id, raw.get("ticks") or []))
    return ReplayRecord(metadata, rounds, events, player_ticks)


def _rounds(replay_id: str, rows: Iterable[dict[str, Any]]) -> Iterable[RoundRecord]:
    for row in rows:
        yield RoundRecord(
            replay_id,
            _integer(row.get("round_num")),
            _optional_integer(_first_present(row, "start", "start_tick")),
            _optional_integer(_first_present(row, "end", "official_end", "end_tick")),
            _side(row.get("winner")),
            _optional_text(row.get("reason")),
            _optional_integer(_first_present(row, "bomb_plant", "bomb_plant_tick")),
            _normalise_bomb_site(row.get("bomb_site")),
        )


def _events(replay_id: str, raw: dict[str, Any]) -> Iterable[EventRecord]:
    sources: list[tuple[str, Iterable[dict[str, Any]]]] = [
        ("kill", raw.get("kills") or []),
        ("damage", raw.get("damages") or []),
        ("bomb", raw.get("bomb") or []),
    ]
    for event_type, rows in (raw.get("events") or {}).items():
        sources.append((str(event_type).lower(), rows or []))
    ordinal = 0
    for event_type, rows in sources:
        for row in rows:
            ordinal += 1
            payload = dict(row)
            yield EventRecord(
                replay_id,
                f"{replay_id}:evt:{ordinal}",
                _optional_integer(row.get("round_num")),
                _optional_integer(row.get("tick")),
                event_type,
                _identity(row, "attacker_steamid", "attacker_id"),
                _identity(row, "victim_steamid", "victim_id"),
                _identity(row, "steamid", "player_steamid", "actor_steamid"),
                _side(row.get("attacker_side") or row.get("side") or row.get("team_name")),
                _normalise_bomb_site(row.get("bombsite") or row.get("site") or row.get("which_bomb_zone")),
                _optional_text(row.get("weapon")),
                payload,
            )


def _ticks(replay_id: str, rows: Iterable[dict[str, Any]]) -> Iterable[PlayerTick]:
    for ordinal, row in enumerate(rows):
        yield PlayerTick(
            replay_id,
            _integer(row.get("round_num")),
            _integer(row.get("tick")),
            _identity(row, "steamid", "steam_id", "player_steamid", "name", "player_name") or f"anonymous:{ordinal}",
            _optional_text(row.get("player_name") or row.get("name")),
            _side(row.get("team_name") or row.get("side")),
            _coordinate(row, "X", "x"),
            _coordinate(row, "Y", "y"),
            _coordinate(row, "Z", "z"),
            _optional_integer(row.get("health")),
            _optional_integer(_first_present(row, "armor_value", "armor")),
            _optional_bool(row.get("alive")),
            _optional_text(row.get("last_place_name") or row.get("zone")),
            dict(row),
        )


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _number(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _integer(value: Any) -> int:
    return int(_number(value, 0.0))


def _optional_integer(value: Any) -> int | None:
    return None if value is None else _integer(value)


def _optional_text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _identity(row: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _coordinate(row: dict[str, Any], *keys: str) -> float | None:
    value = next((row.get(key) for key in keys if row.get(key) is not None), None)
    return None if value is None else _number(value, 0.0)


def _optional_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return str(value).lower() not in {"0", "false", "dead", "none"}


def _side(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return None


def _validate_raw(raw: Any, *, default_tick_rate: float) -> None:
    """Validate the extractor boundary before building canonical records.

    Legacy records often omitted empty ``rounds``/``ticks`` keys, so those
    omissions remain accepted for schema 1.  New schema-2 output is strict so
    malformed records cannot silently become all-zero model inputs.
    """

    if not isinstance(raw, dict):
        raise TypeError("extractor record must be a JSON object")
    version = raw.get("schema_version", 1)
    try:
        version = int(version)
    except (TypeError, ValueError) as exc:
        raise ValueError("schema_version must be an integer") from exc
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise ValueError(
            f"unsupported extractor schema_version={version}; "
            f"supported versions are {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    if not math.isfinite(float(default_tick_rate)) or default_tick_rate <= 0:
        raise ValueError("default_tick_rate must be a positive finite number")
    if version >= SCHEMA_VERSION:
        missing = sorted(REQUIRED_V2_FIELDS.difference(raw))
        if missing:
            raise ValueError(f"schema {SCHEMA_VERSION} record is missing required fields: {', '.join(missing)}")
    if "header" in raw and not isinstance(raw["header"], dict):
        raise ValueError("extractor header must be an object")
    for field in ("rounds", "ticks", "kills", "damages", "bomb"):
        if field in raw and not isinstance(raw[field], list):
            raise ValueError(f"extractor field {field!r} must be a list")
    events = raw.get("events")
    if events is not None and not isinstance(events, dict):
        raise ValueError("extractor events must be an object keyed by event type")
    if "tick_rate" in raw and raw["tick_rate"] is not None:
        rate = _number(raw["tick_rate"], float("nan"))
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("extractor tick_rate must be a positive finite number")


def _first_present(row: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None:
            return row[key]
    return None


def _map_name(value: Any) -> str:
    return str(value or "unknown").strip().lower()


def _normalise_bomb_site(value: Any) -> str | None:
    """Canonicalise Awpy's ``BombsiteA``/``bombsite_a`` forms to a/b."""

    if value is None:
        return None
    text = str(value).strip().lower().replace("-", "").replace("_", "")
    if not text or text in {"none", "notplanted", "unknown", "null"}:
        return None
    if text in {"a", "bombsitea", "sitea"}:
        return "a"
    if text in {"b", "bombsiteb", "siteb"}:
        return "b"
    return str(value).strip().lower()

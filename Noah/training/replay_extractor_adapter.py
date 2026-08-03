"""Tester-only bridge for the standalone ``extractor`` package.

The extractor owns ingestion and normalization.  The model pipeline still
consumes its historical Awpy-shaped dictionaries, so this module translates
records in memory at the tester boundary.  It deliberately does not write a
database, alter training data, or rebuild model artifacts.
"""

from __future__ import annotations

import sys
from dataclasses import is_dataclass
from pathlib import Path
from collections.abc import Iterator
from typing import Any, Mapping


def _load_extractor_normalizer() -> Any:
    """Load the sibling package without making it a runtime dependency."""

    package_root = Path(__file__).resolve().parents[1] / "extractor" / "src"
    if package_root.exists() and str(package_root) not in sys.path:
        sys.path.insert(0, str(package_root))
    try:
        from replay_extractor import normalize_record
    except ImportError as exc:  # pragma: no cover - only used for broken installs
        raise RuntimeError(
            "the replacement extractor is unavailable; keep extractor in the "
            "workspace or install it with `python -m pip install -e extractor`"
        ) from exc
    return normalize_record


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _payload(value: Any) -> dict[str, Any]:
    payload = _value(value, "payload", {})
    return dict(payload) if isinstance(payload, Mapping) else {}


def _canonical_to_raw(record: Any) -> dict[str, Any]:
    """Convert a canonical ``ReplayRecord`` (or its JSON mapping) to raw rows."""

    metadata = _value(record, "metadata", {})
    header = dict(_value(metadata, "header", {}) or {})
    map_name = _value(metadata, "map_name")
    tick_rate = _value(metadata, "tick_rate")
    if map_name and not header.get("map_name"):
        header["map_name"] = map_name
    if tick_rate and not header.get("tick_rate"):
        header["tick_rate"] = tick_rate

    raw: dict[str, Any] = {
        "schema_version": 2,
        "parser": _value(metadata, "parser", "replay-extractor"),
        "demo_file": _value(metadata, "demo_file", "unknown"),
        "source_path": _value(metadata, "source_path", "unknown"),
        "tick_rate": tick_rate or 64.0,
        "header": header,
        "rounds": [],
        "kills": [],
        "damages": [],
        "bomb": [],
        "events": {},
        "ticks": [],
    }

    for round_row in _value(record, "rounds", ()) or ():
        raw["rounds"].append(
            {
                "round_num": _value(round_row, "round_num", 0),
                "start": _value(round_row, "start_tick"),
                "end": _value(round_row, "end_tick"),
                "winner": _value(round_row, "winner"),
                "reason": _value(round_row, "reason"),
                "bomb_plant": _value(round_row, "bomb_plant_tick"),
                "bomb_site": _normalise_bomb_site(_value(round_row, "bomb_site")),
            }
        )

    for tick_row in _value(record, "player_ticks", ()) or ():
        row = _payload(tick_row)
        _fill(row, "round_num", _value(tick_row, "round_num"))
        _fill(row, "tick", _value(tick_row, "tick"))
        _fill(row, "steamid", _value(tick_row, "player_id"))
        _fill(row, "player_name", _value(tick_row, "player_name"))
        _fill(row, "team_name", _value(tick_row, "side"))
        _fill(row, "X", _value(tick_row, "x"))
        _fill(row, "Y", _value(tick_row, "y"))
        _fill(row, "Z", _value(tick_row, "z"))
        _fill(row, "health", _value(tick_row, "health"))
        # Keep both parser spellings available. The shared feature contract
        # resolves them in a deterministic order, so this does not alter the
        # value distribution while making canonical records interoperable.
        armor = _value(tick_row, "armor")
        if row.get("armor_value") is None and row.get("armor") is None:
            _fill(row, "armor_value", armor)
        if row.get("armor_value") is None and row.get("armor") is not None:
            row["armor_value"] = row["armor"]
        if row.get("armor") is None and row.get("armor_value") is not None:
            row["armor"] = row["armor_value"]
        _fill(row, "alive", _value(tick_row, "alive"))
        _fill(row, "zone", _value(tick_row, "zone"))
        raw["ticks"].append(row)

    for event_row in _value(record, "events", ()) or ():
        event_type = str(_value(event_row, "event_type", "event")).lower()
        row = _payload(event_row)
        _fill(row, "round_num", _value(event_row, "round_num"))
        _fill(row, "tick", _value(event_row, "tick"))
        _fill(row, "attacker_steamid", _value(event_row, "attacker_id"))
        _fill(row, "victim_steamid", _value(event_row, "victim_id"))
        _fill(row, "steamid", _value(event_row, "actor_id"))
        _fill(row, "attacker_side", _value(event_row, "side"))
        site = _value(event_row, "site")
        if site is not None:
            row["bombsite"] = _normalise_bomb_site(site)
        _fill(row, "weapon", _value(event_row, "weapon"))
        _fill(row, "event", event_type)
        # ``player_death``, ``player_hurt`` and ``bomb_planted`` are generic
        # event streams in the source record. They must not be promoted into
        # kills/damages/bomb because the dedicated streams already contain
        # those rows.
        if event_type == "kill":
            raw["kills"].append(row)
        elif event_type == "damage":
            raw["damages"].append(row)
        elif event_type == "bomb":
            raw["bomb"].append(row)
        else:
            raw["events"].setdefault(event_type, []).append(row)
    return raw


def _fill(row: dict[str, Any], key: str, value: Any) -> None:
    """Fill a canonical alias without overwriting parser-native fields."""

    if key not in row and value is not None:
        row[key] = value


def _normalise_bomb_site(value: Any) -> str | None:
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


def normalize_extractor_record(raw: Any) -> dict[str, Any]:
    """Normalize one replacement-extractor record for model testing."""

    if isinstance(raw, Mapping) and "metadata" not in raw:
        normalized = _load_extractor_normalizer()(dict(raw))
    elif isinstance(raw, Mapping) and "metadata" in raw:
        normalized = raw
    elif is_dataclass(raw) or hasattr(raw, "metadata"):
        normalized = raw
    else:
        raise TypeError("extractor record must be a mapping or ReplayRecord")
    return _canonical_to_raw(normalized)


def iter_extractor_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield normalized extractor records lazily for bounded testers."""

    try:
        from replay_extractor import load_jsonl
    except ImportError:
        _load_extractor_normalizer()
        from replay_extractor import load_jsonl
    for raw in load_jsonl(path):
        yield normalize_extractor_record(raw)


def parse_extractor_demo(path: Path, *, tick_interval: int = 32) -> dict[str, Any]:
    """Parse one native demo through the replacement extractor for testing."""

    try:
        from replay_extractor import parse_demo
    except ImportError:
        _load_extractor_normalizer()
        from replay_extractor import parse_demo
    return normalize_extractor_record(parse_demo(path, tick_interval=tick_interval))

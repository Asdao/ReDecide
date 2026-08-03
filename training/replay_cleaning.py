"""Pure audit and cleaning helpers for parsed CS2 replay records.

The raw JSONL is never edited.  Cleaning returns a new record and a report so
that a training database can record exactly which policy produced it.
"""

from __future__ import annotations

import copy
import math
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable


CLEANING_VERSION = "1.0"
KNOWN_MAPS = frozenset(
    {
        "de_ancient",
        "de_anubis",
        "de_dust2",
        "de_inferno",
        "de_mirage",
        "de_nuke",
        "de_overpass",
        "de_vertigo",
    }
)


@dataclass(frozen=True, slots=True)
class CleaningOptions:
    """Versioned policy knobs shared by auditing and database materialisation."""

    max_round_seconds: float = 180.0
    coordinate_limit: float = 20_000.0
    drop_invalid_rounds: bool = True
    drop_duplicate_player_ticks: bool = True


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _side(value: Any) -> str | None:
    text = str(value or "").lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return "ct"
    if text in {"t", "terrorist"}:
        return "t"
    return None


def _map_name(record: dict[str, Any]) -> str:
    header = record.get("header") or {}
    match = record.get("match") or {}
    return str(header.get("map_name") or match.get("map_name") or "unknown").lower()


def _player_key(row: dict[str, Any], ordinal: int) -> str:
    for key in ("steamid", "steam_id", "player_steamid", "name", "player_name"):
        value = row.get(key)
        if value not in (None, ""):
            return str(value)
    # A missing identity is still auditable, but rows without identities must
    # not all collapse into one duplicate bucket.
    return f"anonymous:{ordinal}"


def audit_record(record: dict[str, Any], *, options: CleaningOptions | None = None) -> dict[str, Any]:
    """Return a JSON-serialisable quality report for one replay record."""

    policy = options or CleaningOptions()
    issues: list[dict[str, Any]] = []
    rounds = record.get("rounds") or []
    ticks = record.get("ticks") or []
    map_name = _map_name(record)
    if map_name not in KNOWN_MAPS:
        issues.append({"code": "unknown_map", "severity": "warning", "value": map_name})
    if not rounds:
        issues.append({"code": "missing_rounds", "severity": "error"})
    if not ticks:
        issues.append({"code": "missing_ticks", "severity": "warning"})

    round_stats: list[dict[str, Any]] = []
    valid_rounds: set[int] = set()
    for raw_round in rounds:
        round_num = int(_number(raw_round.get("round_num"), -1))
        start = int(_number(raw_round.get("start"), -1))
        end = int(_number(raw_round.get("end") or raw_round.get("official_end"), -1))
        winner = _side(raw_round.get("winner"))
        duration = None
        if start >= 0 and end >= start:
            tick_rate = _number((record.get("header") or {}).get("tick_rate"), 128.0)
            duration = (end - start) / max(tick_rate, 1.0)
        row = {"round_num": round_num, "winner": winner, "duration_seconds": duration}
        round_stats.append(row)
        valid = round_num >= 0 and winner is not None and start >= 0 and end >= start
        if not valid:
            issues.append({"code": "invalid_round", "severity": "error", "round_num": round_num})
        elif duration is not None and duration > policy.max_round_seconds:
            issues.append(
                {
                    "code": "long_round",
                    "severity": "warning",
                    "round_num": round_num,
                    "duration_seconds": duration,
                }
            )
        else:
            valid_rounds.add(round_num)

    tick_keys: Counter[tuple[int, int]] = Counter()
    player_tick_keys: Counter[tuple[int, int, str]] = Counter()
    coordinate_outliers = 0
    non_monotonic_rounds: set[int] = set()
    previous_tick: dict[int, int] = {}
    for ordinal, row in enumerate(ticks):
        round_num = int(_number(row.get("round_num"), -1))
        tick = int(_number(row.get("tick"), -1))
        tick_keys[(round_num, tick)] += 1
        player_tick_keys[(round_num, tick, _player_key(row, ordinal))] += 1
        if round_num in previous_tick and tick < previous_tick[round_num]:
            non_monotonic_rounds.add(round_num)
        previous_tick[round_num] = tick
        for coordinate in ("X", "Y", "Z", "x", "y", "z"):
            if coordinate in row and abs(_number(row.get(coordinate))) > policy.coordinate_limit:
                coordinate_outliers += 1
                break
    if non_monotonic_rounds:
        issues.append(
            {
                "code": "non_monotonic_ticks",
                "severity": "warning",
                "rounds": sorted(non_monotonic_rounds),
            }
        )
    duplicate_player_ticks = sum(count - 1 for count in player_tick_keys.values() if count > 1)
    if duplicate_player_ticks:
        issues.append(
            {"code": "duplicate_player_ticks", "severity": "warning", "count": duplicate_player_ticks}
        )
    if coordinate_outliers:
        issues.append(
            {"code": "coordinate_outliers", "severity": "warning", "count": coordinate_outliers}
        )

    return {
        "cleaning_version": CLEANING_VERSION,
        "source": str(record.get("demo_file") or "unknown"),
        "parser": str(record.get("parser") or "unknown"),
        "map_name": map_name,
        "round_count": len(rounds),
        "tick_row_count": len(ticks),
        "duplicate_tick_keys": sum(count - 1 for count in tick_keys.values() if count > 1),
        "duplicate_player_ticks": duplicate_player_ticks,
        "coordinate_outliers": coordinate_outliers,
        "valid_rounds": len(valid_rounds),
        "rounds": round_stats,
        "issues": issues,
        "error_count": sum(issue["severity"] == "error" for issue in issues),
        "warning_count": sum(issue["severity"] == "warning" for issue in issues),
    }


def clean_record(record: dict[str, Any], *, options: CleaningOptions | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return a cleaned copy and its audit report without mutating ``record``."""

    policy = options or CleaningOptions()
    report = audit_record(record, options=policy)
    cleaned = copy.deepcopy(record)
    valid_rounds = {
        int(row["round_num"])
        for row in report["rounds"]
        if row["winner"] in {"ct", "t"}
        and row["duration_seconds"] is not None
        and row["duration_seconds"] <= policy.max_round_seconds
    }
    if not policy.drop_invalid_rounds:
        valid_rounds = {int(row["round_num"]) for row in report["rounds"] if row["round_num"] >= 0}

    if policy.drop_invalid_rounds:
        cleaned["rounds"] = [
            row for row in cleaned.get("rounds") or [] if int(_number(row.get("round_num"), -1)) in valid_rounds
        ]
        for key in ("ticks", "kills", "damages", "bomb"):
            cleaned[key] = [
                row
                for row in cleaned.get(key) or []
                if int(_number(row.get("round_num"), -1)) in valid_rounds
            ]

    if policy.drop_duplicate_player_ticks and cleaned.get("ticks"):
        seen: set[tuple[int, int, str]] = set()
        deduplicated: list[dict[str, Any]] = []
        for ordinal, row in enumerate(cleaned["ticks"]):
            key = (
                int(_number(row.get("round_num"), -1)),
                int(_number(row.get("tick"), -1)),
                _player_key(row, ordinal),
            )
            if key in seen:
                continue
            seen.add(key)
            deduplicated.append(row)
        cleaned["ticks"] = deduplicated
    cleaned["cleaning_version"] = CLEANING_VERSION
    return cleaned, report


def clean_records(
    records: Iterable[dict[str, Any]], *, options: CleaningOptions | None = None
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Clean records and aggregate their reports for a versioned dataset."""

    cleaned: list[dict[str, Any]] = []
    reports: list[dict[str, Any]] = []
    for record in records:
        item, report = clean_record(record, options=options)
        cleaned.append(item)
        reports.append(report)
    return cleaned, {
        "cleaning_version": CLEANING_VERSION,
        "replay_count": len(reports),
        "error_count": sum(int(report["error_count"]) for report in reports),
        "warning_count": sum(int(report["warning_count"]) for report in reports),
        "reports": reports,
    }

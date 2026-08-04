"""Read-only diagnostics for candidate-action state coverage.

The action scorer can only make a supported recommendation when a replay state
has enough training/simulation observations.  This module does not retrain a
model or mutate replay data.  It inspects either a canonical replay record or a
``combined_replay_analysis`` report and returns a compact, JSON-compatible
coverage summary.

Examples
--------
    python Blackbox/training/candidate_coverage.py \
        data/private/processed/coach_full_fixture.analysis.json

    python Blackbox/training/candidate_coverage.py \
        data/private/processed/full_replays.jsonl --min-support 5
"""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

COVERAGE_SCHEMA_VERSION = "candidate_coverage_v1"
_CANDIDATE_STATE_SCHEMA_VERSION = "candidate_state_v1"
_DIMENSION_NAMES = (
    "map",
    "side",
    "zone",
    "bomb_state",
    "alive_difference",
    "time_bucket",
)
_UNKNOWN = "unknown"


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: Any, default: str = _UNKNOWN) -> str:
    if value in (None, ""):
        return default
    return str(value).strip() or default


def _number(value: Any, default: float | None = None) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _integer(value: Any, default: int | None = None) -> int | None:
    number = _number(value, None)
    if number is None:
        return default
    return int(number)


def _bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in {"true", "yes", "y", "1", "on"}:
            return True
        if text in {"false", "no", "n", "0", "off"}:
            return False
    return None


def _event_key(event: Mapping[str, Any], ordinal: int = 0) -> tuple[Any, ...]:
    """Return a stable key for matching kills across report sections."""

    event_id = event.get("event_id")
    if event_id not in (None, ""):
        return ("event_id", str(event_id))
    round_num = _integer(event.get("round_num"), -1)
    tick = _integer(event.get("tick"), -1)
    attacker = _text(event.get("attacker_id") or event.get("attacker_steamid"), "")
    victim = _text(
        event.get("victim_id")
        or event.get("victim_steamid")
        or event.get("victim_steam_id")
        or event.get("user_id")
        or event.get("user_steamid")
        or event.get("user_steam_id"),
        "",
    )
    weapon = _text(event.get("weapon"), "")
    if round_num >= 0 or tick >= 0 or attacker or victim or weapon:
        # Do not include the list ordinal when facts exist: report sections
        # can sort the same kill differently while still referring to it.
        return ("facts", round_num, tick, attacker, victim, weapon)
    return ("ordinal", ordinal)


def _event_signature(event: Mapping[str, Any]) -> tuple[Any, ...]:
    """Signature used to de-duplicate parser event streams."""

    return (
        _integer(event.get("round_num"), -1),
        _integer(event.get("tick"), -1),
        _text(event.get("attacker_id") or event.get("attacker_steamid"), ""),
        _text(
            event.get("victim_id")
            or event.get("victim_steamid")
            or event.get("victim_steam_id")
            or event.get("user_id")
            or event.get("user_steamid")
            or event.get("user_steam_id"),
            "",
        ),
        _text(event.get("weapon"), ""),
    )


def _is_kill(event: Mapping[str, Any], *, key: str | None = None) -> bool:
    category = str(event.get("category") or "").lower()
    event_type = str(event.get("event_type") or event.get("event") or "").lower()
    source = str(key or event.get("source") or "").lower()
    # ``player_death`` is a common canonical parser stream.  Only accept it
    # when it came from an explicitly named stream; treating every generic
    # ``death`` event as a kill would double-count combined reports.
    return (
        category == "kill"
        or "kill" in event_type
        or source in {"kills", "kill", "player_death"}
    )


def _is_candidate_state_payload(payload: Mapping[str, Any]) -> bool:
    if str(payload.get("schema_version") or "") == _CANDIDATE_STATE_SCHEMA_VERSION:
        return True
    summary = _mapping(payload.get("summary"))
    return str(summary.get("schema_version") or "") == _CANDIDATE_STATE_SCHEMA_VERSION


def _report_type(payload: Mapping[str, Any]) -> str:
    return str(payload.get("report_type") or "").strip().lower()


def _declared_kill_count(payload: Mapping[str, Any]) -> int | None:
    summary = _mapping(payload.get("summary"))
    value = _integer(summary.get("kill_count"), None)
    if value is not None and value >= 0:
        return value
    full_match = _mapping(payload.get("full_match"))
    full_summary = _mapping(full_match.get("summary"))
    value = _integer(full_summary.get("kill_count"), None)
    if value is not None and value >= 0:
        return value
    counts = _mapping(full_match.get("event_counts"))
    value = _integer(counts.get("kill"), None)
    return value if value is not None and value >= 0 else None


def _declared_analyzed_count(payload: Mapping[str, Any]) -> int | None:
    summary = _mapping(payload.get("summary"))
    value = _integer(summary.get("kill_analysis_count"), None)
    if value is not None and value >= 0:
        return value
    return None


def _canonical_kills(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Read dedicated kill rows, falling back to parser event streams."""

    dedicated = [
        dict(item) for item in record.get("kills") or [] if isinstance(item, Mapping)
    ]
    candidates: list[dict[str, Any]] = dedicated
    if not candidates:
        groups = record.get("events")
        if isinstance(groups, Mapping):
            for name, values in groups.items():
                if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                    continue
                for value in values:
                    if isinstance(value, Mapping) and _is_kill(value, key=str(name)):
                        candidates.append(dict(value))
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in candidates:
        unique.setdefault(_event_signature(item), item)
    return list(unique.values())


def _report_kills(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    full_match = _mapping(report.get("full_match"))
    event_rows = full_match.get("events")
    if not isinstance(event_rows, Sequence) or isinstance(event_rows, (str, bytes)):
        event_rows = report.get("events")
    rows: list[dict[str, Any]] = []
    if isinstance(event_rows, Sequence) and not isinstance(event_rows, (str, bytes)):
        rows = [
            dict(item)
            for item in event_rows
            if isinstance(item, Mapping) and _is_kill(item)
        ]
    if not rows:
        # A report may omit full_match while retaining its kill_analysis rows.
        rows = [
            dict(item)
            for item in report.get("kill_analysis") or []
            if isinstance(item, Mapping)
        ]
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in rows:
        unique.setdefault(_event_signature(item), item)
    return list(unique.values())


def _kill_rows(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    if _report_type(payload) == "combined_replay_analysis" or "full_match" in payload:
        return _report_kills(payload)
    return _canonical_kills(payload)


def _analyzed_kill_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = [
        dict(item)
        for item in report.get("kill_analysis") or []
        if isinstance(item, Mapping)
    ]
    if rows:
        return rows
    result: list[dict[str, Any]] = []
    for moment in report.get("moments") or []:
        if not isinstance(moment, Mapping):
            continue
        result.extend(
            dict(event)
            for event in moment.get("events") or []
            if isinstance(event, Mapping) and _is_kill(event)
        )
    return result


def _time_bucket(value: Any) -> str:
    seconds = _number(value, None)
    if seconds is None or seconds < 0:
        return _UNKNOWN
    if seconds < 30:
        return "0-29s"
    if seconds < 60:
        return "30-59s"
    if seconds < 90:
        return "60-89s"
    return "90s+"


def _bomb_state(state: Mapping[str, Any], snapshot: Mapping[str, Any]) -> str:
    value = state.get("bomb_state") or state.get("bomb") or snapshot.get("bomb_state")
    if value not in (None, ""):
        return _text(value).lower()
    planted = _bool(snapshot.get("bomb_planted"))
    site = _text(snapshot.get("bomb_site"), "none").lower()
    if planted:
        return f"planted_{site}" if site not in {"none", _UNKNOWN} else "planted"
    if planted is False:
        return "none"
    return _UNKNOWN


def _dimensions(
    payload: Mapping[str, Any],
    *,
    moment: Mapping[str, Any] | None = None,
    event: Mapping[str, Any] | None = None,
) -> dict[str, str]:
    """Extract stable state dimensions without reconstructing or mutating state."""

    moment = _mapping(moment)
    event = _mapping(event)
    state = _mapping(moment.get("state_dimensions") or moment.get("state"))
    snapshot = _mapping(moment.get("snapshot"))
    top_header = _mapping(payload.get("header"))
    map_name = (
        state.get("map")
        or state.get("map_name")
        or snapshot.get("map_name")
        or payload.get("map_name")
        or top_header.get("map_name")
        or _mapping(payload.get("full_match")).get("map_name")
    )
    side = (
        state.get("side")
        or moment.get("side")
        or event.get("attacker_side")
        or event.get("side")
        or event.get("team")
    )
    zone = (
        state.get("zone")
        or state.get("attacker_zone")
        or moment.get("zone")
        or moment.get("actor_zone")
        or event.get("attacker_zone")
        or event.get("zone")
    )
    alive_difference = (
        state.get("alive_difference")
        or snapshot.get("alive_difference")
        or moment.get("alive_difference")
    )
    if alive_difference in (None, ""):
        ct_alive = _number(snapshot.get("ct_alive"), None)
        t_alive = _number(snapshot.get("t_alive"), None)
        if ct_alive is not None and t_alive is not None:
            alive_difference = ct_alive - t_alive
    alive_value = _integer(alive_difference, None)
    alive_label = str(alive_value) if alive_value is not None else _UNKNOWN
    elapsed = (
        state.get("elapsed_seconds")
        or snapshot.get("elapsed_seconds")
        or snapshot.get("time_seconds")
        or moment.get("time_seconds")
    )
    if elapsed in (None, ""):
        tick = _number(moment.get("decision_tick") or moment.get("tick"), None)
        tick_rate = _number(
            top_header.get("tick_rate") or payload.get("tick_rate"), 64.0
        )
        if tick is not None and tick_rate and tick_rate > 0:
            elapsed = tick / tick_rate
    return {
        "map": _text(map_name).lower(),
        "side": _text(side).lower(),
        "zone": _text(zone),
        "bomb_state": _bomb_state(state, snapshot),
        "alive_difference": alive_label,
        "time_bucket": _time_bucket(elapsed),
    }


def _nearest_tick_rows(
    record: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, Mapping[str, Any]]:
    round_num = _integer(event.get("round_num"), -1)
    tick = _integer(event.get("tick"), -1)
    latest: dict[str, tuple[int, Mapping[str, Any]]] = {}
    for ordinal, row in enumerate(record.get("ticks") or []):
        if (
            not isinstance(row, Mapping)
            or _integer(row.get("round_num"), -1) != round_num
        ):
            continue
        row_tick = _integer(row.get("tick"), -1)
        if row_tick < 0 or (tick is not None and row_tick > tick):
            continue
        identity = _text(
            row.get("steamid")
            or row.get("steam_id")
            or row.get("player_steamid")
            or row.get("name"),
            f"anonymous:{ordinal}",
        )
        previous = latest.get(identity)
        if previous is None or row_tick >= previous[0]:
            latest[identity] = (row_tick, row)
    if not latest:
        return {}
    return {key: row for key, (_, row) in latest.items()}


def _canonical_dimensions(
    record: Mapping[str, Any], event: Mapping[str, Any]
) -> dict[str, str]:
    rows = _nearest_tick_rows(record, event)
    attacker = _text(event.get("attacker_steamid") or event.get("attacker_id"), "")
    actor = rows.get(attacker, {})
    side = (
        event.get("attacker_side")
        or event.get("side")
        or actor.get("side")
        or actor.get("team")
    )
    zones = [row for row in rows.values() if isinstance(row, Mapping)]
    ct_alive = sum(
        1
        for row in zones
        if _text(row.get("side") or row.get("team"), "").lower() == "ct"
        and (_bool(row.get("alive")) is not False)
        and _number(row.get("health"), 100) > 0
    )
    t_alive = sum(
        1
        for row in zones
        if _text(row.get("side") or row.get("team"), "").lower() in {"t", "terrorist"}
        and (_bool(row.get("alive")) is not False)
        and _number(row.get("health"), 100) > 0
    )
    tick = _number(event.get("tick"), None)
    tick_rate = _number(
        _mapping(record.get("header")).get("tick_rate") or record.get("tick_rate"), 64.0
    )
    snapshot = {
        "map_name": _mapping(record.get("header")).get("map_name")
        or record.get("map_name"),
        "alive_difference": ct_alive - t_alive if rows else None,
        "elapsed_seconds": tick / tick_rate
        if tick is not None and tick_rate and tick_rate > 0
        else None,
        "bomb_planted": None,
    }
    return _dimensions(
        record,
        moment={
            "snapshot": snapshot,
            "side": side,
            "zone": actor.get("place") or actor.get("zone"),
        },
        event=event,
    )


def _support_status(
    row: Mapping[str, Any], min_support: int
) -> tuple[bool, str | None, int | None]:
    support = _integer(row.get("sample_count"), None)
    explicit = _bool(row.get("supported"))
    if explicit is True and (support is None or support >= min_support):
        return True, None, support
    if support is None:
        return False, "missing_support", None
    if support < min_support:
        return False, "support_below_threshold", support
    entropy = _number(row.get("entropy"), None)
    if entropy is not None and entropy > 0.95:
        return False, "high_entropy", support
    if "outcome_evidence" in row and row.get("outcome_evidence") is not True:
        return False, "outcome_support_missing", support
    if "outcome_variance" in row and row.get("outcome_variance") is False:
        return False, "no_counterfactual_outcome_variance", support
    if explicit is False:
        return False, "model_marked_unsupported", support
    return True, None, support


def _group_key(dimensions: Mapping[str, str]) -> tuple[str, ...]:
    return tuple(str(dimensions.get(name, _UNKNOWN)) for name in _DIMENSION_NAMES)


def _new_group(dimensions: Mapping[str, str], reason: str) -> dict[str, Any]:
    return {
        **{name: str(dimensions.get(name, _UNKNOWN)) for name in _DIMENSION_NAMES},
        "reason": reason,
        "kill_keys": set(),
        "candidate_row_count": 0,
        "unsupported_candidate_rows": 0,
    }


def _add_group(
    groups: dict[tuple[str, ...], dict[str, Any]],
    dimensions: Mapping[str, str],
    reason: str,
    *,
    kill_keys: Iterable[tuple[Any, ...]] = (),
    candidate_rows: int = 0,
    unsupported_rows: int = 0,
) -> None:
    key = _group_key(dimensions) + (reason,)
    group = groups.setdefault(key, _new_group(dimensions, reason))
    group["kill_keys"].update(kill_keys)
    group["candidate_row_count"] += candidate_rows
    group["unsupported_candidate_rows"] += unsupported_rows


def _report_source_name(payload: Mapping[str, Any]) -> str:
    return _text(payload.get("source") or payload.get("demo_file"), "unknown")


def _candidate_state_coverage(
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Summarize the extractor stage before model-support analysis."""

    summary = _mapping(payload.get("summary"))
    # JSONL contains one row per candidate rather than the report wrapper.
    row_payload = int(
        "rows" not in payload
        and payload.get("schema_version") == _CANDIDATE_STATE_SCHEMA_VERSION
    )
    kills_seen = _integer(summary.get("kills_seen"), row_payload) or 0
    rows_emitted = _integer(summary.get("rows_emitted"), row_payload) or 0
    skipped = max(0, kills_seen - rows_emitted)
    skip_reasons = summary.get("skip_reasons")
    if not isinstance(skip_reasons, Mapping):
        skip_reasons = {}
    rows = payload.get("rows")
    first_row = rows[0] if isinstance(rows, Sequence) and rows and isinstance(rows[0], Mapping) else {}
    source = _text(payload.get("source") or first_row.get("source"), "unknown")
    missing = []
    for reason, count in skip_reasons.items():
        missing.append(
            {
                **{name: _UNKNOWN for name in _DIMENSION_NAMES},
                "reason": str(reason),
                "kill_count": max(0, int(count)),
                "candidate_row_count": 0,
                "unsupported_candidate_rows": 0,
            }
        )
    return {
        "report_type": "candidate_coverage",
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "source_kind": "candidate_state_extraction",
        "stage": "pre_event_state_extraction",
        "support_applicable": False,
        "source": source,
        "min_support": None,
        "total_kills": kills_seen,
        "analyzed_kills": rows_emitted,
        "unanalysed_kills": skipped,
        "candidate_moment_count": rows_emitted,
        "candidate_row_count": rows_emitted,
        "supported_candidate_rows": 0,
        "unsupported_candidate_rows": 0,
        "supported_kills": 0,
        "partially_supported_kills": 0,
        "unsupported_kills": 0,
        "analyzed_kill_rate": rows_emitted / kills_seen if kills_seen else None,
        "supported_kill_rate": None,
        "missing_support_by_state": missing,
        "skip_reasons": {str(key): int(value) for key, value in skip_reasons.items()},
        "state_dimensions": list(_DIMENSION_NAMES),
    }


def analyze_candidate_coverage(
    payload: Mapping[str, Any],
    *,
    min_support: int | None = None,
) -> dict[str, Any]:
    """Analyze one canonical replay record or combined harness report.

    The result is JSON-compatible and contains no model or replay mutations.
    ``min_support`` defaults to the threshold recorded by a combined report,
    then to five for canonical records.
    """

    if not isinstance(payload, Mapping):
        raise TypeError("coverage input must be an object")
    if _is_candidate_state_payload(payload):
        return _candidate_state_coverage(payload)
    config = _mapping(payload.get("config"))
    probability_config = _mapping(config.get("probability_thresholds"))
    threshold = min_support
    if threshold is None:
        threshold = _integer(probability_config.get("min_support"), None)
    if threshold is None:
        threshold = _integer(config.get("min_support"), 5)
    if threshold < 0:
        raise ValueError("min_support cannot be negative")

    report = (
        _report_type(payload) == "combined_replay_analysis" or "full_match" in payload
    )
    kill_rows = _kill_rows(payload)
    declared = _declared_kill_count(payload)
    total_kills = max(len(kill_rows), declared or 0)
    total_keyed_rows: list[tuple[tuple[Any, ...], dict[str, Any]]] = [
        (_event_key(row, index), row) for index, row in enumerate(kill_rows)
    ]
    while len(total_keyed_rows) < total_kills:
        index = len(total_keyed_rows)
        total_keyed_rows.append((("declared", index), {}))
    analyzed_rows = _analyzed_kill_rows(payload) if report else []
    analyzed_keys = {_event_key(row, index) for index, row in enumerate(analyzed_rows)}
    declared_analyzed = _declared_analyzed_count(payload) if report else None
    if declared_analyzed is not None and len(analyzed_keys) < declared_analyzed:
        # Preserve the report's declared count when a producer omitted the
        # flattened rows; associate the missing count with stable kill rows so
        # that they are not incorrectly classified as ``not_analyzed``.
        analyzed_keys.update(
            key for key, _ in total_keyed_rows[: declared_analyzed - len(analyzed_keys)]
        )
    analyzed_kills = min(total_kills, len(analyzed_keys))
    groups: dict[tuple[str, ...], dict[str, Any]] = {}
    candidate_row_count = 0
    supported_candidate_rows = 0
    unsupported_candidate_rows = 0
    candidate_moment_count = 0
    kill_candidate_rows: defaultdict[tuple[Any, ...], int] = defaultdict(int)
    kill_supported_rows: defaultdict[tuple[Any, ...], int] = defaultdict(int)

    if report:
        for moment in payload.get("moments") or []:
            if not isinstance(moment, Mapping):
                continue
            candidate_rows = [
                row
                for row in moment.get("candidate_actions") or []
                if isinstance(row, Mapping)
            ]
            if not candidate_rows:
                continue
            candidate_moment_count += 1
            kill_events = [
                event
                for event in moment.get("events") or []
                if isinstance(event, Mapping) and _is_kill(event)
            ]
            kill_keys = {
                _event_key(event, index) for index, event in enumerate(kill_events)
            }
            event = kill_events[0] if kill_events else {}
            dimensions = _dimensions(payload, moment=moment, event=event)
            for row in candidate_rows:
                candidate_row_count += 1
                supported, reason, _support = _support_status(row, threshold)
                if supported:
                    supported_candidate_rows += 1
                else:
                    unsupported_candidate_rows += 1
                    _add_group(
                        groups,
                        dimensions,
                        reason or "unsupported",
                        kill_keys=kill_keys,
                        candidate_rows=1,
                        unsupported_rows=1,
                    )
                for key in kill_keys:
                    kill_candidate_rows[key] += 1
                    kill_supported_rows[key] += int(supported)

    # A canonical record has no candidate rows yet.  Report each kill as an
    # unanalyzed state so the dimensions show exactly where coverage is absent.
    for key, event in total_keyed_rows:
        dimensions = (
            _canonical_dimensions(payload, event)
            if not report
            else _dimensions(payload, event=event)
        )
        if key not in analyzed_keys:
            _add_group(groups, dimensions, "not_analyzed", kill_keys=(key,))
        elif key not in kill_candidate_rows:
            _add_group(groups, dimensions, "no_candidate_rows", kill_keys=(key,))

    supported_kills = sum(
        1
        for key, row_count in kill_candidate_rows.items()
        if row_count > 0 and kill_supported_rows[key] == row_count
    )
    partially_supported_kills = sum(
        1
        for key, row_count in kill_candidate_rows.items()
        if 0 < kill_supported_rows[key] < row_count
    )
    unsupported_kills = max(0, analyzed_kills - supported_kills - partially_supported_kills)
    unanalysed_kills = max(0, total_kills - analyzed_kills)
    missing_groups: list[dict[str, Any]] = []
    for group in groups.values():
        item = {key: value for key, value in group.items() if key != "kill_keys"}
        item["kill_count"] = len(group["kill_keys"])
        missing_groups.append(item)
    missing_groups.sort(
        key=lambda item: (
            -int(item["kill_count"]),
            -int(item["unsupported_candidate_rows"]),
            tuple(str(item[name]) for name in _DIMENSION_NAMES),
            str(item["reason"]),
        )
    )
    analyzed_rate = analyzed_kills / total_kills if total_kills else None
    supported_rate = supported_kills / analyzed_kills if analyzed_kills else None
    return {
        "report_type": "candidate_coverage",
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "source_kind": "combined_replay_analysis"
        if report
        else "canonical_replay_record",
        "source": _report_source_name(payload),
        "min_support": threshold,
        "total_kills": total_kills,
        "analyzed_kills": analyzed_kills,
        "unanalysed_kills": unanalysed_kills,
        "candidate_moment_count": candidate_moment_count,
        "candidate_row_count": candidate_row_count,
        "supported_candidate_rows": supported_candidate_rows,
        "unsupported_candidate_rows": unsupported_candidate_rows,
        "supported_kills": supported_kills,
        "partially_supported_kills": partially_supported_kills,
        "unsupported_kills": unsupported_kills,
        "analyzed_kill_rate": analyzed_rate,
        "supported_kill_rate": supported_rate,
        "support_applicable": True,
        "missing_support_by_state": missing_groups,
        "state_dimensions": list(_DIMENSION_NAMES),
    }


def aggregate_candidate_coverage(
    payloads: Iterable[Mapping[str, Any]],
    *,
    min_support: int | None = None,
) -> dict[str, Any]:
    """Aggregate diagnostics for multiple records/reports, such as JSONL."""

    reports = [
        analyze_candidate_coverage(payload, min_support=min_support)
        for payload in payloads
    ]
    if not reports:
        return {
            "report_type": "candidate_coverage",
            "schema_version": COVERAGE_SCHEMA_VERSION,
            "input_count": 0,
            "total_kills": 0,
            "analyzed_kills": 0,
            "unanalysed_kills": 0,
            "candidate_moment_count": 0,
            "candidate_row_count": 0,
            "supported_candidate_rows": 0,
            "unsupported_candidate_rows": 0,
            "supported_kills": 0,
            "partially_supported_kills": 0,
            "unsupported_kills": 0,
            "analyzed_kill_rate": None,
            "supported_kill_rate": None,
            "support_applicable": True,
            "missing_support_by_state": [],
            "state_dimensions": list(_DIMENSION_NAMES),
        }
    summed = {
        key: sum(int(report.get(key) or 0) for report in reports)
        for key in (
            "total_kills",
            "analyzed_kills",
            "unanalysed_kills",
            "candidate_moment_count",
            "candidate_row_count",
            "supported_candidate_rows",
            "unsupported_candidate_rows",
            "supported_kills",
            "partially_supported_kills",
            "unsupported_kills",
        )
    }
    grouped: dict[tuple[str, ...], dict[str, Any]] = {}
    for report in reports:
        for item in report.get("missing_support_by_state") or []:
            dimensions = {name: item.get(name, _UNKNOWN) for name in _DIMENSION_NAMES}
            reason = _text(item.get("reason"), "unknown")
            key = _group_key(dimensions) + (reason,)
            target = grouped.setdefault(
                key,
                {
                    **dimensions,
                    "reason": reason,
                    "kill_count": 0,
                    "candidate_row_count": 0,
                    "unsupported_candidate_rows": 0,
                },
            )
            target["kill_count"] += int(item.get("kill_count") or 0)
            target["candidate_row_count"] += int(item.get("candidate_row_count") or 0)
            target["unsupported_candidate_rows"] += int(
                item.get("unsupported_candidate_rows") or 0
            )
    missing = list(grouped.values())
    missing.sort(
        key=lambda item: (
            -int(item["kill_count"]),
            -int(item["unsupported_candidate_rows"]),
            tuple(str(item[name]) for name in _DIMENSION_NAMES),
            str(item["reason"]),
        )
    )
    total = summed["total_kills"]
    analyzed = summed["analyzed_kills"]
    support_applicable = all(bool(report.get("support_applicable", True)) for report in reports)
    return {
        "report_type": "candidate_coverage",
        "schema_version": COVERAGE_SCHEMA_VERSION,
        "input_count": len(reports),
        "min_support": min_support
        if min_support is not None
        else reports[0].get("min_support", 5),
        **summed,
        "analyzed_kill_rate": analyzed / total if total else None,
        "supported_kill_rate": summed["supported_kills"] / analyzed
        if analyzed and support_applicable
        else None,
        "support_applicable": support_applicable,
        "missing_support_by_state": missing,
        "state_dimensions": list(_DIMENSION_NAMES),
        "sources": [report.get("source", "unknown") for report in reports],
    }


def load_json_inputs(path: str | Path) -> list[dict[str, Any]]:
    """Load a JSON object/list or JSONL file without modifying it."""

    source = Path(path)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        return []
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        rows: list[dict[str, Any]] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSONL at line {line_number}: {exc}") from exc
            if not isinstance(value, Mapping):
                raise TypeError(f"JSONL line {line_number} must be an object")
            rows.append(dict(value))
        return rows
    if isinstance(payload, Mapping):
        return [dict(payload)]
    if isinstance(payload, list):
        if not all(isinstance(item, Mapping) for item in payload):
            raise TypeError("JSON list entries must be objects")
        return [dict(item) for item in payload]
    raise TypeError("coverage input must be a JSON object, list, or JSONL")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input",
        type=Path,
        nargs="?",
        help="canonical replay JSON/JSONL or combined analysis report",
    )
    parser.add_argument(
        "--input",
        dest="input_option",
        type=Path,
        default=None,
        help="same as the positional input path",
    )
    parser.add_argument(
        "--min-support",
        type=int,
        default=None,
        help="override the report's support threshold",
    )
    parser.add_argument(
        "--output", type=Path, default=None, help="optional JSON report destination"
    )
    args = parser.parse_args(argv)
    input_path = args.input_option or args.input
    if input_path is None:
        parser.error("an input path is required")
    result = aggregate_candidate_coverage(
        load_json_inputs(input_path), min_support=args.min_support
    )
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


__all__ = [
    "COVERAGE_SCHEMA_VERSION",
    "aggregate_candidate_coverage",
    "analyze_candidate_coverage",
    "load_json_inputs",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())

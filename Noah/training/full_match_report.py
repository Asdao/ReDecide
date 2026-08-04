"""Deterministic full-match replay timeline reports.

This module is deliberately a reporting layer around the existing replay-value
model.  It does not train, mutate, or persist model state.  A report contains
model probabilities at the extracted replay states, within-round probability
swings, and evidence annotations for kill/death/bomb events.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from cs2_sim.core.model import ReplayValueEnsemble
from Noah.training.full_features import record_to_event_rows, record_to_rows


class _Predictor(Protocol):
    def predict(self, snapshot: Mapping[str, Any]) -> Any: ...


REPORT_SCHEMA_VERSION = 1
_EVENT_ORDER = {"kill": 0, "death": 1, "bomb": 2, "other": 3}


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = -1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _text(value: Any) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _map_name(record: Mapping[str, Any]) -> str:
    header = record.get("header")
    header = header if isinstance(header, Mapping) else {}
    return str(header.get("map_name") or record.get("map_name") or "unknown").lower()


def _tick_rate(record: Mapping[str, Any]) -> float:
    header = record.get("header")
    header = header if isinstance(header, Mapping) else {}
    value = header.get("tick_rate") or record.get("tick_rate")
    rate = _number(value, 64.0)
    if rate <= 0:
        raise ValueError("tick_rate must be positive")
    return rate


def _event_round(event: Mapping[str, Any], rounds: Sequence[Mapping[str, Any]]) -> int:
    explicit = _integer(event.get("round_num"), -1)
    if explicit >= 0:
        return explicit
    tick = _integer(event.get("tick"), -1)
    if tick < 0:
        return -1
    for round_row in rounds:
        round_num = _integer(round_row.get("round_num"), -1)
        start = _integer(round_row.get("start") or round_row.get("start_tick"), -1)
        end = _integer(
            round_row.get("end")
            or round_row.get("official_end")
            or round_row.get("end_tick"),
            -1,
        )
        if round_num >= 0 and start >= 0 and end >= start and start <= tick <= end:
            return round_num
    return -1


def _category(event_type: str, source: str) -> str | None:
    text = f"{event_type} {source}".lower()
    if "death" in text or "kill" in text:
        return "death" if "death" in text and "kill" not in text else "kill"
    if "bomb" in text:
        return "bomb"
    return None


def _event_annotation(
    row: Mapping[str, Any],
    *,
    event_type: str,
    source: str,
    rounds: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    category = _category(event_type, source)
    if category is None:
        return None
    round_num = _event_round(row, rounds)
    tick = _integer(row.get("tick"), -1)
    if tick < 0:
        return None
    payload = row.get("payload")
    payload = payload if isinstance(payload, Mapping) else {}
    attacker_id = row.get("attacker_steamid") or row.get("attacker_id") or payload.get("attacker_steamid")
    victim_id = row.get("victim_steamid") or row.get("victim_id") or payload.get("victim_steamid")
    actor_id = row.get("steamid") or row.get("actor_id") or payload.get("steamid")
    site = (
        row.get("bombsite")
        or row.get("site")
        or row.get("which_bomb_zone")
        or row.get("bomb_site")
        or payload.get("bombsite")
        or payload.get("site")
    )
    return {
        "round_num": round_num,
        "tick": tick,
        "category": category,
        "event_type": str(event_type or category).lower(),
        "source": source,
        "attacker_id": _text(attacker_id),
        "victim_id": _text(victim_id),
        "actor_id": _text(actor_id),
        "attacker_name": _text(row.get("attacker_name") or payload.get("attacker_name")),
        "victim_name": _text(row.get("victim_name") or payload.get("victim_name")),
        "side": _text(row.get("attacker_side") or row.get("side") or payload.get("attacker_side")),
        "weapon": _text(row.get("weapon") or payload.get("weapon")),
        "bomb_site": _text(site),
    }


def _event_annotations(
    record: Mapping[str, Any],
    *,
    include_other_events: bool,
) -> list[dict[str, Any]]:
    rounds = [item for item in record.get("rounds") or [] if isinstance(item, Mapping)]
    candidates: list[dict[str, Any]] = []

    for key, event_type in (("kills", "kill"), ("damages", "damage"), ("bomb", "bomb")):
        for row in record.get(key) or []:
            if isinstance(row, Mapping):
                item = _event_annotation(row, event_type=event_type, source=key, rounds=rounds)
                if item is not None:
                    candidates.append(item)

    event_groups = record.get("events") or {}
    if isinstance(event_groups, Mapping):
        for name in sorted(event_groups, key=str):
            values = event_groups.get(name) or []
            if not isinstance(values, Sequence) or isinstance(values, (str, bytes)):
                continue
            for row in values:
                if not isinstance(row, Mapping):
                    continue
                category = _category(str(name), f"events:{name}")
                if category is None and not include_other_events:
                    continue
                if category is None:
                    # Keep the report compact and deterministic while allowing
                    # callers to opt into non-decision event evidence.
                    category = "other"
                item = _event_annotation(
                    row,
                    event_type=str(name),
                    source=f"events:{name}",
                    rounds=rounds,
                )
                if item is None:
                    tick = _integer(row.get("tick"), -1)
                    if tick < 0:
                        continue
                    item = {
                        "round_num": _event_round(row, rounds),
                        "tick": tick,
                        "category": category,
                        "event_type": str(name).lower(),
                        "source": f"events:{name}",
                        "attacker_id": None,
                        "victim_id": None,
                        "actor_id": _text(row.get("steamid") or row.get("actor_id")),
                        "attacker_name": None,
                        "victim_name": None,
                        "side": _text(row.get("side") or row.get("team_name")),
                        "weapon": _text(row.get("weapon")),
                        "bomb_site": _text(row.get("bombsite") or row.get("site")),
                    }
                else:
                    item["category"] = category
                candidates.append(item)

    # Dedicated bomb/kill streams and parser event streams can represent the
    # same fact. Deduplicate exact facts, retaining stable source ordering.
    unique: dict[tuple[Any, ...], dict[str, Any]] = {}
    for item in candidates:
        key = (
            item["round_num"],
            item["tick"],
            item["category"],
            item["attacker_id"],
            item["victim_id"],
            item["actor_id"],
            item["weapon"],
            item["bomb_site"],
        )
        if key not in unique:
            unique[key] = item
    events = list(unique.values())
    events.sort(
        key=lambda item: (
            item["round_num"],
            item["tick"],
            _EVENT_ORDER.get(item["category"], 99),
            item["source"],
            item["event_type"],
        )
    )
    for index, item in enumerate(events, start=1):
        item["event_id"] = f"event-{index:06d}"
    return events


def _prediction(model: Any, row: Mapping[str, Any]) -> tuple[float, dict[str, Any]]:
    snapshot = row.get("snapshot")
    snapshot = snapshot if isinstance(snapshot, Mapping) else {}
    features = row.get("features")
    prediction: Any
    if isinstance(features, Mapping) and hasattr(model, "predict_features"):
        names = getattr(model, "feature_names", tuple(features))
        vector = [float(features[name]) for name in names]
        prediction = model.predict_features(vector, snapshot=snapshot)
    else:
        prediction = model.predict(snapshot)
    probability = float(getattr(prediction, "probability", prediction))
    probability = min(1.0, max(0.0, probability))
    details = {
        "uncertainty": getattr(prediction, "uncertainty", None),
        "sample_count": getattr(prediction, "sample_count", None),
        "calibrated": getattr(prediction, "calibrated", None),
    }
    return probability, details


def _swing(previous: float | None, current: float) -> dict[str, Any] | None:
    if previous is None:
        return None
    delta = current - previous
    direction = "ct_gain" if delta > 0 else "t_gain" if delta < 0 else "flat"
    return {"delta": delta, "absolute": abs(delta), "direction": direction}


def build_full_match_report(
    record: Mapping[str, Any],
    model: Any | None = None,
    *,
    ensemble: Any | None = None,
    sample_every: int = 1,
    include_terminal: bool = True,
    include_other_events: bool = False,
    max_timeline_points: int | None = None,
    top_swing_count: int = 10,
) -> dict[str, Any]:
    """Build a JSON-compatible, deterministic full-match report.

    ``model`` may be :class:`ReplayValueEnsemble`, the public ``ReplayModel``
    facade, or a small test double exposing ``predict(snapshot)``.  Omitting it
    uses the existing Bayesian ensemble fallback and does not mutate artifacts.
    """

    if sample_every <= 0:
        raise ValueError("sample_every must be positive")
    if max_timeline_points is not None and max_timeline_points <= 0:
        raise ValueError("max_timeline_points must be positive")
    if top_swing_count < 0:
        raise ValueError("top_swing_count cannot be negative")
    if model is not None and ensemble is not None:
        raise ValueError("provide only one of model or ensemble")
    predictor = ensemble or model or ReplayValueEnsemble()
    parsed_rows = record_to_rows(
        dict(record),
        sample_every=sample_every,
        decision_window_seconds=None,
        include_terminal=include_terminal,
    )
    if not parsed_rows:
        parsed_rows = record_to_event_rows(
            dict(record),
            decision_window_seconds=None,
            include_terminal=include_terminal,
        )
    parsed_rows.sort(key=lambda row: (_integer(row.get("round_num")), _integer(row.get("tick"))))
    if max_timeline_points is not None:
        parsed_rows = parsed_rows[:max_timeline_points]

    events = _event_annotations(record, include_other_events=include_other_events)
    events_by_position: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        events_by_position[(event["round_num"], event["tick"])].append(event)

    timeline: list[dict[str, Any]] = []
    probabilities_by_round: dict[int, float | None] = {}
    for row in parsed_rows:
        round_num = _integer(row.get("round_num"))
        tick = _integer(row.get("tick"))
        probability, details = _prediction(predictor, row)
        swing = _swing(probabilities_by_round.get(round_num), probability)
        probabilities_by_round[round_num] = probability
        snapshot = row.get("snapshot")
        snapshot = snapshot if isinstance(snapshot, Mapping) else {}
        item = {
            "round_num": round_num,
            "tick": tick,
            "time_seconds": _number(snapshot.get("elapsed_seconds")),
            "probability_ct_win": probability,
            "uncertainty": details["uncertainty"],
            "sample_count": details["sample_count"],
            "calibrated": details["calibrated"],
            "probability_swing": swing,
            "events": list(events_by_position.get((round_num, tick), [])),
        }
        timeline.append(item)

    # Attach events that fall between sampled states to the nearest state in
    # the same round, never across a round boundary.
    if timeline:
        for event in events:
            if any(event is candidate for item in timeline for candidate in item["events"]):
                continue
            candidates = [item for item in timeline if item["round_num"] == event["round_num"]]
            if not candidates:
                continue
            nearest = min(candidates, key=lambda item: (abs(item["tick"] - event["tick"]), item["tick"]))
            nearest["events"].append(event)
            nearest["events"].sort(
                key=lambda item: (
                    item["tick"],
                    _EVENT_ORDER.get(item["category"], 99),
                    item["event_id"],
                )
            )

    swings = [
        {
            "round_num": item["round_num"],
            "tick": item["tick"],
            **item["probability_swing"],
        }
        for item in timeline
        if item["probability_swing"] is not None
    ]
    swings.sort(key=lambda item: (-float(item["absolute"]), item["round_num"], item["tick"]))
    event_counts = Counter(str(event["category"]) for event in events)
    round_rows = { _integer(row.get("round_num")): row for row in record.get("rounds") or [] if isinstance(row, Mapping) }
    round_reports: list[dict[str, Any]] = []
    for round_num in sorted(set(round_rows) | {item["round_num"] for item in timeline}):
        round_timeline = [item for item in timeline if item["round_num"] == round_num]
        source_round = round_rows.get(round_num, {})
        round_reports.append(
            {
                "round_num": round_num,
                "winner": source_round.get("winner"),
                "start_tick": source_round.get("start") or source_round.get("start_tick"),
                "end_tick": source_round.get("end") or source_round.get("official_end") or source_round.get("end_tick"),
                "timeline_points": len(round_timeline),
                "probability_start": round_timeline[0]["probability_ct_win"] if round_timeline else None,
                "probability_end": round_timeline[-1]["probability_ct_win"] if round_timeline else None,
                "largest_swing": max((item["probability_swing"] for item in round_timeline if item["probability_swing"]), key=lambda item: item["absolute"], default=None),
            }
        )
    return {
        "report_type": "full_match_timeline",
        "schema_version": REPORT_SCHEMA_VERSION,
        "source": str(record.get("source_path") or record.get("demo_file") or "unknown"),
        "demo_file": record.get("demo_file"),
        "map_name": _map_name(record),
        "tick_rate": _tick_rate(record),
        "timeline_points": len(timeline),
        "timeline": timeline,
        "probability_swings": swings[:top_swing_count],
        "events": events,
        "event_counts": dict(sorted(event_counts.items())),
        "rounds": round_reports,
        "summary": {
            "round_count": len(round_reports),
            "event_count": len(events),
            "initial_probability": timeline[0]["probability_ct_win"] if timeline else None,
            "final_probability": timeline[-1]["probability_ct_win"] if timeline else None,
            "largest_swing": swings[0] if swings else None,
        },
    }


# Friendly aliases for callers that used “analyze” terminology in earlier
# integrations.  Keeping both names avoids forcing a frontend/API migration.
analyze_full_match = build_full_match_report
full_match_report = build_full_match_report


__all__ = [
    "REPORT_SCHEMA_VERSION",
    "analyze_full_match",
    "build_full_match_report",
    "full_match_report",
]

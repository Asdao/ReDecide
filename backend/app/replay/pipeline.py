"""Transport-neutral replay preparation for the selector and progress UI.

The two public functions intentionally require only one input: a replay path
or an already-normalized replay mapping. FastAPI can later serialize the
returned selector payload and stream the progress iterator without moving any
replay or model logic into the HTTP layer.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from pathlib import Path
from typing import Any


PIPELINE_SCHEMA_VERSION = "replay_pipeline_v1"
SELECTOR_SCHEMA_VERSION = "player_selector_v1"
PROGRESS_SCHEMA_VERSION = "pipeline_progress_v1"
DEFAULT_MAX_DECISIONS = 100
DEFAULT_MAX_TIMELINE_POINTS = 120
MAX_EXTRACTED_WINDOWS = 1_000

_OUTCOME_FIELDS = frozenset(
    {
        "outcome",
        "round_won",
        "round_winner",
        "winner",
        "label_end_tick",
        "label_horizon",
        "label_horizon_ticks",
        "label_horizon_seconds",
        "kill_tick",
        "death_tick",
        "trade_tick",
        "round_value_delta",
        "survived_after_kill",
    }
)


def extract_players_for_selector(replay: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Return selector-ready players and event references for one replay.

    A player option owns only references to events in which that player is a
    participant. Global match data, especially the team win estimator, is not
    copied into or filtered by this selector contract.
    """

    record = _load_record(replay)
    windows = _engagement_windows(record)
    candidates = _first_contact_candidates(record, windows, max_decisions=DEFAULT_MAX_DECISIONS)
    return _selector_from_record(record, windows, candidates)


def stream_replay_pipeline(
    replay: str | Path | Mapping[str, Any],
    *,
    version: str | None = None,
    sample_every: int = 8,
    max_decisions: int = DEFAULT_MAX_DECISIONS,
    max_timeline_points: int = DEFAULT_MAX_TIMELINE_POINTS,
    decision_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield monotonic progress updates and finish with the complete result.

    Only ``replay`` is required. The optional keyword arguments are bounded
    tuning/selection controls used by the existing Pi bridge. A future SSE
    route can forward every yielded object verbatim.
    """

    _validate_limits(
        sample_every=sample_every,
        max_decisions=max_decisions,
        max_timeline_points=max_timeline_points,
    )
    yield _progress("received", 0, "Replay input accepted.")
    yield _progress("extracting_replay", 10, "Extracting and normalizing replay telemetry.")
    record = _load_record(replay)
    yield _progress("replay_extracted", 30, "Replay telemetry is ready.")

    windows = _engagement_windows(record)
    candidates = _first_contact_candidates(record, windows, max_decisions=max_decisions)
    selector = _selector_from_record(record, windows, candidates)
    yield _progress(
        "players_indexed",
        45,
        "Players are ready for the frontend selector.",
        player_count=len(selector["players"]),
    )
    yield _progress(
        "key_events_indexed",
        60,
        "First-contact coaching anchors and replay markers are indexed.",
        key_event_count=len(selector["key_events"]),
    )

    yield _progress("win_estimator_started", 70, "Calculating the global CT/T win-rate timeline.")
    win_estimator = _win_estimator(
        record,
        version=version,
        sample_every=sample_every,
        max_timeline_points=max_timeline_points,
    )
    yield _progress(
        "win_estimator_ready",
        85,
        "The global team win-rate timeline is ready.",
        model_available=win_estimator["model_available"],
    )

    selected_decision = _select_decision(decision_id, candidates, windows)
    yield _progress("model_payload_ready", 95, "Outcome-blind coaching facts are ready for Pi.")
    result = _pipeline_result(
        record,
        selector=selector,
        candidates=candidates,
        selected_decision=selected_decision,
        win_estimator=win_estimator,
    )
    yield _progress(
        "complete",
        100,
        "Replay preparation is complete.",
        done=True,
        result=result,
    )


def merge_pi_output(
    pipeline_result: Mapping[str, Any],
    pi_output: str | Mapping[str, Any],
) -> dict[str, Any]:
    """Attach one redacted Pi response to the authoritative UI result.

    Pi receives replay-local aliases (for example ``decision_001`` and
    ``player_02``). The backend owns the original candidate list and therefore
    resolves the decision alias locally before exposing the coaching text to
    the UI. The source replay and the original pipeline mapping are never
    modified.
    """

    result = dict(pipeline_result)
    coach = _decode_pi_output(pi_output)
    decision_id = str(coach.get("decision_id") or "").strip()
    if not decision_id:
        raise ValueError("Pi output must include decision_id")

    candidates = [
        candidate
        for candidate in result.get("decision_candidates", [])
        if isinstance(candidate, Mapping)
    ]
    decision_aliases = {
        f"decision_{index:03d}": str(candidate["decision_id"])
        for index, candidate in enumerate(candidates, start=1)
        if candidate.get("decision_id") not in (None, "")
    }
    resolved_decision_id = decision_aliases.get(decision_id, decision_id)
    candidate = next(
        (
            candidate
            for candidate in candidates
            if str(candidate.get("decision_id")) == resolved_decision_id
        ),
        None,
    )
    if candidate is None:
        raise ValueError("Pi output decision_id is not present in the pipeline result")

    player_id = str(candidate.get("player_id") or "")
    player = next(
        (
            item
            for item in result.get("players", [])
            if isinstance(item, Mapping) and str(item.get("player_id")) == player_id
        ),
        {},
    )
    player_name = candidate.get("display_name") or player.get("display_name") or player_id
    coaching = dict(coach)
    coaching.update(
        {
            "decision_id": resolved_decision_id,
            "player_id": player_id,
            "player_name": str(player_name),
            "source": "pi",
        }
    )
    result["coach_analysis"] = coaching
    result["selected_decision"] = dict(candidate)
    result["selected_decision"]["player_name"] = str(player_name)
    return result


def _decode_pi_output(value: str | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Pi output must be a JSON object or non-empty text")
    decoder = json.JSONDecoder()
    for index, character in enumerate(value):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(value[index:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, Mapping):
            return dict(parsed)
    raise ValueError("Pi output did not contain a JSON object")


def _load_record(replay: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(replay, Mapping):
        return dict(replay)
    from backend.replay_engine.harness import load_replay_record

    return load_replay_record(replay)


def _engagement_windows(record: dict[str, Any]) -> list[dict[str, Any]]:
    from backend.replay_engine.training.engagement_windows import extract_engagement_windows

    return extract_engagement_windows(
        record,
        horizon_seconds=5.0,
        decision_lead_seconds=1.0,
        action_window_seconds=1.0,
        max_windows=MAX_EXTRACTED_WINDOWS,
    )


def _selector_from_record(
    record: Mapping[str, Any],
    windows: list[Mapping[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    events = _event_markers(record)
    coaching_contacts = {
        (
            candidate["round_number"],
            candidate["contact_tick"],
            frozenset((candidate["player_id"], str(candidate["opponent_id"]))),
        )
        for candidate in candidates
        if candidate["event_category"] == "damage"
    }
    for event in events:
        contact = (event["round_number"], event["tick"], frozenset(event["participant_ids"]))
        if event["event_type"] == "damage" and contact in coaching_contacts:
            event.update(
                {
                    "is_key_event": True,
                    "key_event_type": "first_damage_contact",
                    "is_coaching_anchor": True,
                }
            )
        elif event["event_type"] == "kill":
            event.update(
                {
                    "is_key_event": True,
                    "key_event_type": "kill_marker",
                    "is_coaching_anchor": False,
                }
            )
        elif _is_bomb_marker(event["event_type"]):
            event.update(
                {
                    "is_key_event": True,
                    "key_event_type": "bomb_marker",
                    "is_coaching_anchor": False,
                }
            )

    players = _player_index(record, windows)
    event_ids: dict[str, list[str]] = {player["player_id"]: [] for player in players}
    key_event_ids: dict[str, list[str]] = {player["player_id"]: [] for player in players}
    decision_ids: dict[str, list[str]] = {player["player_id"]: [] for player in players}
    for event in events:
        for player_id in event["participant_ids"]:
            event_ids.setdefault(player_id, []).append(event["event_id"])
            if event["is_key_event"]:
                key_event_ids.setdefault(player_id, []).append(event["event_id"])
    for candidate in candidates:
        decision_ids.setdefault(candidate["player_id"], []).append(candidate["decision_id"])

    for player in players:
        player_id = player["player_id"]
        player.update(
            {
                "event_ids": event_ids.get(player_id, []),
                "key_event_ids": key_event_ids.get(player_id, []),
                "decision_ids": decision_ids.get(player_id, []),
            }
        )
    return {
        "schema_version": SELECTOR_SCHEMA_VERSION,
        "replay_id": _replay_id(record),
        "players": players,
        "events": events,
        "key_events": [event for event in events if event["is_key_event"]],
        "filter_contract": {
            "player_event_field": "participant_ids",
            "player_reference_fields": ["event_ids", "key_event_ids", "decision_ids"],
            "global_unfiltered_fields": ["win_estimator"],
        },
    }


def _event_markers(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    groups: list[tuple[str, Any]] = [
        ("damage", record.get("damages") or []),
        ("kill", record.get("kills") or []),
        ("bomb", record.get("bomb") or []),
    ]
    extra = record.get("events") if isinstance(record.get("events"), Mapping) else {}
    groups.extend((str(name).lower(), rows or []) for name, rows in extra.items())
    markers: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    ordinal = 0
    for event_type, rows in groups:
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            ordinal += 1
            normalized_type = _event_type(event_type, row)
            participant_ids = _participant_ids(row)
            round_number = _integer(row.get("round_num"), 0)
            tick = _integer(row.get("tick"), 0)
            signature = (
                normalized_type,
                round_number,
                tick,
                tuple(participant_ids),
                str(row.get("weapon") or ""),
            )
            if signature in seen:
                continue
            seen.add(signature)
            markers.append(
                {
                    "event_id": str(row.get("event_id") or f"evt:{ordinal}:r{round_number}:t{tick}"),
                    "round_number": round_number,
                    "tick": tick,
                    "event_type": normalized_type,
                    "participant_ids": participant_ids,
                    "is_key_event": False,
                    "key_event_type": None,
                    "is_coaching_anchor": False,
                }
            )
    return sorted(markers, key=lambda event: (event["round_number"], event["tick"], event["event_id"]))


def _participant_ids(event: Mapping[str, Any]) -> list[str]:
    values = []
    for prefix in ("attacker", "victim"):
        value = _first_present(
            event,
            f"{prefix}_steamid",
            f"{prefix}_steam_id",
            f"{prefix}_id",
            f"{prefix}_name",
        )
        if value not in (None, ""):
            values.append(str(value))
    actor = _first_present(event, "steamid", "player_steamid", "actor_steamid", "actor_id")
    if actor not in (None, ""):
        values.append(str(actor))
    return list(dict.fromkeys(values))


def _event_type(group_name: str, event: Mapping[str, Any]) -> str:
    text = str(event.get("event") or event.get("event_type") or group_name).strip().lower().replace("-", "_")
    if text in {"player_hurt", "hurt", "damages"}:
        return "damage"
    if text in {"player_death", "death", "kills"}:
        return "kill"
    return text


def _is_bomb_marker(event_type: str) -> bool:
    return any(word in event_type for word in ("bomb", "plant", "defus", "explode"))


def _player_index(record: Mapping[str, Any], windows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    players: dict[str, dict[str, Any]] = {}

    def ensure(player_id: Any) -> dict[str, Any] | None:
        if player_id in (None, ""):
            return None
        key = str(player_id)
        return players.setdefault(
            key,
            {"player_id": key, "display_name": None, "side_by_round": {}, "rounds": []},
        )

    for tick in record.get("ticks") or []:
        if not isinstance(tick, Mapping):
            continue
        item = ensure(_first_present(tick, "steamid", "steam_id", "player_id", "player_name", "name"))
        if item is None:
            continue
        item["display_name"] = item["display_name"] or tick.get("player_name") or tick.get("name")
        _add_player_round(item, tick.get("round_num"), tick.get("team_name") or tick.get("team") or tick.get("side"))
    for window in windows:
        item = ensure(window.get("player_id"))
        if item is not None:
            _add_player_round(item, window.get("round_num"), window.get("side"))
    for item in players.values():
        item["rounds"].sort()
    return sorted(players.values(), key=lambda item: (str(item.get("display_name") or ""), item["player_id"]))


def _add_player_round(player: dict[str, Any], round_value: Any, side_value: Any) -> None:
    round_number = _integer(round_value, -1)
    side = str(side_value or "").lower()
    if round_number < 0:
        return
    if round_number not in player["rounds"]:
        player["rounds"].append(round_number)
    if side in {"ct", "t"}:
        player["side_by_round"][str(round_number)] = side


def _first_contact_candidates(
    record: Mapping[str, Any],
    windows: list[Mapping[str, Any]],
    *,
    max_decisions: int,
) -> list[dict[str, Any]]:
    first_by_player_round: dict[tuple[int, str], Mapping[str, Any]] = {}
    for window in windows:
        round_number = _integer(window.get("round_num"), -1)
        player_id = str(window.get("player_id") or "")
        contact_tick = _integer(window.get("contact_tick"), -1)
        if round_number < 0 or not player_id or contact_tick < 0:
            continue
        key = (round_number, player_id)
        previous = first_by_player_round.get(key)
        if previous is None or contact_tick < _integer(previous.get("contact_tick"), contact_tick):
            first_by_player_round[key] = window

    from backend.replay_engine.training.action_labeler import build_action_event_index, classify_action

    event_index = build_action_event_index(record)
    round_end_ticks = {
        _integer(round_info.get("round_num"), -1): _integer(
            round_info.get("end", round_info.get("official_end")),
            -1,
        )
        for round_info in record.get("rounds") or []
        if isinstance(round_info, Mapping)
    }
    candidates = []
    ordered = sorted(
        first_by_player_round.values(),
        key=lambda item: (
            _integer(item.get("round_num"), -1),
            _integer(item.get("contact_tick"), -1),
            str(item.get("player_id") or ""),
        ),
    )
    for window in ordered[:max_decisions]:
        round_number = _integer(window.get("round_num"), 0)
        player_id = str(window.get("player_id"))
        contact_tick = _integer(window.get("contact_tick"), 0)
        tick_rate = _number(window.get("tick_rate"), 64.0)
        features = window.get("features") if isinstance(window.get("features"), Mapping) else {}
        feature_anchor = str(features.get("anchor_kind") or "")
        if "damage" not in feature_anchor:
            # Kills remain UI replay markers. They are never substituted for
            # the first-damage coaching selector when telemetry is missing.
            continue
        action_close_tick = contact_tick + max(1, round(2.5 * tick_rate))
        round_end_tick = round_end_ticks.get(round_number, -1)
        if round_end_tick >= contact_tick:
            action_close_tick = min(action_close_tick, round_end_tick)
        tick_series = [
            row
            for row in record.get("ticks") or []
            if isinstance(row, Mapping)
            and _integer(row.get("round_num"), -1) == round_number
            and str(_first_present(row, "steamid", "steam_id", "player_id", "player_name", "name") or "")
            == player_id
        ]
        action = classify_action(
            record,
            player_id=player_id,
            round_num=round_number,
            decision_tick=contact_tick,
            action_end_tick=action_close_tick,
            tick_series=tick_series,
            tick_rate=tick_rate,
            contact_actor=player_id if str(window.get("role")) == "attacker" else None,
            event_index=event_index,
        )
        candidates.append(
            {
                "decision_id": f"r{round_number}:p{player_id}:t{contact_tick}",
                "round_number": round_number,
                "player_id": player_id,
                "display_name": None,
                "side": str(window.get("side") or "unknown"),
                "role": str(window.get("role") or "unknown"),
                "event_category": "damage",
                "decision_open_tick": contact_tick,
                "contact_tick": contact_tick,
                "action_close_tick": action_close_tick,
                "opponent_id": window.get("opponent_id"),
                "observed_action": action.get("action") or "UNCLASSIFIED",
                "observed_action_confidence": action.get("confidence"),
                "evidence": list(action.get("evidence") or []),
            }
        )
    return candidates


def _select_decision(
    decision_id: str | None,
    candidates: list[dict[str, Any]],
    windows: list[Mapping[str, Any]],
) -> dict[str, Any] | None:
    if decision_id is None:
        return None
    selected = next((candidate for candidate in candidates if candidate["decision_id"] == decision_id), None)
    if selected is None:
        raise ValueError("decision_id is not present in this replay")
    for window in windows:
        if (
            str(window.get("player_id")) == selected["player_id"]
            and _integer(window.get("round_num"), -1) == selected["round_number"]
            and _integer(window.get("contact_tick"), -1) == selected["contact_tick"]
        ):
            safe_window = _safe_window(window)
            safe_window["anchor_tick"] = selected["decision_open_tick"]
            safe_window["action_close_tick"] = selected["action_close_tick"]
            return {**selected, "window": safe_window}
    raise ValueError("decision_id has no matching decision window")


def _safe_window(window: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "source",
        "match_id",
        "map_name",
        "round_num",
        "player_id",
        "side",
        "opponent_id",
        "role",
        "anchor_tick",
        "contact_tick",
        "decision_lead_seconds",
        "tick_rate",
        "features",
        "prediction",
    }
    return {
        key: value
        for key, value in window.items()
        if key in allowed and key not in _OUTCOME_FIELDS and not key.startswith("label_")
    }


def _win_estimator(
    record: dict[str, Any],
    *,
    version: str | None,
    sample_every: int,
    max_timeline_points: int,
) -> dict[str, Any]:
    try:
        from cs2_sim.api import ModelConfig, ReplayModel
        from backend.replay_engine.training.full_features import record_to_rows

        release_dir = (
            Path(__file__).resolve().parents[3]
            / "backend"
            / "replay_engine"
            / "model"
            / "artifacts"
            / "releases"
        )
        model = ReplayModel.load(ModelConfig(releases_dir=release_dir, version=version, allow_fallback=True))
        rows = record_to_rows(record, sample_every=sample_every, include_terminal=False)
        if len(rows) > max_timeline_points:
            stride = max(1, (len(rows) + max_timeline_points - 1) // max_timeline_points)
            rows = rows[::stride][:max_timeline_points]
        timeline = []
        for row in rows:
            prediction = model.predict(row["snapshot"])
            ct_probability = float(prediction.probability)
            timeline.append(
                {
                    "round_number": _integer(row.get("round_num"), 0),
                    "tick": _integer(row.get("tick"), 0),
                    "ct_probability": ct_probability,
                    "t_probability": 1.0 - ct_probability,
                    "uncertainty": float(prediction.uncertainty),
                }
            )
        return {
            "scope": "global_team_probability",
            "filtered_by_player": False,
            "model_available": True,
            "model_type": "replay_value_ensemble_or_fallback",
            "timeline": timeline,
        }
    except Exception:
        return {
            "scope": "global_team_probability",
            "filtered_by_player": False,
            "model_available": False,
            "model_type": "unavailable",
            "timeline": [],
            "warning": "The win estimator was unavailable; player and key-event indexing remains usable.",
        }


def _pipeline_result(
    record: Mapping[str, Any],
    *,
    selector: dict[str, Any],
    candidates: list[dict[str, Any]],
    selected_decision: dict[str, Any] | None,
    win_estimator: dict[str, Any],
) -> dict[str, Any]:
    display_names = {player["player_id"]: player.get("display_name") for player in selector["players"]}
    for candidate in candidates:
        candidate["display_name"] = display_names.get(candidate["player_id"])
    header = record.get("header") if isinstance(record.get("header"), Mapping) else {}
    source = str(record.get("demo_file") or "replay")
    has_damage = any(candidate["event_category"] == "damage" for candidate in candidates)
    return {
        "report_type": "replay_pipeline_analysis",
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "source": Path(source).name,
        "replay_id": selector["replay_id"],
        "map_name": str(header.get("map_name") or record.get("map_name") or "unknown"),
        "players": selector["players"],
        "events": selector["events"],
        "key_events": selector["key_events"],
        "filter_contract": selector["filter_contract"],
        "decision_candidates": candidates,
        "selected_decision": selected_decision,
        "win_estimator": win_estimator,
        "summary": {
            "player_count": len(selector["players"]),
            "event_count": len(selector["events"]),
            "key_event_count": len(selector["key_events"]),
            "decision_candidate_count": len(candidates),
            "anchor": "first_damage_contact" if has_damage else "no_damage_stream",
            "anchor_fallback": False,
            "analysis_available": has_damage,
            "outcome_blind": True,
        },
    }


def _progress(stage: str, progress: int, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "stage": stage,
        "progress": progress,
        "message": message,
        "done": False,
        **extra,
    }


def _validate_limits(*, sample_every: int, max_decisions: int, max_timeline_points: int) -> None:
    for name, value, maximum in (
        ("sample_every", sample_every, 256),
        ("max_decisions", max_decisions, 500),
        ("max_timeline_points", max_timeline_points, 500),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
            raise ValueError(f"{name} must be an integer between 1 and {maximum}")


def _replay_id(record: Mapping[str, Any]) -> str:
    match = record.get("match") if isinstance(record.get("match"), Mapping) else {}
    return str(
        record.get("replay_id")
        or record.get("match_id")
        or match.get("match_id")
        or Path(str(record.get("demo_file") or "replay")).stem
    )


def _first_present(value: Mapping[str, Any], *keys: str) -> Any:
    return next((value.get(key) for key in keys if value.get(key) is not None), None)


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _number(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


__all__ = ["extract_players_for_selector", "merge_pi_output", "stream_replay_pipeline"]

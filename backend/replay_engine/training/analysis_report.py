"""Pure report and key-moment projection helpers for the replay harness.

This module deliberately contains no model, simulator, or replay parsing
dependencies.  It turns normalized replay rows and an already-built analysis
timeline into the report-facing moment and kill-row structures consumed by the
CLI and API.  Keeping these operations here gives the orchestration layer a
small, explicit seam without changing the existing report schema.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

_OUTCOME_FIELDS = frozenset(
    {
        "winner",
        "round_winner",
        "label_round_winner",
        "round_won",
        "label_round_win",
        "label_kill",
        "label_death",
        "label_trade",
        "label_survival",
        "label_damage",
        "kill_tick",
        "death_tick",
        "trade_tick",
        "future_damage_dealt",
        "future_damage_taken",
        "survived_after_kill",
        "outcome",
        "parse_warning",
        "contact_tick",
        "label_end_tick",
        "label_cutoff_tick",
        "label_horizon_ticks",
        "label_horizon_seconds",
        "observed_action_event_ticks",
    }
)


def _redact_outcome_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _redact_outcome_fields(item)
            for key, item in value.items()
            if str(key) not in _OUTCOME_FIELDS
        }
    if isinstance(value, list):
        return [_redact_outcome_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_outcome_fields(item) for item in value)
    return value


def outcome_blind_report(report: Mapping[str, Any]) -> dict[str, Any]:
    """Project an evaluation report into a safe, outcome-blind payload.

    The offline report intentionally retains ``full_match`` and future labels
    for evaluation.  API/UI callers must use this projection before exposing
    a report outside the model boundary.  The projection is conservative and
    removes the complete terminal timeline plus known future-label fields.
    """

    if not isinstance(report, Mapping):
        raise TypeError("analysis report must be a mapping")
    projected = _redact_outcome_fields(dict(report))
    projected.pop("full_match", None)
    projected.pop("kill_analysis", None)
    summary = projected.get("summary")
    if isinstance(summary, Mapping):
        summary = dict(summary)
        for key in ("kill_count", "kill_analysis_count", "moment_count"):
            summary.pop(key, None)
        projected["summary"] = summary

    moments = projected.get("moments")
    if isinstance(moments, list):
        safe_moments: list[dict[str, Any]] = []
        for moment in moments:
            if not isinstance(moment, Mapping):
                continue
            safe_moment = dict(moment)
            cutoff = _int(safe_moment.get("decision_tick"), -1)
            if cutoff < 0:
                safe_moment.pop("events", None)
                safe_moment.pop("tick", None)
            else:
                moment_tick = _int(safe_moment.get("tick"), -1)
                if moment_tick > cutoff:
                    safe_moment.pop("tick", None)
                events = safe_moment.get("events")
                if isinstance(events, list):
                    safe_events = [
                        event
                        for event in events
                        if isinstance(event, Mapping)
                        and 0 <= _int(event.get("tick"), -1) <= cutoff
                    ]
                    if safe_events:
                        safe_moment["events"] = safe_events
                    else:
                        safe_moment.pop("events", None)
            safe_moments.append(safe_moment)
        projected["moments"] = safe_moments
    projected["outcome_blind"] = True
    return dict(projected)


def _number(value: Any, default: float = 0.0) -> float:
    """Coerce a replay value to ``float`` while tolerating missing fields."""

    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = -1) -> int:
    """Coerce a replay value to ``int`` while tolerating missing fields."""

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _snapshot_for_event(
    rows: list[dict[str, Any]], *, round_num: int, tick: int
) -> dict[str, Any] | None:
    """Return the nearest pre-event feature row for a round and tick."""

    candidates = [row for row in rows if _int(row.get("round_num")) == round_num]
    if not candidates:
        return None
    before = [row for row in candidates if _int(row.get("tick")) <= tick]
    return min(before or candidates, key=lambda row: abs(_int(row.get("tick")) - tick))


def _observed_action(
    rows: list[dict[str, Any]],
    *,
    actor: str | None,
    round_num: int,
    tick: int,
) -> dict[str, Any] | None:
    """Find the inferred action nearest to a moment's decision tick."""

    if actor is None:
        return None
    candidates = [
        row
        for row in rows
        if str(row.get("player_id")) == actor
        and _int(row.get("round_num")) == round_num
        and abs(_int(row.get("tick")) - tick) <= 128
    ]
    if not candidates:
        return None
    row = min(candidates, key=lambda item: abs(_int(item.get("tick")) - tick))
    action = str(row.get("action") or "")
    if action == "move":
        next_zone = str(row.get("next_zone") or "unknown")
        action = f"move_to_adjacent_zone:{next_zone}"
    return {
        "action": action,
        "tick": _int(row.get("tick")),
        "source": "inferred_replay_action",
    }


def _event_actor(event: Mapping[str, Any]) -> str | None:
    """Return the first actor-like identifier present on an event."""

    for key in ("actor_id", "attacker_id", "victim_id"):
        if event.get(key) not in (None, ""):
            return str(event[key])
    return None


def _coached_player(event: Mapping[str, Any]) -> str | None:
    """Coach the player who died at a kill moment; fall back for other events."""

    if str(event.get("category") or "") == "kill" and event.get("victim_id") not in (
        None,
        "",
    ):
        return str(event["victim_id"])
    return _event_actor(event)


def _engagement_window_for_kill(
    windows: Iterable[Mapping[str, Any]],
    *,
    round_num: int,
    tick: int,
    player_id: str | None,
) -> dict[str, Any] | None:
    """Select the engagement window for a player and kill tick."""

    if player_id is None:
        return None
    candidates = [
        dict(row)
        for row in windows
        if _int(row.get("round_num")) == round_num
        and str(row.get("player_id")) == player_id
        and _int(row.get("death_tick")) == tick
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: abs(tick - _int(row.get("contact_tick"), tick)))


def _movement_action(action: str) -> str:
    """Collapse movement variants to the legacy candidate comparison name."""

    return "move" if action.startswith("move") else "hold" if action == "hold" else action


def _display_action_name(observed: Mapping[str, Any]) -> str:
    """Return the stable human-readable action name used by reports."""

    action = str(observed.get("action") or "unknown")
    parameters = observed.get("parameters")
    parameters = parameters if isinstance(parameters, Mapping) else {}
    target_zone = parameters.get("target_zone")
    if target_zone not in (None, "") and action in {"move_to_adjacent_zone", "peek"}:
        return f"{action}:{target_zone}"
    utility_type = parameters.get("utility_type")
    if utility_type not in (None, "") and action == "use_utility":
        return f"{action}:{utility_type}"
    return action


def _find_moments(
    report: Mapping[str, Any], *, threshold: float, max_moments: int | None
) -> list[dict[str, Any]]:
    """Select and group important timeline events into report moments.

    Simultaneous kills are intentionally kept in separate moments so each
    actor-specific recommendation remains isolated.  Non-kill events at one
    tick remain grouped with their probability-swing context.
    """

    moments: dict[tuple[Any, ...], dict[str, Any]] = {}
    timeline = report.get("timeline") or []
    for item in timeline:
        if not isinstance(item, Mapping):
            continue
        round_num = _int(item.get("round_num"))
        tick = _int(item.get("tick"))
        swing = item.get("probability_swing")
        swing_value = (
            abs(_number((swing or {}).get("absolute")))
            if isinstance(swing, Mapping)
            else 0.0
        )
        events = [event for event in item.get("events") or [] if isinstance(event, Mapping)]
        important_events = [
            event for event in events if str(event.get("category")) in {"kill", "death", "bomb"}
        ]
        if swing_value < threshold and not important_events:
            continue
        # A moment may contain multiple simultaneous kills. Keep each kill in
        # its own moment so actor-specific recommendations cannot leak from
        # the first event to the other flattened kill rows. Non-kill events
        # at one tick remain grouped with the probability-swing context.
        kill_events = [
            event for event in important_events if str(event.get("category")) == "kill"
        ]
        # Death rows commonly mirror the same kill in parser output. Prefer
        # the kill event as the actor-specific coaching moment so one physical
        # event does not create a duplicate context-only moment.
        event_groups: list[Mapping[str, Any] | None] = (
            kill_events if kill_events else list(important_events) if important_events else [None]
        )
        for important_event in event_groups:
            if important_event is not None and str(important_event.get("category")) == "kill":
                event_key = important_event.get("event_id") or (
                    important_event.get("attacker_id"),
                    important_event.get("victim_id"),
                    important_event.get("weapon"),
                )
                moment_key: tuple[Any, ...] = (round_num, tick, "kill", event_key)
            else:
                moment_key = (round_num, tick, "context")
            entry = moments.setdefault(
                moment_key,
                {
                    "round_num": round_num,
                    "tick": tick,
                    "probability_ct_win": _number(item.get("probability_ct_win")),
                    "probability_swing": dict(swing) if isinstance(swing, Mapping) else None,
                    "importance": swing_value,
                    "events": [],
                },
            )
            entry["importance"] = max(float(entry["importance"]), swing_value)
            if important_event is not None:
                entry["events"].append(important_event)
    result = list(moments.values())
    for item in result:
        unique: dict[tuple[Any, ...], Mapping[str, Any]] = {}
        for event in item["events"]:
            key = (
                event.get("event_id"),
                event.get("round_num"),
                event.get("tick"),
                event.get("category"),
                event.get("attacker_id"),
                event.get("victim_id"),
            )
            unique[key] = event
        item["events"] = list(unique.values())
    result.sort(key=lambda item: (-float(item["importance"]), item["round_num"], item["tick"]))
    return result if max_moments is None else result[:max_moments]


def _kill_analysis_rows(moments: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Flatten one structured row per kill for API and CLI consumers."""

    rows: list[dict[str, Any]] = []
    for moment in moments:
        best = moment.get("best_estimated_alternative")
        best = best if isinstance(best, Mapping) else {}
        least_risk = moment.get("least_death_risk_action")
        least_risk = least_risk if isinstance(least_risk, Mapping) else {}
        snapshot = moment.get("snapshot")
        snapshot = snapshot if isinstance(snapshot, Mapping) else {}
        observed_action = moment.get("observed_action_name")
        for event in moment.get("events") or []:
            if not isinstance(event, Mapping) or str(event.get("category")) != "kill":
                continue
            rows.append(
                {
                    "round_num": _int(event.get("round_num"), _int(moment.get("round_num"))),
                    "tick": _int(event.get("tick"), _int(moment.get("tick"))),
                    "decision_tick": _int(moment.get("decision_tick"), _int(moment.get("tick"))),
                    "decision_lead_seconds": _number(moment.get("decision_lead_seconds"), 0.0),
                    "coached_player_id": moment.get("actor_id"),
                    "coached_player_role": moment.get("coached_player_role"),
                    "time_seconds": _number(snapshot.get("elapsed_seconds"), 0.0),
                    "event_id": event.get("event_id"),
                    "attacker_id": event.get("attacker_id"),
                    "victim_id": event.get("victim_id"),
                    "weapon": event.get("weapon"),
                    "observed_action": observed_action,
                    "recommended_action": best.get("action"),
                    "recommendation_supported": bool(best.get("supported", False)),
                    "recommendation_sample_count": int(best.get("sample_count") or 0),
                    "recommendation_support_level": best.get("support_level"),
                    "recommendation_support_reason": best.get("support_reason"),
                    "recommendation_raw_support": best.get("raw_support"),
                    "recommendation_outcome_support": best.get("outcome_support"),
                    "recommendation_outcome_variance": best.get("outcome_variance"),
                    "recommendation_rollout_quality": best.get("rollout_quality"),
                    "least_death_risk_action": least_risk.get("action"),
                    "least_death_probability": least_risk.get("death_probability"),
                    "least_death_round_loss_probability_proxy": least_risk.get(
                        "round_loss_probability_proxy"
                    ),
                    "least_death_is_proxy": bool(least_risk.get("is_proxy", True)),
                    "least_death_risk_upper_bound": least_risk.get("risk_upper_bound"),
                    "least_death_risk_interval_level": least_risk.get("risk_interval_level"),
                    "least_death_risk_interval_method": least_risk.get("risk_interval_method"),
                    "least_death_risk_support": least_risk.get("support"),
                    "least_death_risk_supported": bool(least_risk.get("supported", False)),
                    "least_death_risk_outcome_variance": least_risk.get("outcome_variance"),
                    "least_death_risk_outcome_evidence": least_risk.get("outcome_evidence"),
                    "least_death_risk_fallback_usable": bool(least_risk.get("fallback_usable", False)),
                    "least_death_risk_status": least_risk.get("fallback_status"),
                    "least_death_risk_source": least_risk.get("risk_source"),
                    "round_win_probability": best.get("candidate_success_probability"),
                    "engagement_round_win_probability": best.get("round_win_probability"),
                    "survival_probability": best.get("survival_probability"),
                    "kill_probability": best.get("kill_probability"),
                    "trade_probability": best.get("trade_probability"),
                    "damage_probability": best.get("damage_probability"),
                    "coaching_utility": best.get("coaching_utility"),
                    "round_loss_probability_proxy": best.get("death_probability"),
                    "probability_of_improvement": moment.get("probability_of_improvement"),
                    "expected_regret": moment.get("expected_regret"),
                    "probability_decision_class": moment.get("probability_decision_class"),
                    "probability_abstention": moment.get("probability_abstention"),
                    "estimate_type": best.get("estimate_type"),
                }
            )
    rows.sort(
        key=lambda row: (
            _int(row.get("round_num")),
            _int(row.get("tick")),
            str(row.get("event_id") or ""),
        )
    )
    for index, row in enumerate(rows, start=1):
        row["kill_number"] = index
    return rows


__all__ = [
    "_coached_player",
    "_display_action_name",
    "_engagement_window_for_kill",
    "_event_actor",
    "_find_moments",
    "_kill_analysis_rows",
    "_movement_action",
    "_observed_action",
    "_snapshot_for_event",
    "outcome_blind_report",
]

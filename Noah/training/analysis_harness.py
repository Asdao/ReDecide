"""Combined key-moment and estimated-alternative replay analysis.

The harness has two intentionally separate stages:

1. observed replay evidence (round-value swings and deterministic events);
2. legal candidate scoring from a simulator-trained action-value model.

Candidate results are estimates, not proof of a counterfactual.  If the state
cannot be reconstructed or candidate support is too low, the harness abstains.
Supported comparisons use seeded Beta-posterior draws to estimate the
probability of meaningful improvement and expected regret; weak comparisons
remain neutral or insufficient rather than being forced into good/bad labels.
"""

from __future__ import annotations

import argparse
import json
import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol

from cs2_sim.actions import Action
from cs2_sim.core.model import FullLightGBMModel, SmallStatisticalModel
from cs2_sim.rules import legal_actions
from cs2_sim.state import BombState, GameState, PlayerState, Team

from Noah.training.full_features import record_to_rows
from Noah.training.infer_actions import infer_actions
from Noah.training.recommendations import (
    ProbabilityLabelThresholds,
    annotate_probability_labels,
    rank_candidate_actions,
)

HARNESS_SCHEMA_VERSION = "replay_analysis_v1"


class DecisionClass(StrEnum):
    GOOD = "good"
    BAD = "bad"
    NEUTRAL = "neutral"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    NO_OBSERVED_ACTION = "no_observed_action"


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    moment_threshold: float = 0.08
    max_moments: int | None = 25
    min_support: int = 5
    recommendation_margin: float = 0.05
    sample_every: int = 8
    probability_of_improvement_threshold: float = 0.8
    expected_regret_threshold: float | None = None
    credible_level: float = 0.9
    max_interval_width: float = 0.8
    posterior_samples: int = 5000
    posterior_seed: int = 7

    def __post_init__(self) -> None:
        if not 0 < self.moment_threshold <= 1:
            raise ValueError("moment_threshold must be between 0 and 1")
        if self.max_moments is not None and self.max_moments <= 0:
            raise ValueError("max_moments must be positive when provided")
        if self.min_support < 0:
            raise ValueError("min_support cannot be negative")
        if self.recommendation_margin < 0 or self.recommendation_margin > 1:
            raise ValueError("recommendation_margin must be between 0 and 1")
        if self.sample_every <= 0:
            raise ValueError("sample_every must be positive")
        if not 0.5 < self.probability_of_improvement_threshold < 1.0:
            raise ValueError("probability_of_improvement_threshold must be between 0.5 and 1")
        if self.expected_regret_threshold is not None and not 0 <= self.expected_regret_threshold <= 1:
            raise ValueError("expected_regret_threshold must be between 0 and 1")
        if not 0 < self.credible_level < 1:
            raise ValueError("credible_level must be between 0 and 1")
        if not 0 < self.max_interval_width <= 1:
            raise ValueError("max_interval_width must be between 0 and 1")
        if self.posterior_samples <= 0:
            raise ValueError("posterior_samples must be positive")


class CandidateModel(Protocol):
    def score_actions(
        self,
        state: GameState,
        player_id: str,
        legal: Iterable[Action],
    ) -> Mapping[Action, float]: ...


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _side(value: Any) -> Team | None:
    text = str(value or "").strip().lower()
    if text in {"ct", "counterterrorist", "counter-terrorist"}:
        return Team.CT
    if text in {"t", "terrorist"}:
        return Team.T
    return None


def _identity(row: Mapping[str, Any], ordinal: int) -> str:
    for key in ("steamid", "steam_id", "player_steamid", "name", "player_name"):
        if row.get(key) not in (None, ""):
            return str(row[key])
    return f"anonymous:{ordinal}"


def _zone(row: Mapping[str, Any]) -> str:
    return str(row.get("last_place_name") or row.get("place") or row.get("zone") or "unknown")


def _nearest_tick_rows(
    record: Mapping[str, Any],
    *,
    round_num: int,
    tick: int,
    strict_before: bool = False,
    tick_index: Mapping[int, Mapping[str, tuple[list[int], list[dict[str, Any]]]]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Reconstruct latest player rows at or before a replay event."""

    if tick_index is not None:
        output: dict[str, dict[str, Any]] = {}
        for player_id, (ticks, rows) in tick_index.get(round_num, {}).items():
            position = bisect_left(ticks, tick) if strict_before else bisect_right(ticks, tick)
            if position:
                output[player_id] = dict(rows[position - 1])
        return output
    latest: dict[str, tuple[int, dict[str, Any]]] = {}
    for ordinal, row in enumerate(record.get("ticks") or []):
        if not isinstance(row, Mapping) or _int(row.get("round_num")) != round_num:
            continue
        row_tick = _int(row.get("tick"))
        if row_tick < 0 or row_tick > tick or (strict_before and row_tick >= tick):
            continue
        player_id = _identity(row, ordinal)
        previous = latest.get(player_id)
        if previous is None or row_tick >= previous[0]:
            latest[player_id] = (row_tick, dict(row))
    return {player_id: row for player_id, (_, row) in latest.items()}


def _build_tick_index(
    record: Mapping[str, Any],
) -> dict[int, dict[str, tuple[list[int], list[dict[str, Any]]]]]:
    """Index one replay's player snapshots for repeated pre-event lookups."""

    grouped: dict[int, dict[str, list[tuple[int, dict[str, Any]]]]] = defaultdict(dict)
    for ordinal, raw in enumerate(record.get("ticks") or ()):
        if not isinstance(raw, Mapping):
            continue
        round_num = _int(raw.get("round_num"))
        tick = _int(raw.get("tick"))
        if round_num < 0 or tick < 0:
            continue
        player_id = _identity(raw, ordinal)
        grouped.setdefault(round_num, {}).setdefault(player_id, []).append((tick, dict(raw)))
    indexed: dict[int, dict[str, tuple[list[int], list[dict[str, Any]]]]] = {}
    for round_num, players in grouped.items():
        indexed[round_num] = {}
        for player_id, values in players.items():
            values.sort(key=lambda item: item[0])
            # Keep the last parser row when duplicate identities share a tick.
            deduplicated: dict[int, dict[str, Any]] = {}
            for tick, row in values:
                deduplicated[tick] = row
            ticks = sorted(deduplicated)
            indexed[round_num][player_id] = (ticks, [deduplicated[tick] for tick in ticks])
    return indexed


def _round_start_tick(record: Mapping[str, Any], round_num: int) -> int | None:
    """Return the normalized round start tick when the parser supplied it."""

    for row in record.get("rounds") or ():
        if not isinstance(row, Mapping) or _int(row.get("round_num")) != round_num:
            continue
        value = _int(row.get("start"), -1)
        return value if value >= 0 else None
    return None


def _tick_rate(record: Mapping[str, Any]) -> float:
    header = record.get("header")
    header = header if isinstance(header, Mapping) else {}
    value = _number(header.get("tick_rate") or record.get("tick_rate"), 64.0)
    return value if value > 0 else 64.0


def _bomb_state(record: Mapping[str, Any], *, round_num: int, tick: int) -> tuple[BombState, str, float | None]:
    state = BombState.NONE
    site = "A_SITE"
    event_tick = -1
    for event in record.get("bomb") or []:
        if not isinstance(event, Mapping):
            continue
        if _int(event.get("round_num")) != round_num or _int(event.get("tick")) > tick:
            continue
        current_tick = _int(event.get("tick"))
        if current_tick < event_tick:
            continue
        event_tick = current_tick
        name = str(event.get("event") or event.get("type") or "").lower()
        if "plant" in name:
            state = BombState.PLANTED
        elif "defus" in name:
            state = BombState.DEFUSED
        elif "drop" in name:
            state = BombState.DROPPED
        elif "pick" in name or "carry" in name:
            state = BombState.CARRIED
        elif "deton" in name or "explode" in name:
            state = BombState.DETONATED
        site_value = str(event.get("bombsite") or event.get("site") or "").upper()
        if site_value in {"A", "B"}:
            site = f"{site_value}_SITE"
        elif site_value.endswith("A"):
            site = "A_SITE"
        elif site_value.endswith("B"):
            site = "B_SITE"
    return state, site, 40.0 if state is BombState.PLANTED else None


def reconstruct_game_state(
    record: Mapping[str, Any],
    *,
    round_num: int,
    tick: int,
    before_event: bool = False,
    tick_index: Mapping[int, Mapping[str, tuple[list[int], list[dict[str, Any]]]]] | None = None,
) -> GameState | None:
    """Build a simulator state, optionally excluding same-tick event outcomes."""

    rows = _nearest_tick_rows(
        record,
        round_num=round_num,
        tick=tick,
        strict_before=before_event,
        tick_index=tick_index,
    )
    if before_event and not rows:
        # Without a strictly earlier snapshot, using an event-tick row can
        # leak the kill/death outcome into the candidate state.  The caller
        # must abstain and report missing pre-event evidence instead.
        return None
    players: dict[str, PlayerState] = {}
    for player_id, row in rows.items():
        team = _side(row.get("team_name") or row.get("team") or row.get("side"))
        if team is None:
            continue
        health = max(0, min(100, int(_number(row.get("health"), 100.0))))
        utility = row.get("utility_count", row.get("utility", row.get("grenades", 0)))
        has_bomb = bool(row.get("has_bomb") or row.get("bomb_carrier"))
        players[player_id] = PlayerState(
            player_id=player_id,
            team=team,
            zone=_zone(row),
            health=health,
            alive=bool(row.get("alive", health > 0)),
            has_bomb=has_bomb,
            utility_count=max(0, int(_number(utility))),
        )
    if not players:
        return None
    bomb_state, bomb_site, bomb_time = _bomb_state(record, round_num=round_num, tick=tick)
    start_tick = _round_start_tick(record, round_num)
    tick_rate = _tick_rate(record)
    elapsed_seconds = (
        max(0.0, (tick - start_tick) / tick_rate)
        if start_tick is not None
        else max(0.0, tick / tick_rate)
    )
    return GameState(
        players,
        bomb_state=bomb_state,
        bomb_site=bomb_site,
        bomb_time_remaining=bomb_time,
        time_seconds=elapsed_seconds,
    )


def _action_name(action: Action) -> str:
    return f"{action.action_type.value}:{action.target_zone}" if action.target_zone else action.action_type.value


def _action_support(model: CandidateModel, state: GameState, player_id: str, action: Action) -> int:
    small = getattr(model, "small_model", model)
    support_method = getattr(small, "action_support", None)
    if callable(support_method):
        try:
            return int(support_method(state, player_id))
        except (KeyError, TypeError, ValueError):
            return 0
    counts = getattr(small, "_action_counts", {})
    state_key_fn = getattr(small, "state_key", None)
    if state_key_fn is None:
        return 0
    try:
        state_key = state_key_fn(state, player_id)
    except (KeyError, TypeError):
        return 0
    return int(sum(counts.get(state_key, {}).values()))


def _action_outcome_counts(
    model: CandidateModel,
    state: GameState,
    player_id: str,
    action: Action,
) -> tuple[int, int] | None:
    small = getattr(model, "small_model", model)
    outcome_method = getattr(small, "outcome_counts", None)
    if callable(outcome_method):
        try:
            return outcome_method(state, player_id, action)
        except (KeyError, TypeError, ValueError):
            return None
    outcomes = getattr(small, "_outcomes", {})
    state_key_fn = getattr(small, "state_key", None)
    action_key_fn = getattr(small, "action_key", None)
    if state_key_fn is None or action_key_fn is None:
        return None
    try:
        state_key = state_key_fn(state, player_id)
        action_key = action_key_fn(action)
        values = outcomes.get(state_key, {}).get(action_key)
    except (KeyError, TypeError, AttributeError):
        return None
    if not isinstance(values, (list, tuple)) or len(values) != 2:
        return None
    wins, losses = int(values[0]), int(values[1])
    if wins < 0 or losses < 0:
        return None
    return wins, losses


def _candidate_model_type(model: CandidateModel | None) -> str:
    if model is None:
        return "unavailable"
    if isinstance(model, FullLightGBMModel) and model.is_fitted:
        return "full_lightgbm_blended_with_small_statistical"
    if isinstance(model, SmallStatisticalModel) or isinstance(getattr(model, "small_model", None), SmallStatisticalModel):
        return "small_statistical"
    return "custom_candidate_model"


def _candidate_rows(
    model: CandidateModel | None,
    state: GameState | None,
    player_id: str | None,
    *,
    min_support: int,
) -> tuple[list[dict[str, Any]], str]:
    if model is None or state is None or player_id is None or player_id not in state.players:
        return [], "unavailable"
    legal = legal_actions(state, player_id)
    if not legal:
        return [], "no_legal_actions"
    scores = model.score_actions(state, player_id, legal)
    entropy_method = getattr(model, "normalized_entropy", None)
    try:
        entropy = float(entropy_method(state, player_id, legal)) if callable(entropy_method) else 1.0
    except (KeyError, TypeError, ValueError, ZeroDivisionError):
        entropy = 1.0
    entropy = min(1.0, max(0.0, entropy))
    action_outcomes = {
        _action_name(action): _action_outcome_counts(model, state, player_id, action)
        for action in legal
    }
    outcome_means = [
        (wins + 1.0) / (wins + losses + 2.0)
        for values in action_outcomes.values()
        if values is not None
        for wins, losses in (values,)
        if wins + losses > 0
    ]
    outcome_variance = (
        len(outcome_means) == len(legal)
        and max(outcome_means) - min(outcome_means) > 1e-9
    )
    small = getattr(model, "small_model", model)
    support_info_method = getattr(small, "action_support_info", None)
    support_info = (
        support_info_method(state, player_id)
        if callable(support_info_method)
        else {"level": "exact", "raw_support": None}
    )
    rows: list[dict[str, Any]] = []
    for action in legal:
        action_name = _action_name(action)
        success = min(1.0, max(0.0, float(scores[action])))
        support = _action_support(model, state, player_id, action)
        outcome_counts = action_outcomes[action_name]
        rows.append(
            {
                "action": action_name,
                "candidate_success_probability": success,
                "death_probability": 1.0 - success,
                "round_value_delta": success,
                "sample_count": support,
                "support_level": support_info.get("level"),
                "raw_support": support_info.get("raw_support"),
                "confidence": support / (support + 10.0) if support else 0.0,
                "entropy": entropy,
                "outcome_support": (
                    sum(outcome_counts) if outcome_counts is not None else 0
                ),
                "outcome_evidence": bool(
                    outcome_counts is not None and sum(outcome_counts) > 0
                ),
                "outcome_variance": outcome_variance,
                "rollout_quality": (
                    "action_outcome_variance"
                    if outcome_variance
                    else "no_action_outcome_variance"
                ),
                "legal": True,
                "supported": support >= min_support,
                **(
                    {
                        "posterior_successes": outcome_counts[0],
                        "posterior_failures": outcome_counts[1],
                    }
                    if outcome_counts is not None
                    else {}
                ),
            }
        )
    return rows, "simulator_action_value"


def _least_death_risk_candidate(
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Return the lowest conservative death-risk estimate among legal actions.

    This is deliberately separate from the primary round-value ranking.  The
    current candidate model's ``death_probability`` is a round-loss proxy, so
    the output carries its provenance and should be shown as a fallback when
    the primary recommendation abstains.
    """

    estimates: list[dict[str, Any]] = []
    for candidate in candidates:
        action = str(candidate.get("action") or "")
        if not action or candidate.get("legal") is False:
            continue
        successes = candidate.get("posterior_successes")
        failures = candidate.get("posterior_failures")
        try:
            successes_value = float(successes)
            failures_value = float(failures)
        except (TypeError, ValueError):
            successes_value = failures_value = -1.0
        if (
            successes_value >= 0
            and failures_value >= 0
            and math.isfinite(successes_value)
            and math.isfinite(failures_value)
            and successes_value + failures_value > 0
        ):
            alpha = failures_value + 1.0
            beta = successes_value + 1.0
            total = alpha + beta
            mean = alpha / total
            variance = alpha * beta / (total * total * (total + 1.0))
            source = "round_loss_proxy_posterior"
            support = successes_value + failures_value
        else:
            try:
                mean = min(1.0, max(0.0, float(candidate.get("death_probability", 0.5))))
            except (TypeError, ValueError):
                mean = 0.5
            try:
                support = max(0.0, float(candidate.get("sample_count", 0)))
            except (TypeError, ValueError):
                support = 0.0
            alpha = mean * support + 1.0
            beta = (1.0 - mean) * support + 1.0
            total = alpha + beta
            variance = alpha * beta / (total * total * (total + 1.0))
            source = "round_loss_proxy_support_prior"
            outcome_evidence = False
        if (
            successes_value >= 0
            and failures_value >= 0
            and math.isfinite(successes_value)
            and math.isfinite(failures_value)
            and successes_value + failures_value > 0
        ):
            outcome_evidence = True
        upper = min(1.0, max(0.0, mean + 1.645 * math.sqrt(max(0.0, variance))))
        outcome_variance = bool(candidate.get("outcome_variance"))
        candidate_supported = bool(candidate.get("supported", False))
        if not outcome_evidence:
            fallback_status = "abstained_no_outcome_evidence"
        elif not outcome_variance:
            fallback_status = "abstained_no_action_outcome_variance"
        elif not candidate_supported:
            fallback_status = "unsupported_candidate_state"
        else:
            fallback_status = "usable"
        estimates.append(
            {
                "action": action,
                "death_probability": mean,
                "round_loss_probability_proxy": mean,
                "is_proxy": True,
                "risk_upper_bound": upper,
                "risk_interval_level": 0.90,
                "risk_interval_method": "beta_normal_approximation_upper_bound",
                "support": int(support),
                "support_level": candidate.get("support_level"),
                "supported": candidate_supported,
                "outcome_evidence": outcome_evidence,
                "outcome_variance": outcome_variance,
                "fallback_usable": fallback_status == "usable",
                "fallback_status": fallback_status,
                "risk_source": source,
                "selection_mode": "lowest_conservative_death_risk",
            }
        )
    if not estimates:
        return None
    return min(
        estimates,
        key=lambda item: (
            float(item["risk_upper_bound"]),
            float(item["death_probability"]),
            -int(item["support"]),
            str(item["action"]),
        ),
    )


def _snapshot_for_event(rows: list[dict[str, Any]], *, round_num: int, tick: int) -> dict[str, Any] | None:
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
    for key in ("actor_id", "attacker_id", "victim_id"):
        if event.get(key) not in (None, ""):
            return str(event[key])
    return None


def _find_moments(
    report: Mapping[str, Any],
    *,
    threshold: float,
    max_moments: int | None,
) -> list[dict[str, Any]]:
    moments: dict[tuple[Any, ...], dict[str, Any]] = {}
    timeline = report.get("timeline") or []
    for item in timeline:
        if not isinstance(item, Mapping):
            continue
        round_num = _int(item.get("round_num"))
        tick = _int(item.get("tick"))
        swing = item.get("probability_swing")
        swing_value = abs(_number((swing or {}).get("absolute"))) if isinstance(swing, Mapping) else 0.0
        events = [event for event in item.get("events") or [] if isinstance(event, Mapping)]
        important_events = [event for event in events if str(event.get("category")) in {"kill", "death", "bomb"}]
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
                    "least_death_risk_action": (
                        least_risk.get("action") if isinstance(least_risk, Mapping) else None
                    ),
                    "least_death_probability": (
                        least_risk.get("death_probability") if isinstance(least_risk, Mapping) else None
                    ),
                    "least_death_round_loss_probability_proxy": (
                        least_risk.get("round_loss_probability_proxy")
                        if isinstance(least_risk, Mapping)
                        else None
                    ),
                    "least_death_is_proxy": (
                        bool(least_risk.get("is_proxy", True))
                        if isinstance(least_risk, Mapping)
                        else None
                    ),
                    "least_death_risk_upper_bound": (
                        least_risk.get("risk_upper_bound") if isinstance(least_risk, Mapping) else None
                    ),
                    "least_death_risk_interval_level": (
                        least_risk.get("risk_interval_level")
                        if isinstance(least_risk, Mapping)
                        else None
                    ),
                    "least_death_risk_interval_method": (
                        least_risk.get("risk_interval_method")
                        if isinstance(least_risk, Mapping)
                        else None
                    ),
                    "least_death_risk_support": (
                        least_risk.get("support") if isinstance(least_risk, Mapping) else None
                    ),
                    "least_death_risk_supported": (
                        bool(least_risk.get("supported", False))
                        if isinstance(least_risk, Mapping)
                        else False
                    ),
                    "least_death_risk_outcome_variance": (
                        least_risk.get("outcome_variance") if isinstance(least_risk, Mapping) else None
                    ),
                    "least_death_risk_outcome_evidence": (
                        least_risk.get("outcome_evidence")
                        if isinstance(least_risk, Mapping)
                        else None
                    ),
                    "least_death_risk_fallback_usable": (
                        bool(least_risk.get("fallback_usable", False))
                        if isinstance(least_risk, Mapping)
                        else False
                    ),
                    "least_death_risk_status": (
                        least_risk.get("fallback_status")
                        if isinstance(least_risk, Mapping)
                        else None
                    ),
                    "least_death_risk_source": (
                        least_risk.get("risk_source") if isinstance(least_risk, Mapping) else None
                    ),
                    "round_win_probability": best.get("candidate_success_probability"),
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


def build_replay_analysis(
    record: Mapping[str, Any],
    model: Any,
    *,
    candidate_model: CandidateModel | None = None,
    config: HarnessConfig | None = None,
) -> dict[str, Any]:
    """Generate key moments and support-aware estimated alternatives."""

    settings = config or HarnessConfig()
    normalized = dict(record)
    report = model.analyse_match(
        normalized,
        sample_every=settings.sample_every,
        include_terminal=True,
        max_timeline_points=None,
    )
    feature_rows = record_to_rows(normalized, sample_every=settings.sample_every, include_terminal=True)
    action_rows = infer_actions(normalized, window_seconds=2.0)
    moments = _find_moments(report, threshold=settings.moment_threshold, max_moments=settings.max_moments)
    output_moments: list[dict[str, Any]] = []
    for moment in moments:
        round_num = int(moment["round_num"])
        tick = int(moment["tick"])
        snapshot_row = _snapshot_for_event(feature_rows, round_num=round_num, tick=tick)
        event = moment["events"][0] if moment["events"] else {}
        event_ticks = [_int(item.get("tick")) for item in moment["events"] if _int(item.get("tick")) >= 0]
        decision_tick = min(event_ticks) if event_ticks else tick
        state = reconstruct_game_state(
            normalized,
            round_num=round_num,
            tick=decision_tick,
            before_event=True,
        )
        actor = _event_actor(event)
        observed_action = _observed_action(action_rows, actor=actor, round_num=round_num, tick=decision_tick)
        candidates, candidate_source = _candidate_rows(
            candidate_model,
            state,
            actor,
            min_support=settings.min_support,
        )
        ranked = rank_candidate_actions(candidates, min_support=settings.min_support) if candidates else []
        for candidate in ranked:
            candidate["estimate_type"] = "simulator_action_value_estimate"
        best = ranked[0] if ranked else None
        least_risk = _least_death_risk_candidate(ranked)
        observed_candidate: dict[str, Any] | None = None
        classification = DecisionClass.NO_OBSERVED_ACTION.value
        regret = None
        if best is not None and actor is not None:
            observed_candidate = next(
                (row for row in ranked if row["action"] == str(event.get("action") or "")),
                None,
            )
            if observed_candidate is None and observed_action is not None:
                observed_candidate = next(
                    (row for row in ranked if row["action"] == observed_action["action"]),
                    None,
                )
            if observed_candidate is None or not observed_candidate["supported"] or not best["supported"]:
                classification = DecisionClass.INSUFFICIENT_EVIDENCE.value
            else:
                regret = float(best["round_value_delta"]) - float(observed_candidate["round_value_delta"])
                classification = (
                    DecisionClass.BAD.value
                    if regret >= settings.recommendation_margin
                    else DecisionClass.GOOD.value
                    if regret <= 0.0
                    else DecisionClass.NEUTRAL.value
                )
        output_moments.append(
            {
                **moment,
                "actor_id": actor,
                "decision_tick": decision_tick,
                "snapshot": snapshot_row.get("snapshot") if snapshot_row else None,
                "candidate_source": candidate_source,
                "candidate_model_type": _candidate_model_type(candidate_model),
                "legal_candidate_count": len(ranked),
                "candidate_actions": ranked,
                "observed_action": observed_candidate,
                "observed_action_name": observed_action["action"] if observed_action else None,
                "best_estimated_alternative": best,
                "least_death_risk_action": least_risk,
                "estimated_regret": regret,
                "decision_class": classification,
            }
        )
    classes = defaultdict(int)
    for item in output_moments:
        classes[str(item["decision_class"])] += 1
    total_kills = int((report.get("event_counts") or {}).get("kill", 0))
    base_report = {
        "report_type": "combined_replay_analysis",
        "schema_version": HARNESS_SCHEMA_VERSION,
        "source": report.get("source", "unknown"),
        "map_name": report.get("map_name", "unknown"),
        "config": {
            "moment_threshold": settings.moment_threshold,
            "max_moments": settings.max_moments,
            "min_support": settings.min_support,
            "recommendation_margin": settings.recommendation_margin,
        },
        "full_match": report,
        "moments": output_moments,
        "kill_analysis": [],
        "summary": {
            "moment_count": len(output_moments),
            "kill_count": total_kills,
            "kill_analysis_count": 0,
            "least_risk_fallback_count": 0,
            "least_risk_candidate_count": 0,
            "least_risk_usable_count": 0,
            "decision_classes": dict(sorted(classes.items())),
            "recommendations_are_counterfactual_estimates": True,
            "candidate_model_type": _candidate_model_type(candidate_model),
        },
        "candidate_legality": {
            "rules": "cs2_sim.rules.legal_actions",
            "topology": "simulator_default_adjacency",
            "note": (
                "Replay nav-area labels are preserved, but map-specific navigation "
                "edges require a map adapter before movement alternatives can be "
                "treated as CS2-legal."
            ),
        },
    }
    annotated = annotate_probability_labels(
        base_report,
        thresholds=ProbabilityLabelThresholds(
            min_support=settings.min_support,
            probability_of_improvement=settings.probability_of_improvement_threshold,
            expected_regret=(
                settings.recommendation_margin
                if settings.expected_regret_threshold is None
                else settings.expected_regret_threshold
            ),
            credible_level=settings.credible_level,
            max_interval_width=settings.max_interval_width,
            posterior_samples=settings.posterior_samples,
            seed=settings.posterior_seed,
        ),
    )
    annotated["kill_analysis"] = _kill_analysis_rows(annotated.get("moments") or [])
    annotated["summary"]["kill_analysis_count"] = len(annotated["kill_analysis"])
    annotated["summary"]["least_risk_candidate_count"] = sum(
        1 for item in annotated.get("moments") or [] if item.get("least_death_risk_action")
    )
    annotated["summary"]["least_risk_usable_count"] = sum(
        1
        for item in annotated.get("moments") or []
        if isinstance(item.get("least_death_risk_action"), Mapping)
        and item["least_death_risk_action"].get("fallback_usable")
    )
    annotated["summary"]["least_risk_fallback_count"] = sum(
        1
        for item in annotated.get("moments") or []
        if item.get("least_death_risk_action")
        and item.get("probability_decision_class") == DecisionClass.INSUFFICIENT_EVIDENCE.value
    )
    return annotated


def load_candidate_model(path: str | Path) -> CandidateModel:
    """Load the simulator-trained action scorer, with statistical fallback."""

    candidate_path = Path(path)
    if candidate_path.name == "small_statistical.json":
        return SmallStatisticalModel.load(candidate_path)
    try:
        return FullLightGBMModel.load(candidate_path)
    except (ImportError, RuntimeError, ValueError):
        fallback = candidate_path.with_name("small_statistical.json")
        if not fallback.is_file():
            raise
        return SmallStatisticalModel.load(fallback)


__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "CandidateModel",
    "DecisionClass",
    "HarnessConfig",
    "build_replay_analysis",
    "load_candidate_model",
    "reconstruct_game_state",
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="normalized replay JSONL")
    parser.add_argument("--record-index", type=int, default=0)
    parser.add_argument("--release-dir", type=Path, default=Path("model/artifacts/releases"))
    parser.add_argument("--version", default="v2")
    parser.add_argument("--candidate-model", type=Path, default=None)
    parser.add_argument("--moment-threshold", type=float, default=0.08)
    parser.add_argument("--max-moments", type=int, default=25)
    parser.add_argument(
        "--all-moments",
        action="store_true",
        help="analyze every detected kill/death/bomb moment instead of the default cap",
    )
    parser.add_argument("--min-support", type=int, default=5)
    parser.add_argument("--recommendation-margin", type=float, default=0.05)
    parser.add_argument("--probability-of-improvement-threshold", type=float, default=0.8)
    parser.add_argument("--expected-regret-threshold", type=float, default=None)
    parser.add_argument("--credible-level", type=float, default=0.9)
    parser.add_argument("--max-interval-width", type=float, default=0.8)
    parser.add_argument("--posterior-samples", type=int, default=5000)
    parser.add_argument("--posterior-seed", type=int, default=7)
    parser.add_argument("--sample-every", type=int, default=8)
    parser.add_argument("--output", type=Path, default=Path("model/artifacts/replay_analysis.json"))
    args = parser.parse_args()
    if args.record_index < 0:
        raise ValueError("record-index cannot be negative")
    selected: dict[str, Any] | None = None
    record_number = 0
    with args.input.open(encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            if record_number == args.record_index:
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("replay JSONL records must be objects")
                selected = value
                break
            record_number += 1
    if selected is None:
        raise ValueError(f"no replay record at index {args.record_index}: {args.input}")
    from cs2_sim import ModelConfig, ReplayModel

    release_dir = args.release_dir
    if not release_dir.is_dir() and Path("Noah").joinpath(release_dir).is_dir():
        release_dir = Path("Noah") / release_dir
    runtime = ReplayModel.load(ModelConfig(releases_dir=release_dir, version=args.version))
    from Noah.training.recommendations import (
        ProbabilityLabelThresholds,
        annotate_probability_labels,
    )

    expected_regret_threshold = (
        args.recommendation_margin
        if args.expected_regret_threshold is None
        else args.expected_regret_threshold
    )
    if args.candidate_model:
        result = build_replay_analysis(
            selected,
            runtime,
            candidate_model=load_candidate_model(args.candidate_model),
            config=HarnessConfig(
                moment_threshold=args.moment_threshold,
                max_moments=None if args.all_moments else args.max_moments,
                min_support=args.min_support,
                recommendation_margin=args.recommendation_margin,
                sample_every=args.sample_every,
                probability_of_improvement_threshold=args.probability_of_improvement_threshold,
                expected_regret_threshold=expected_regret_threshold,
                credible_level=args.credible_level,
                max_interval_width=args.max_interval_width,
                posterior_samples=args.posterior_samples,
                posterior_seed=args.posterior_seed,
            ),
        )
        if result.get("probability_label_schema_version") != "probability_labels_v1":
            result = annotate_probability_labels(
                result,
                thresholds=ProbabilityLabelThresholds(
                    min_support=args.min_support,
                    probability_of_improvement=args.probability_of_improvement_threshold,
                    expected_regret=expected_regret_threshold,
                    credible_level=args.credible_level,
                    max_interval_width=args.max_interval_width,
                    posterior_samples=args.posterior_samples,
                    seed=args.posterior_seed,
                ),
            )
    else:
        result = runtime.analyse_replay(
            selected,
            moment_threshold=args.moment_threshold,
            max_moments=None if args.all_moments else args.max_moments,
            min_support=args.min_support,
            recommendation_margin=args.recommendation_margin,
            sample_every=args.sample_every,
            probability_of_improvement_threshold=args.probability_of_improvement_threshold,
            expected_regret_threshold=expected_regret_threshold,
            credible_level=args.credible_level,
            max_interval_width=args.max_interval_width,
            posterior_samples=args.posterior_samples,
            posterior_seed=args.posterior_seed,
        )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))
    print(f"[analysis] moments={len(result['moments'])} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

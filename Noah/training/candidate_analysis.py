"""Candidate-action scoring and observational engagement helpers.

This module contains the model-facing half of Noah's replay harness.  It is
deliberately independent of report construction: callers provide a
reconstructed :class:`~cs2_sim.state.GameState`, a candidate model, and (for
engagement scoring) a normalized engagement window.  Candidate values remain
estimates and preserve the harness's support and abstention metadata.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from cs2_sim.action_vocabulary import (
    ABSTRACT_CANDIDATE_ACTION_NAMES,
    action_parameters,
    canonical_action,
)
from cs2_sim.actions import Action
from cs2_sim.core.model import FullLightGBMModel, SmallStatisticalModel
from cs2_sim.rules import legal_actions
from cs2_sim.state import GameState

from Noah.training.recommendations import rank_candidate_actions


class CandidateModel(Protocol):
    """Minimal action-value interface consumed by the harness."""

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


def _action_name(action: Action) -> str:
    return f"{action.action_type.value}:{action.target_zone}" if action.target_zone else action.action_type.value


def _movement_action(action: str) -> str:
    return "move" if action.startswith("move") else "hold" if action == "hold" else action


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
    outcome_variance = len(outcome_means) == len(legal) and max(outcome_means) - min(outcome_means) > 1e-9
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
                "outcome_support": sum(outcome_counts) if outcome_counts is not None else 0,
                "outcome_evidence": bool(outcome_counts is not None and sum(outcome_counts) > 0),
                "outcome_variance": outcome_variance,
                "rollout_quality": "action_outcome_variance" if outcome_variance else "no_action_outcome_variance",
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


def _least_death_risk_candidate(candidates: Iterable[Mapping[str, Any]]) -> dict[str, Any] | None:
    """Return the lowest conservative death-risk estimate among legal actions."""

    estimates: list[dict[str, Any]] = []
    for candidate in candidates:
        action = str(candidate.get("action") or "")
        if not action or candidate.get("legal") is False:
            continue
        direct_death_head = candidate.get("death_probability_source") == "engagement_death_head"
        successes = candidate.get("posterior_successes")
        failures = candidate.get("posterior_failures")
        try:
            successes_value = float(successes)
            failures_value = float(failures)
        except (TypeError, ValueError):
            successes_value = failures_value = -1.0
        if direct_death_head:
            mean = min(1.0, max(0.0, _number(candidate.get("death_probability"), 0.5)))
            support = max(0.0, _number(candidate.get("sample_count"), 0.0))
            alpha = mean * support + 1.0
            beta = (1.0 - mean) * support + 1.0
            total = alpha + beta
            variance = alpha * beta / (total * total * (total + 1.0))
            source = "engagement_death_head"
            outcome_evidence = support > 0
        elif (
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
        if not direct_death_head and (
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
                "round_loss_probability_proxy": mean if not direct_death_head else None,
                "is_proxy": not direct_death_head,
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


def _augment_candidates_with_engagement(
    model: Any,
    candidates: list[dict[str, Any]],
    window: Mapping[str, Any] | None,
    *,
    min_support: int,
) -> list[dict[str, Any]]:
    """Rank legal actions with observational multi-head engagement utility."""

    score = getattr(model, "score_engagement", None)
    if not callable(score) or window is None:
        return candidates
    candidates = [dict(candidate) for candidate in candidates]
    simulator_values = [_number(candidate.get("candidate_success_probability"), 0.5) for candidate in candidates]
    default_simulator_value = sum(simulator_values) / len(simulator_values) if simulator_values else 0.5
    existing_movements = {_movement_action(str(candidate.get("action") or "")) for candidate in candidates}
    for action in ABSTRACT_CANDIDATE_ACTION_NAMES:
        if action in existing_movements:
            continue
        candidates.append(
            {
                "action": action,
                "candidate_success_probability": default_simulator_value,
                "round_value_delta": default_simulator_value,
                "death_probability": 1.0 - default_simulator_value,
                "sample_count": 0,
                "confidence": 0.0,
                "entropy": 1.0,
                "legal": True,
                "legality_scope": "abstract_movement_choice",
                "support_level": "engagement_state",
            }
        )
    augmented: list[dict[str, Any]] = []
    utilities: list[float] = []
    for original in candidates:
        candidate = dict(original)
        row = dict(window)
        candidate_action = str(candidate.get("action") or "")
        row["observed_action"] = _movement_action(candidate_action)
        row["observed_action_name"] = canonical_action(candidate_action)
        row["observed_action_parameters"] = action_parameters(candidate_action)
        prediction = dict(score(row))
        death = min(1.0, max(0.0, _number(prediction.get("death_probability"), 0.5)))
        survival = min(1.0, max(0.0, _number(prediction.get("survival_probability"), 1.0 - death)))
        kill = min(1.0, max(0.0, _number(prediction.get("kill_probability"), 0.0)))
        trade = min(1.0, max(0.0, _number(prediction.get("trade_probability"), 0.0)))
        damage = min(1.0, max(0.0, _number(prediction.get("damage_probability"), kill)))
        simulator_value = min(1.0, max(0.0, _number(candidate.get("candidate_success_probability"), 0.5)))
        round_win_raw = prediction.get("round_win_probability")
        round_win = simulator_value if round_win_raw is None else min(1.0, max(0.0, _number(round_win_raw, simulator_value)))
        utility = 0.35 * round_win + 0.25 * survival + 0.15 * kill + 0.10 * trade + 0.10 * damage + 0.05 * simulator_value
        support = max(0, _int(prediction.get("sample_count"), 0))
        confidence = min(1.0, max(0.0, _number(prediction.get("confidence"), 0.0)))
        candidate.update(
            {
                "candidate_success_probability": utility,
                "round_value_delta": utility,
                "death_probability": death,
                "death_probability_source": "engagement_death_head",
                "survival_probability": survival,
                "kill_probability": kill,
                "trade_probability": trade,
                "damage_probability": damage,
                "round_win_probability": round_win,
                "simulator_value_probability": simulator_value,
                "coaching_utility": utility,
                "utility_weights": {"round_win": 0.35, "survival": 0.25, "kill": 0.15, "trade": 0.10, "damage": 0.10, "simulator": 0.05},
                "sample_count": support,
                "support_level": prediction.get("support_level", "engagement_state"),
                "confidence": confidence,
                "entropy": _number(prediction.get("entropy"), 1.0),
                "outcome_support": support,
                "outcome_evidence": support > 0,
                "supported": bool(prediction.get("supported")) and support >= min_support,
                "engagement_state_key": prediction.get("state_key"),
                "engagement_lightgbm_blend_weight": prediction.get("lightgbm_blend_weight", 0.0),
                "estimate_type": "observational_action_conditioned_multi_head_estimate",
                "posterior_successes": utility * support,
                "posterior_failures": (1.0 - utility) * support,
                "posterior_count_semantics": "effective_weighted_utility_counts",
            }
        )
        augmented.append(candidate)
        utilities.append(utility)
    has_variance = bool(utilities and max(utilities) - min(utilities) > 1e-9)
    for candidate in augmented:
        candidate["outcome_variance"] = has_variance
        candidate["rollout_quality"] = "observed_action_outcomes" if has_variance else "no_action_outcome_variance"
    return rank_candidate_actions(augmented, min_support=min_support)


__all__ = [
    "CandidateModel",
    "_action_name",
    "_action_outcome_counts",
    "_action_support",
    "_augment_candidates_with_engagement",
    "_candidate_model_type",
    "_candidate_rows",
    "_least_death_risk_candidate",
    "_movement_action",
]

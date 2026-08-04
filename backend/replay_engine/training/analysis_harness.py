"""Combined key-moment and estimated-alternative replay analysis.

This module is the stable orchestration facade for the harness. Replay-state
reconstruction, candidate scoring, and report projection live in dedicated
modules so callers can keep using the existing ``build_replay_analysis`` API
without depending on the implementation layout.
"""

from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from cs2_sim.core.model import FullLightGBMModel, SmallStatisticalModel

from backend.replay_engine.training import replay_state as _replay_state
from backend.replay_engine.training.analysis_report import (
    _coached_player,
    _display_action_name,
    _engagement_window_for_kill,
    _find_moments,
    _kill_analysis_rows,
    _movement_action,
    _observed_action,
    _snapshot_for_event,
)
from backend.replay_engine.training.candidate_analysis import (
    CandidateModel,
    _augment_candidates_with_engagement,
    _candidate_model_type,
    _candidate_rows,
    _least_death_risk_candidate,
)
from backend.replay_engine.training.full_features import record_to_rows
from backend.replay_engine.training.infer_actions import infer_actions
from backend.replay_engine.training.recommendations import (
    ProbabilityLabelThresholds,
    annotate_probability_labels,
    rank_candidate_actions,
)

HARNESS_SCHEMA_VERSION = "replay_analysis_v1"

# Keep the old private helper names available for compatibility while the
# implementation lives in the dedicated replay-state module.
_bomb_state = _replay_state.bomb_state
_build_tick_index = _replay_state.build_tick_index
_nearest_tick_rows = _replay_state.nearest_tick_rows
_round_start_tick = _replay_state.round_start_tick
_tick_rate = _replay_state.tick_rate
reconstruct_game_state = _replay_state.reconstruct_game_state


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
        if not 0 <= self.recommendation_margin <= 1:
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


def _int(value: Any, default: int = -1) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


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
    feature_rows = record_to_rows(
        normalized,
        sample_every=settings.sample_every,
        include_terminal=True,
    )
    action_rows = infer_actions(normalized, window_seconds=2.0)
    tick_index = _build_tick_index(normalized)
    engagement_windows: list[dict[str, Any]] = []
    if callable(getattr(model, "score_engagement", None)):
        from backend.replay_engine.training.engagement_windows import extract_engagement_windows

        engagement_windows = extract_engagement_windows(
            normalized,
            horizon_seconds=5.0,
            lookback_seconds=3.0,
            decision_lead_seconds=1.0,
            action_window_seconds=1.0,
        )

    moments = _find_moments(
        report,
        threshold=settings.moment_threshold,
        max_moments=settings.max_moments,
    )
    output_moments: list[dict[str, Any]] = []
    for moment in moments:
        round_num = int(moment["round_num"])
        tick = int(moment["tick"])
        snapshot_row = _snapshot_for_event(feature_rows, round_num=round_num, tick=tick)
        event = moment["events"][0] if moment["events"] else {}
        event_ticks = [
            _int(item.get("tick"))
            for item in moment["events"]
            if _int(item.get("tick")) >= 0
        ]
        event_tick = min(event_ticks) if event_ticks else tick
        actor = _coached_player(event)
        engagement_window = _engagement_window_for_kill(
            engagement_windows,
            round_num=round_num,
            tick=event_tick,
            player_id=actor,
        )
        decision_tick = (
            _int(engagement_window.get("anchor_tick"))
            if engagement_window is not None
            else event_tick
        )
        state = reconstruct_game_state(
            normalized,
            round_num=round_num,
            tick=decision_tick,
            before_event=True,
            tick_index=tick_index,
        )
        observed_action = _observed_action(
            action_rows,
            actor=actor,
            round_num=round_num,
            tick=decision_tick,
        )
        if engagement_window is not None and engagement_window.get("observed_action"):
            action_name = str(engagement_window["observed_action"])
            destination = engagement_window.get("observed_action_destination")
            if action_name == "move" and destination not in (None, "", "unknown"):
                action_name = f"move_to_adjacent_zone:{destination}"
            elif action_name in {"move_to_adjacent_zone", "peek"} and destination not in (
                None,
                "",
                "unknown",
            ):
                action_name = f"{action_name}:{destination}"
            parameters = engagement_window.get("observed_action_parameters")
            parameters = parameters if isinstance(parameters, Mapping) else {}
            observed_action = {
                "action": action_name,
                "parameters": parameters,
                "tick": decision_tick,
                "source": "engagement_decision_window",
            }

        candidates, candidate_source = _candidate_rows(
            candidate_model,
            state,
            actor,
            min_support=settings.min_support,
        )
        ranked = (
            rank_candidate_actions(candidates, min_support=settings.min_support)
            if candidates
            else []
        )
        for candidate in ranked:
            candidate.setdefault("estimate_type", "simulator_action_value_estimate")
        engagement_ranked = (
            ranked
            if candidate_source == "rubric_action_suitability"
            else _augment_candidates_with_engagement(
                model,
                ranked,
                engagement_window,
                min_support=settings.min_support,
            )
        )
        if engagement_ranked is not ranked:
            ranked = engagement_ranked
            candidate_source = f"{candidate_source}+observational_engagement"

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
            if observed_candidate is None and observed_action is not None:
                observed_movement = _movement_action(str(observed_action["action"]))
                observed_candidate = next(
                    (
                        row
                        for row in ranked
                        if _movement_action(str(row.get("action") or "")) == observed_movement
                    ),
                    None,
                )
            if observed_candidate is None or not observed_candidate["supported"] or not best["supported"]:
                classification = DecisionClass.INSUFFICIENT_EVIDENCE.value
            else:
                regret = float(best["round_value_delta"]) - float(
                    observed_candidate["round_value_delta"]
                )
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
                "coached_player_role": (
                    "victim" if str(event.get("category") or "") == "kill" else "actor"
                ),
                "decision_tick": decision_tick,
                "decision_lead_seconds": (
                    engagement_window.get("decision_lead_seconds")
                    if engagement_window is not None
                    else 0.0
                ),
                "engagement_window": engagement_window,
                "snapshot": snapshot_row.get("snapshot") if snapshot_row else None,
                "candidate_source": candidate_source,
                "candidate_model_type": _candidate_model_type(candidate_model),
                "candidate_action_count": len(ranked),
                "legal_candidate_count": sum(1 for row in ranked if row.get("legal") is True),
                "candidate_actions": ranked,
                "observed_action": observed_candidate,
                "observed_action_name": (
                    _display_action_name(observed_action) if observed_action else None
                ),
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
    """Load the candidate scorer, preserving its target semantics."""

    candidate_path = Path(path)
    if candidate_path.name == "small_statistical.json":
        model = SmallStatisticalModel.load(candidate_path)
        return _attach_candidate_metadata(model, candidate_path)
    try:
        return _attach_candidate_metadata(FullLightGBMModel.load(candidate_path), candidate_path)
    except (ImportError, RuntimeError, ValueError):
        fallback = candidate_path.with_name("small_statistical.json")
        if not fallback.is_file():
            raise
        return _attach_candidate_metadata(SmallStatisticalModel.load(fallback), fallback)


def _attach_candidate_metadata(model: CandidateModel, path: Path) -> CandidateModel:
    """Attach optional training metadata to legacy and statistical artifacts."""

    metrics_path = path.parent / "candidate_training_metrics.json"
    if not metrics_path.is_file():
        return model
    try:
        payload = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return model
    if not isinstance(payload, Mapping):
        return model
    if getattr(model, "training_target", None) is None:
        model.training_target = payload.get("training_target")
    if getattr(model, "training_label_source", None) is None:
        model.training_label_source = payload.get("label_source") or payload.get("rollout_label_source")
    return model


__all__ = [
    "HARNESS_SCHEMA_VERSION",
    "CandidateModel",
    "DecisionClass",
    "HarnessConfig",
    "build_replay_analysis",
    "load_candidate_model",
    "reconstruct_game_state",
]

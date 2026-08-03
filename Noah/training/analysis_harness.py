"""Combined key-moment and estimated-alternative replay analysis.

The harness has two intentionally separate stages:

1. observed replay evidence (round-value swings and deterministic events);
2. legal candidate scoring from a simulator-trained action-value model.

Candidate results are estimates, not proof of a counterfactual.  If the state
cannot be reconstructed or candidate support is too low, the harness abstains.
"""

from __future__ import annotations

import argparse
import json
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
from Noah.training.recommendations import rank_candidate_actions

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
    max_moments: int = 25
    min_support: int = 5
    recommendation_margin: float = 0.05
    sample_every: int = 8

    def __post_init__(self) -> None:
        if not 0 < self.moment_threshold <= 1:
            raise ValueError("moment_threshold must be between 0 and 1")
        if self.max_moments <= 0 or self.min_support < 0:
            raise ValueError("max_moments must be positive and min_support cannot be negative")
        if self.recommendation_margin < 0 or self.recommendation_margin > 1:
            raise ValueError("recommendation_margin must be between 0 and 1")
        if self.sample_every <= 0:
            raise ValueError("sample_every must be positive")


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


def _nearest_tick_rows(record: Mapping[str, Any], *, round_num: int, tick: int) -> dict[str, dict[str, Any]]:
    """Reconstruct latest player rows at or before a replay event."""

    latest: dict[str, tuple[int, dict[str, Any]]] = {}
    for ordinal, row in enumerate(record.get("ticks") or []):
        if not isinstance(row, Mapping) or _int(row.get("round_num")) != round_num:
            continue
        row_tick = _int(row.get("tick"))
        if row_tick < 0 or row_tick > tick:
            continue
        player_id = _identity(row, ordinal)
        previous = latest.get(player_id)
        if previous is None or row_tick >= previous[0]:
            latest[player_id] = (row_tick, dict(row))
    return {player_id: row for player_id, (_, row) in latest.items()}


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


def reconstruct_game_state(record: Mapping[str, Any], *, round_num: int, tick: int) -> GameState | None:
    """Build the simulator state needed for legal candidate generation."""

    rows = _nearest_tick_rows(record, round_num=round_num, tick=tick)
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
    return GameState(
        players,
        bomb_state=bomb_state,
        bomb_site=bomb_site,
        bomb_time_remaining=bomb_time,
        time_seconds=0.0,
    )


def _action_name(action: Action) -> str:
    return f"{action.action_type.value}:{action.target_zone}" if action.target_zone else action.action_type.value


def _action_support(model: CandidateModel, state: GameState, player_id: str, action: Action) -> int:
    small = getattr(model, "small_model", model)
    counts = getattr(small, "_action_counts", {})
    state_key_fn = getattr(small, "state_key", None)
    if state_key_fn is None:
        return 0
    try:
        state_key = state_key_fn(state, player_id)
    except (KeyError, TypeError):
        return 0
    return int(sum(counts.get(state_key, {}).values()))


def _candidate_model_type(model: CandidateModel | None) -> str:
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
    rows: list[dict[str, Any]] = []
    for action in legal:
        success = min(1.0, max(0.0, float(scores[action])))
        support = _action_support(model, state, player_id, action)
        rows.append(
            {
                "action": _action_name(action),
                "candidate_success_probability": success,
                "death_probability": 1.0 - success,
                "round_value_delta": success,
                "sample_count": support,
                "confidence": support / (support + 10.0) if support else 0.0,
                "entropy": 0.0,
                "legal": True,
                "supported": support >= min_support,
            }
        )
    return rows, "simulator_action_value"


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


def _find_moments(report: Mapping[str, Any], *, threshold: float, max_moments: int) -> list[dict[str, Any]]:
    moments: dict[tuple[int, int], dict[str, Any]] = {}
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
        entry = moments.setdefault(
            (round_num, tick),
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
        entry["events"].extend(important_events)
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
    return result[:max_moments]


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
        state = reconstruct_game_state(normalized, round_num=round_num, tick=decision_tick)
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
                "estimated_regret": regret,
                "decision_class": classification,
            }
        )
    classes = defaultdict(int)
    for item in output_moments:
        classes[str(item["decision_class"])] += 1
    return {
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
        "summary": {
            "moment_count": len(output_moments),
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


def load_candidate_model(path: str | Path) -> CandidateModel:
    """Load the simulator-trained action scorer, with statistical fallback."""

    candidate_path = Path(path)
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
    parser.add_argument("--min-support", type=int, default=5)
    parser.add_argument("--recommendation-margin", type=float, default=0.05)
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
    candidate = load_candidate_model(args.candidate_model) if args.candidate_model else None
    result = build_replay_analysis(
        selected,
        runtime,
        candidate_model=candidate,
        config=HarnessConfig(
            moment_threshold=args.moment_threshold,
            max_moments=args.max_moments,
            min_support=args.min_support,
            recommendation_margin=args.recommendation_margin,
            sample_every=args.sample_every,
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], sort_keys=True))
    print(f"[analysis] moments={len(result['moments'])} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

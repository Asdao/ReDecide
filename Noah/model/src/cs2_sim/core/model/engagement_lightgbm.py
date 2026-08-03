"""Optional compact LightGBM heads for engagement outcomes.

The statistical :class:`EngagementModel` remains the safe fallback.  This
module only imports LightGBM when a booster is trained or loaded, allowing the
small runtime to analyse replays without the native dependency installed.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cs2_sim.action_vocabulary import ACTION_FEATURE_NAMES, action_features

ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION = "engagement_lightgbm_v3"
ENGAGEMENT_LGBM_FEATURE_NAMES_V1 = (
    "horizon_seconds",
    "damage_health",
    "damage_armor",
    "distance",
    "attacker_health",
    "attacker_armor",
    "victim_health",
    "victim_armor",
    "headshot",
    "through_smoke",
    "map_code",
    "side_code",
    "role_code",
)
ENGAGEMENT_LGBM_FEATURE_NAMES_V2 = ENGAGEMENT_LGBM_FEATURE_NAMES_V1 + (
    "action_move",
    "decision_lead_seconds",
    "lookback_seconds",
    "history_sample_count",
    "distance_moved",
    "average_speed",
    "displacement",
    "zone_changes",
    "health",
    "armor",
    "health_delta",
    "armor_delta",
    "inventory_size",
    "has_defuser",
    "recent_damage_dealt",
    "recent_damage_taken",
    "alive_teammates",
    "alive_enemies",
    "nearest_teammate_distance",
    "nearest_enemy_distance",
    "zone_code",
)
ENGAGEMENT_LGBM_FEATURE_NAMES = ENGAGEMENT_LGBM_FEATURE_NAMES_V2 + ACTION_FEATURE_NAMES + (
    "action_target_zone_code",
    "action_utility_code",
    "action_confidence",
)
ENGAGEMENT_TARGETS = ("kill", "death", "trade", "survival", "damage", "round_win")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _code(value: Any) -> float:
    digest = hashlib.blake2b(str(value or "unknown").encode(), digest_size=4).digest()
    return float(int.from_bytes(digest, "big") % 100_000)


def engagement_feature_vector(
    row: Mapping[str, Any],
    feature_names: tuple[str, ...] = ENGAGEMENT_LGBM_FEATURE_NAMES,
) -> list[float]:
    features = row.get("features")
    features = features if isinstance(features, Mapping) else {}
    observed_action = str(row.get("observed_action") or "").lower()
    observed_parameters = row.get("observed_action_parameters")
    observed_parameters = observed_parameters if isinstance(observed_parameters, Mapping) else {}
    values = {
        "horizon_seconds": _number(row.get("horizon_seconds"), 2.0),
        "damage_health": _number(features.get("damage_health")),
        "damage_armor": _number(features.get("damage_armor")),
        "distance": _number(features.get("distance")),
        "attacker_health": _number(features.get("attacker_health")),
        "attacker_armor": _number(features.get("attacker_armor")),
        "victim_health": _number(features.get("victim_health")),
        "victim_armor": _number(features.get("victim_armor")),
        "headshot": float(bool(features.get("headshot"))),
        "through_smoke": float(bool(features.get("through_smoke"))),
        "map_code": _code(row.get("map_name")),
        "side_code": _code(row.get("side")),
        "role_code": _code(row.get("role")),
        "action_move": float(observed_action == "move" or observed_action.startswith("move_to_")),
        "decision_lead_seconds": _number(row.get("decision_lead_seconds")),
        "lookback_seconds": _number(features.get("lookback_seconds")),
        "history_sample_count": _number(features.get("history_sample_count")),
        "distance_moved": _number(features.get("distance_moved")),
        "average_speed": _number(features.get("average_speed")),
        "displacement": _number(features.get("displacement")),
        "zone_changes": _number(features.get("zone_changes")),
        "health": _number(features.get("health")),
        "armor": _number(features.get("armor")),
        "health_delta": _number(features.get("health_delta")),
        "armor_delta": _number(features.get("armor_delta")),
        "inventory_size": _number(features.get("inventory_size")),
        "has_defuser": float(bool(features.get("has_defuser"))),
        "recent_damage_dealt": _number(features.get("recent_damage_dealt")),
        "recent_damage_taken": _number(features.get("recent_damage_taken")),
        "alive_teammates": _number(features.get("alive_teammates")),
        "alive_enemies": _number(features.get("alive_enemies")),
        "nearest_teammate_distance": _number(features.get("nearest_teammate_distance")),
        "nearest_enemy_distance": _number(features.get("nearest_enemy_distance")),
        "zone_code": _code(features.get("zone")),
    }
    values.update(action_features(observed_action))
    values.update(
        {
            "action_target_zone_code": _code(
                observed_parameters.get("target_zone")
                or row.get("observed_action_destination")
            ),
            "action_utility_code": _code(observed_parameters.get("utility_type")),
            "action_confidence": _number(row.get("observed_action_confidence")),
        }
    )
    return [values[name] for name in feature_names]


class EngagementLightGBMBundle:
    """Load and score independently trained compact binary target heads."""

    def __init__(self, boosters: Mapping[str, Any], *, feature_names: tuple[str, ...] = ENGAGEMENT_LGBM_FEATURE_NAMES) -> None:
        if tuple(feature_names) not in {
            ENGAGEMENT_LGBM_FEATURE_NAMES,
            ENGAGEMENT_LGBM_FEATURE_NAMES_V2,
            ENGAGEMENT_LGBM_FEATURE_NAMES_V1,
        }:
            raise ValueError("engagement LightGBM feature schema does not match")
        self.boosters = dict(boosters)
        self.feature_names = tuple(feature_names)

    @property
    def available_targets(self) -> tuple[str, ...]:
        return tuple(sorted(self.boosters))

    def predict_dict(self, row: Mapping[str, Any]) -> dict[str, float]:
        vector = engagement_feature_vector(row, self.feature_names)
        return {
            target: float(booster.predict([vector])[0])
            for target, booster in self.boosters.items()
        }

    def save(self, path: str | Path) -> None:
        payload = {
            "schema_version": ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION,
            "feature_names": list(self.feature_names),
            "targets": {target: booster.model_to_string() for target, booster in self.boosters.items()},
        }
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.part")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(destination)

    @classmethod
    def load(cls, path: str | Path) -> EngagementLightGBMBundle:
        try:
            import lightgbm as lgb
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise RuntimeError("LightGBM is not installed") from exc
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if payload.get("schema_version") not in {
            "engagement_lightgbm_v1",
            "engagement_lightgbm_v2",
            ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION,
        }:
            raise ValueError("unsupported engagement LightGBM schema")
        names = tuple(payload.get("feature_names") or ())
        if names not in {
            ENGAGEMENT_LGBM_FEATURE_NAMES,
            ENGAGEMENT_LGBM_FEATURE_NAMES_V2,
            ENGAGEMENT_LGBM_FEATURE_NAMES_V1,
        }:
            raise ValueError("engagement LightGBM feature schema does not match")
        targets = payload.get("targets") or {}
        boosters = {str(target): lgb.Booster(model_str=str(model)) for target, model in targets.items()}
        return cls(boosters, feature_names=names)


__all__ = [
    "ENGAGEMENT_LGBM_FEATURE_NAMES",
    "ENGAGEMENT_LGBM_FEATURE_NAMES_V2",
    "ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION",
    "ENGAGEMENT_TARGETS",
    "EngagementLightGBMBundle",
    "engagement_feature_vector",
]

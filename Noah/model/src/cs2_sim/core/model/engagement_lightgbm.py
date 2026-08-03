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

ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION = "engagement_lightgbm_v1"
ENGAGEMENT_LGBM_FEATURE_NAMES = (
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
ENGAGEMENT_TARGETS = ("kill", "death", "trade")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def _code(value: Any) -> float:
    digest = hashlib.blake2b(str(value or "unknown").encode(), digest_size=4).digest()
    return float(int.from_bytes(digest, "big") % 100_000)


def engagement_feature_vector(row: Mapping[str, Any]) -> list[float]:
    features = row.get("features")
    features = features if isinstance(features, Mapping) else {}
    return [
        _number(row.get("horizon_seconds"), 2.0),
        _number(features.get("damage_health")),
        _number(features.get("damage_armor")),
        _number(features.get("distance")),
        _number(features.get("attacker_health")),
        _number(features.get("attacker_armor")),
        _number(features.get("victim_health")),
        _number(features.get("victim_armor")),
        float(bool(features.get("headshot"))),
        float(bool(features.get("through_smoke"))),
        _code(row.get("map_name")),
        _code(row.get("side")),
        _code(row.get("role")),
    ]


class EngagementLightGBMBundle:
    """Load and score independently trained compact binary target heads."""

    def __init__(self, boosters: Mapping[str, Any], *, feature_names: tuple[str, ...] = ENGAGEMENT_LGBM_FEATURE_NAMES) -> None:
        if tuple(feature_names) != ENGAGEMENT_LGBM_FEATURE_NAMES:
            raise ValueError("engagement LightGBM feature schema does not match")
        self.boosters = dict(boosters)
        self.feature_names = tuple(feature_names)

    @property
    def available_targets(self) -> tuple[str, ...]:
        return tuple(sorted(self.boosters))

    def predict_dict(self, row: Mapping[str, Any]) -> dict[str, float]:
        vector = engagement_feature_vector(row)
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
        if payload.get("schema_version") != ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION:
            raise ValueError("unsupported engagement LightGBM schema")
        names = tuple(payload.get("feature_names") or ())
        if names != ENGAGEMENT_LGBM_FEATURE_NAMES:
            raise ValueError("engagement LightGBM feature schema does not match")
        targets = payload.get("targets") or {}
        boosters = {str(target): lgb.Booster(model_str=str(model)) for target, model in targets.items()}
        return cls(boosters, feature_names=names)


__all__ = [
    "ENGAGEMENT_LGBM_FEATURE_NAMES",
    "ENGAGEMENT_LIGHTGBM_SCHEMA_VERSION",
    "ENGAGEMENT_TARGETS",
    "EngagementLightGBMBundle",
    "engagement_feature_vector",
]

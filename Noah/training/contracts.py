"""Versioned contracts shared by extraction, training, and runtime reports.

These lightweight structures keep the boundary between replay parsing and
model inference explicit.  They intentionally contain no pandas/LightGBM
dependency, so a user upload can be validated in the small runtime package.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cs2_sim.core.model import FEATURE_NAMES, REPLAY_FEATURE_NAMES, snapshot_features

CONTRACT_SCHEMA_VERSION = "feature_contracts_v1"
SNAPSHOT_FEATURE_SCHEMA_VERSION = 2
ENGAGEMENT_FEATURE_SCHEMA_VERSION = "engagement_features_v3"
CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION = "candidate_action_features_v1"


@dataclass(frozen=True, slots=True)
class FieldSpec:
    """Document one model field and whether it is safe before an event."""

    name: str
    value_type: str
    available_at_prediction: bool
    default: Any
    minimum: float | None = None
    maximum: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.value_type,
            "available_at_prediction": self.available_at_prediction,
            "default": self.default,
            "minimum": self.minimum,
            "maximum": self.maximum,
        }


SNAPSHOT_FIELD_SPECS = tuple(
    FieldSpec(name, "float", True, 0.0) for name in REPLAY_FEATURE_NAMES
)
ENGAGEMENT_FIELD_SPECS = (
    FieldSpec("horizon_seconds", "float", True, 2.0, 0.001, 60.0),
    FieldSpec("observed_action", "string", True, "unknown"),
    FieldSpec("observed_action_family", "string", True, "unknown"),
    FieldSpec("observed_action_parameters", "object", True, {}),
    FieldSpec("observed_action_confidence", "float", True, 0.0, 0.0, 1.0),
    FieldSpec("decision_lead_seconds", "float", True, 1.0, 0.0, 10.0),
    FieldSpec("anchor_kind", "string", True, "unknown"),
    FieldSpec("weapon", "string", True, "unknown"),
    FieldSpec("damage_health", "float", True, 0.0, 0.0, 200.0),
    FieldSpec("damage_armor", "float", True, 0.0, 0.0, 200.0),
    FieldSpec("distance", "float", True, 0.0, 0.0, 10000.0),
    FieldSpec("attacker_health", "float", True, 0.0, 0.0, 100.0),
    FieldSpec("victim_health", "float", True, 0.0, 0.0, 100.0),
    FieldSpec("lookback_seconds", "float", True, 3.0, 0.001, 30.0),
    FieldSpec("history_sample_count", "float", True, 0.0, 0.0, None),
    FieldSpec("distance_moved", "float", True, 0.0, 0.0, None),
    FieldSpec("average_speed", "float", True, 0.0, 0.0, None),
    FieldSpec("displacement", "float", True, 0.0, 0.0, None),
    FieldSpec("zone_changes", "float", True, 0.0, 0.0, None),
    FieldSpec("health", "float", True, 0.0, 0.0, 100.0),
    FieldSpec("armor", "float", True, 0.0, 0.0, 100.0),
    FieldSpec("health_delta", "float", True, 0.0, -100.0, 100.0),
    FieldSpec("armor_delta", "float", True, 0.0, -100.0, 100.0),
    FieldSpec("inventory_size", "float", True, 0.0, 0.0, None),
    FieldSpec("has_defuser", "boolean", True, False),
    FieldSpec("recent_damage_dealt", "float", True, 0.0, 0.0, None),
    FieldSpec("recent_damage_taken", "float", True, 0.0, 0.0, None),
    FieldSpec("alive_teammates", "float", True, 0.0, 0.0, 4.0),
    FieldSpec("alive_enemies", "float", True, 0.0, 0.0, 5.0),
    FieldSpec("nearest_teammate_distance", "float", True, 0.0, 0.0, None),
    FieldSpec("nearest_enemy_distance", "float", True, 0.0, 0.0, None),
    FieldSpec("zone", "string", True, "unknown"),
)
CANDIDATE_ACTION_FIELD_SPECS = tuple(
    FieldSpec(name, "float", True, 0.0) for name in FEATURE_NAMES
)


def _finite(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("feature values must be finite")
    return number


@dataclass(frozen=True, slots=True)
class SnapshotFeatures:
    """Canonical ordered full-match feature vector."""

    values: Mapping[str, float]
    schema_version: int = SNAPSHOT_FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != SNAPSHOT_FEATURE_SCHEMA_VERSION:
            raise ValueError(f"unsupported snapshot feature schema: {self.schema_version}")
        missing = [name for name in REPLAY_FEATURE_NAMES if name not in self.values]
        unknown = [name for name in self.values if name not in REPLAY_FEATURE_NAMES]
        if missing or unknown:
            raise ValueError(f"snapshot feature names differ; missing={missing[:3]} unknown={unknown[:3]}")
        object.__setattr__(self, "values", {name: _finite(self.values[name]) for name in REPLAY_FEATURE_NAMES})

    @classmethod
    def from_snapshot(cls, snapshot: Mapping[str, Any]) -> SnapshotFeatures:
        vector = snapshot_features(snapshot)
        return cls(dict(zip(REPLAY_FEATURE_NAMES, vector, strict=True)))

    def vector(self) -> list[float]:
        return [self.values[name] for name in REPLAY_FEATURE_NAMES]

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "features": dict(self.values)}


@dataclass(frozen=True, slots=True)
class EngagementFeatures:
    """Pre-event engagement fields, with outcome labels excluded."""

    values: Mapping[str, Any]
    schema_version: str = ENGAGEMENT_FEATURE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != ENGAGEMENT_FEATURE_SCHEMA_VERSION:
            raise ValueError(f"unsupported engagement feature schema: {self.schema_version}")
        if any(str(key).startswith("label_") or str(key) in {"outcome", "kill_tick", "death_tick", "trade_tick", "round_won", "round_value_delta"} for key in self.values):
            raise ValueError("engagement features cannot contain post-event labels")

    @classmethod
    def from_window(cls, row: Mapping[str, Any]) -> EngagementFeatures:
        features = dict(row.get("features") or {})
        features["horizon_seconds"] = row.get("horizon_seconds", 2.0)
        features["observed_action"] = row.get("observed_action", "unknown")
        features["observed_action_family"] = row.get("observed_action_family", "unknown")
        features["observed_action_parameters"] = row.get("observed_action_parameters", {})
        features["observed_action_confidence"] = row.get("observed_action_confidence", 0.0)
        features["decision_lead_seconds"] = row.get("decision_lead_seconds", 1.0)
        return cls(features)

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": self.schema_version, "features": dict(self.values)}


@dataclass(frozen=True, slots=True)
class FullMatchAnalysis:
    """Typed wrapper for the JSON-compatible full-match report."""

    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.payload.get("report_type") != "full_match_timeline":
            raise ValueError("invalid full-match analysis report type")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True, slots=True)
class EngagementAnalysis:
    """Typed wrapper for the JSON-compatible engagement report."""

    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.payload.get("report_type") != "engagement_analysis":
            raise ValueError("invalid engagement analysis report type")

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True, slots=True)
class ModelReleaseManifest:
    """Checksummed component manifest for one deployable release."""

    version: str
    components: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    feature_schema_versions: Mapping[str, str | int] = field(default_factory=dict)
    dataset_manifest: str | None = None
    metrics: str | None = None
    schema_version: str = "model_release_manifest_v1"

    def __post_init__(self) -> None:
        if not self.version or Path(self.version).name != self.version or self.version in {".", ".."}:
            raise ValueError("release version must be one directory name")
        if self.schema_version != "model_release_manifest_v1":
            raise ValueError("unsupported release manifest schema")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "version": self.version,
            "components": {str(key): dict(value) for key, value in self.components.items()},
            "feature_schema_versions": dict(self.feature_schema_versions),
            "dataset_manifest": self.dataset_manifest,
            "metrics": self.metrics,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ModelReleaseManifest:
        if payload.get("schema_version") != "model_release_manifest_v1":
            raise ValueError("unsupported release manifest schema")
        return cls(
            version=str(payload.get("version") or ""),
            components={str(k): dict(v) for k, v in (payload.get("components") or {}).items()},
            feature_schema_versions=dict(payload.get("feature_schema_versions") or {}),
            dataset_manifest=payload.get("dataset_manifest"),
            metrics=payload.get("metrics"),
        )

    def save(self, path: str | Path) -> None:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(f"{destination.name}.part")
        temporary.write_text(json.dumps(self.to_dict(), indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)

    @classmethod
    def load(cls, path: str | Path) -> ModelReleaseManifest:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(payload, Mapping):
            raise TypeError("release manifest must be an object")
        return cls.from_dict(payload)

    def validate(self, root: str | Path, *, require_checksums: bool = False) -> None:
        """Validate component containment and optional byte/checksum metadata."""

        base = Path(root).resolve()
        resolved_components: dict[str, Path] = {}
        for name, metadata in self.components.items():
            value = metadata.get("path")
            if not isinstance(value, str) or not value:
                raise ValueError(f"release component {name!r} has no path")
            component = (base / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
            try:
                component.relative_to(base)
            except ValueError as exc:
                raise ValueError(f"release component escapes bundle: {component}") from exc
            if not component.is_file():
                raise FileNotFoundError(component)
            expected_bytes = metadata.get("bytes")
            expected_hash = metadata.get("sha256")
            if require_checksums and (expected_bytes is None or expected_hash is None):
                raise ValueError(f"release component {name!r} is missing checksums")
            if expected_bytes is not None and int(expected_bytes) != component.stat().st_size:
                raise ValueError(f"release component {name!r} size mismatch")
            if expected_hash is not None:
                digest = hashlib.sha256(component.read_bytes()).hexdigest()
                if str(expected_hash).lower() != digest:
                    raise ValueError(f"release component {name!r} checksum mismatch")
            resolved_components[name] = component

        schema_path = resolved_components.get("feature_schema")
        if schema_path is not None:
            try:
                feature_schema = json.loads(schema_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"could not read release feature schema: {schema_path}") from exc
            if not isinstance(feature_schema, Mapping):
                raise ValueError("release feature schema must be an object")
            sections = {"replay": "snapshot", "engagement": "engagement", "candidate_action": "candidate_action"}
            for version_key, section_name in sections.items():
                expected = self.feature_schema_versions.get(version_key)
                section = feature_schema.get(section_name)
                if expected is None or not isinstance(section, Mapping):
                    continue
                actual = section.get("schema_version")
                if str(actual) != str(expected):
                    raise ValueError(
                        f"release feature schema mismatch for {version_key}: "
                        f"manifest={expected!r}, schema={actual!r}"
                    )


__all__ = [
    "CANDIDATE_ACTION_FEATURE_SCHEMA_VERSION",
    "CANDIDATE_ACTION_FIELD_SPECS",
    "CONTRACT_SCHEMA_VERSION",
    "ENGAGEMENT_FEATURE_SCHEMA_VERSION",
    "ENGAGEMENT_FIELD_SPECS",
    "SNAPSHOT_FEATURE_SCHEMA_VERSION",
    "SNAPSHOT_FIELD_SPECS",
    "EngagementAnalysis",
    "EngagementFeatures",
    "FieldSpec",
    "FullMatchAnalysis",
    "ModelReleaseManifest",
    "SnapshotFeatures",
]

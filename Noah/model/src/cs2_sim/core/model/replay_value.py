"""Deployable Bayesian + LightGBM replay-value ensemble."""

from __future__ import annotations

import hashlib
import json
import math
import os
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping, Sequence
from typing import Any

from .snapshot import SnapshotValueModel


REPLAY_FEATURE_NAMES = (
    "map_code",
    "time_seconds",
    "ct_alive",
    "t_alive",
    "alive_difference",
    "ct_avg_health",
    "t_avg_health",
    "kills_seen",
    "bomb_planted",
    "bomb_site_code",
    "ct_avg_x",
    "ct_avg_y",
    "t_avg_x",
    "t_avg_y",
    "ct_total_health",
    "t_total_health",
    "ct_avg_armor",
    "t_avg_armor",
    "damage_events_seen",
    "shots_seen",
    "utility_events_seen",
    "bomb_time_remaining",
    "ct_avg_z",
    "t_avg_z",
    "ct_norm_x",
    "ct_norm_y",
    "t_norm_x",
    "t_norm_y",
    "map_is_de_ancient",
    "map_is_de_anubis",
    "map_is_de_dust2",
    "map_is_de_inferno",
    "map_is_de_mirage",
    "map_is_de_nuke",
    "map_is_de_overpass",
    "map_is_de_vertigo",
    "bomb_site_is_none",
    "bomb_site_is_a",
    "bomb_site_is_b",
)

MODEL_MANIFEST_VERSION = 2
FEATURE_SCHEMA_VERSION = 2
SUPPORTED_FEATURE_SCHEMA_VERSIONS = frozenset({1, FEATURE_SCHEMA_VERSION})

_MAP_NAMES = tuple(name.removeprefix("map_is_") for name in REPLAY_FEATURE_NAMES if name.startswith("map_is_"))
_BOMB_SITES = tuple(name.removeprefix("bomb_site_is_") for name in REPLAY_FEATURE_NAMES if name.startswith("bomb_site_is_"))
_HASH_CHUNK_SIZE = 1024 * 1024


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _code(value: Any) -> float:
    digest = hashlib.blake2b(str(value or "unknown").encode(), digest_size=4).digest()
    return float(int.from_bytes(digest, "big") % 100_000)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_manifest_path(manifest_path: Path, value: str | Path) -> Path:
    """Resolve a component path relative to its manifest, including v1 paths.

    Early manifests were generated with ``models/foo`` while themselves being
    stored in ``models/``.  The second candidate preserves those releases while
    the first candidate is the unambiguous v2 behavior.
    """

    component = Path(value).expanduser()
    if component.is_absolute():
        return component.resolve()
    relative = (manifest_path.parent / component).resolve()
    if relative.exists():
        return relative
    legacy = (manifest_path.parent.parent / component).resolve()
    if legacy.exists():
        return legacy
    return relative


def _verify_component_checksum(
    component: Path,
    metadata: Mapping[str, Any] | None,
    name: str,
    *,
    allow_fallback: bool,
) -> bool:
    """Validate optional bytes/hash metadata, returning whether it is usable."""

    if not metadata:
        return True
    expected_bytes = metadata.get("bytes")
    if expected_bytes is not None and int(expected_bytes) != component.stat().st_size:
        if allow_fallback:
            return False
        raise ValueError(
            f"{name} model component size mismatch: expected {expected_bytes}, "
            f"got {component.stat().st_size} ({component})"
        )
    expected_hash = metadata.get("sha256")
    if expected_hash is not None and str(expected_hash).lower() != _sha256_file(component):
        if allow_fallback:
            return False
        raise ValueError(f"{name} model component checksum mismatch: {component}")
    return True


def snapshot_features(snapshot: Mapping[str, Any]) -> list[float]:
    """Build the ordered vector used by the full replay trainer.

    Keeping this conversion at the runtime boundary is important: callers may
    pass a canonical/enriched snapshot, but the booster must always receive
    exactly the feature order recorded in the manifest.
    """

    ct_alive = int(snapshot.get("ct_alive") or 0)
    t_alive = int(snapshot.get("t_alive") or 0)
    map_name = str(snapshot.get("map_name") or "unknown")
    bomb_site = str(snapshot.get("bomb_site") or "none").lower()
    values = [
        _code(snapshot.get("map_name")),
        _number(snapshot.get("elapsed_seconds")),
        float(ct_alive),
        float(t_alive),
        float(ct_alive - t_alive),
        _number(snapshot.get("ct_avg_health"), 100.0),
        _number(snapshot.get("t_avg_health"), 100.0),
        float(snapshot.get("kills_seen") or 0),
        float(bool(snapshot.get("bomb_planted"))),
        _code(snapshot.get("bomb_site")),
        _number(snapshot.get("ct_avg_x")),
        _number(snapshot.get("ct_avg_y")),
        _number(snapshot.get("t_avg_x")),
        _number(snapshot.get("t_avg_y")),
        _number(snapshot.get("ct_total_health")),
        _number(snapshot.get("t_total_health")),
        _number(snapshot.get("ct_avg_armor")),
        _number(snapshot.get("t_avg_armor")),
        _number(snapshot.get("damage_events_seen")),
        _number(snapshot.get("shots_seen")),
        _number(snapshot.get("utility_events_seen")),
        _number(snapshot.get("bomb_time_remaining")),
        _number(snapshot.get("ct_avg_z")),
        _number(snapshot.get("t_avg_z")),
        _number(snapshot.get("ct_norm_x")),
        _number(snapshot.get("ct_norm_y")),
        _number(snapshot.get("t_norm_x")),
        _number(snapshot.get("t_norm_y")),
    ]
    values.extend(float(map_name == name) for name in _MAP_NAMES)
    values.extend(float(bomb_site == name) for name in _BOMB_SITES)
    return values


@dataclass(frozen=True, slots=True)
class ReplayValuePrediction:
    probability: float
    sample_count: int
    uncertainty: float
    bayesian_probability: float | None
    booster_probability: float | None
    calibrated: bool


class ReplayValueEnsemble:
    """Runtime scorer with a safe Bayesian fallback when LightGBM is absent."""

    def __init__(
        self,
        *,
        bayesian: SnapshotValueModel | None = None,
        booster: Any | None = None,
        booster_weight: float = 0.8,
        calibrator: Any | None = None,
        feature_names: tuple[str, ...] = REPLAY_FEATURE_NAMES,
    ) -> None:
        if not 0.0 <= booster_weight <= 1.0:
            raise ValueError("booster_weight must be between 0 and 1")
        if tuple(feature_names) != REPLAY_FEATURE_NAMES:
            raise ValueError("replay feature schema does not match this application")
        self.bayesian = bayesian or SnapshotValueModel()
        self.booster = booster
        self.booster_weight = booster_weight
        self.calibrator = calibrator
        self.feature_names = tuple(feature_names)

    @property
    def has_booster(self) -> bool:
        return self.booster is not None

    def _predict_with_features(
        self,
        features: Sequence[float],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> ReplayValuePrediction:
        if len(features) != len(self.feature_names):
            raise ValueError(
                f"expected {len(self.feature_names)} replay features, got {len(features)}"
            )
        canonical_snapshot = dict(snapshot) if snapshot is not None else None
        bayesian_probability: float | None = None
        if canonical_snapshot is not None:
            bayesian_probability = self.bayesian.predict_ct_win(canonical_snapshot)
        booster_probability: float | None = None
        if self.booster is not None:
            prediction = self.booster.predict([list(features)])
            booster_probability = float(prediction[0] if hasattr(prediction, "__getitem__") else prediction)
        if booster_probability is None and bayesian_probability is None:
            raise ValueError("a canonical snapshot is required when no booster is loaded")
        if booster_probability is None:
            assert bayesian_probability is not None
            probability = bayesian_probability
        elif bayesian_probability is None:
            probability = booster_probability
        else:
            probability = (
                self.booster_weight * booster_probability
                + (1.0 - self.booster_weight) * bayesian_probability
            )
        calibrated = self.calibrator is not None
        if self.calibrator is not None:
            probability = float(self.calibrator.predict([probability])[0])
        probability = min(1.0, max(0.0, probability))
        sample_count = self.bayesian.sample_count(canonical_snapshot) if canonical_snapshot is not None else 0
        uncertainty = 1.0 / math.sqrt(sample_count + 1.0)
        return ReplayValuePrediction(
            probability=probability,
            sample_count=sample_count,
            uncertainty=uncertainty,
            bayesian_probability=bayesian_probability,
            booster_probability=booster_probability,
            calibrated=calibrated,
        )

    def predict(
        self,
        snapshot: Mapping[str, Any],
        *,
        features: Sequence[float] | None = None,
    ) -> ReplayValuePrediction:
        """Predict from a canonical/enriched snapshot.

        ``features`` can be supplied by a shared feature builder to avoid
        rebuilding a vector.  When omitted, the vector is built with
        :func:`snapshot_features`.
        """

        vector = snapshot_features(snapshot) if features is None else features
        return self._predict_with_features(vector, snapshot=snapshot)

    def predict_features(
        self,
        features: Sequence[float],
        *,
        snapshot: Mapping[str, Any] | None = None,
    ) -> ReplayValuePrediction:
        """Predict directly from an ordered model vector.

        A snapshot is optional when a booster is available.  Supplying it is
        recommended because it enables the Bayesian component and its
        uncertainty estimate; direct-vector mode is useful for services that
        already validated/canonicalized model inputs.
        """

        return self._predict_with_features(features, snapshot=snapshot)

    def predict_ct_win(self, snapshot: dict[str, Any]) -> float:
        return self.predict(snapshot).probability

    def save_manifest(
        self,
        path: str | Path,
        *,
        booster_path: str | Path | None = None,
        bayesian_path: str | Path | None = None,
        calibrator_path: str | Path | None = None,
    ) -> None:
        """Write one manifest describing the runtime component files."""

        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)

        def component_metadata(component_path: str | Path | None) -> dict[str, Any] | None:
            if component_path is None:
                return None
            raw = Path(component_path)
            resolved = raw if raw.is_absolute() else (Path.cwd() / raw)
            resolved = resolved.resolve()
            try:
                relative = resolved.relative_to(output.parent.resolve()).as_posix()
            except ValueError:
                # Keep an explicit path for artifacts outside the release dir.
                relative = str(resolved)
            metadata: dict[str, Any] = {"path": relative}
            if resolved.exists() and resolved.is_file():
                metadata["bytes"] = resolved.stat().st_size
                metadata["sha256"] = _sha256_file(resolved)
            return metadata

        components = {
            "booster": component_metadata(booster_path),
            "bayesian": component_metadata(bayesian_path),
            "calibrator": component_metadata(calibrator_path),
        }
        manifest = {
            "manifest_version": MODEL_MANIFEST_VERSION,
            "version": MODEL_MANIFEST_VERSION,
            "schema_version": FEATURE_SCHEMA_VERSION,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_names": list(self.feature_names),
            "booster_weight": self.booster_weight,
            "booster": components["booster"]["path"] if components["booster"] else None,
            "bayesian": components["bayesian"]["path"] if components["bayesian"] else None,
            "calibrator": components["calibrator"]["path"] if components["calibrator"] else None,
            "components": components,
        }
        temporary = output.with_name(f"{output.name}.part")
        temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, output)

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        bayesian_path: str | Path | None = None,
        calibrator_path: str | Path | None = None,
        allow_fallback: bool = False,
    ) -> "ReplayValueEnsemble":
        """Load a model manifest independent of the process working directory.

        Component paths are resolved relative to the manifest first.  Legacy
        v1 manifests that included a ``models/`` prefix are also supported.
        Missing, unreadable, incompatible, or checksum-mismatched components
        raise by default; pass ``allow_fallback=True`` only for an explicit
        degraded-mode runtime.
        """

        source = Path(path).expanduser().resolve()
        if not source.exists():
            if allow_fallback:
                return cls()
            raise FileNotFoundError(f"replay model manifest does not exist: {source}")
        manifest: dict[str, Any] = {}
        booster_path: Path | None = source
        if source.suffix.lower() == ".json":
            try:
                payload = json.loads(source.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                if allow_fallback:
                    return cls()
                raise ValueError(f"could not read replay model manifest {source}: {exc}") from exc
            if payload.get("type") == "platt":
                raise ValueError("a calibrator is not a replay-value model manifest")
            if "feature_names" not in payload or "booster" not in payload:
                if allow_fallback:
                    return cls()
                raise ValueError(f"{source} is not a replay-value model manifest")
            manifest = payload

            schema_version = int(manifest.get("feature_schema_version", manifest.get("schema_version", 1)))
            if schema_version not in SUPPORTED_FEATURE_SCHEMA_VERSIONS:
                raise ValueError(
                    f"unsupported replay feature schema version {schema_version}; "
                    f"expected one of {sorted(SUPPORTED_FEATURE_SCHEMA_VERSIONS)}"
                )
            declared_names = tuple(manifest.get("feature_names") or ())
            if declared_names and declared_names != REPLAY_FEATURE_NAMES:
                raise ValueError("replay model feature schema does not match this application")

            components = manifest.get("components")
            if not isinstance(components, dict):
                components = {}

            def component_value(name: str, override: str | Path | None) -> tuple[Path | None, dict[str, Any] | None]:
                metadata = components.get(name)
                metadata = metadata if isinstance(metadata, dict) else None
                value = override if override is not None else (
                    metadata.get("path") if metadata is not None else manifest.get(name)
                )
                if value is None:
                    return None, metadata
                return _resolve_manifest_path(source, value), metadata

            booster_value, booster_metadata = component_value("booster", None)
            bayesian_value, bayesian_metadata = component_value("bayesian", bayesian_path)
            calibrator_value, calibrator_metadata = component_value("calibrator", calibrator_path)
            booster_path = booster_value
            bayesian_path = bayesian_value
            calibrator_path = calibrator_value
        elif not source.is_file():
            if allow_fallback:
                return cls()
            raise FileNotFoundError(f"replay model artifact does not exist: {source}")
        else:
            booster_metadata = bayesian_metadata = calibrator_metadata = None
        metadata_path = booster_path.with_suffix(booster_path.suffix + ".json") if booster_path else None
        metadata: dict[str, Any] = {}
        if metadata_path is not None and metadata_path.exists():
            try:
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                if not allow_fallback:
                    raise ValueError(f"could not read model metadata {metadata_path}: {exc}") from exc
        feature_names = tuple(manifest.get("feature_names") or metadata.get("feature_names") or REPLAY_FEATURE_NAMES)
        if feature_names != REPLAY_FEATURE_NAMES:
            raise ValueError("replay model feature schema does not match this application")

        def usable_component(
            component: Path | None,
            component_metadata: dict[str, Any] | None,
            name: str,
        ) -> Path | None:
            if component is None:
                return None
            if not component.exists() or not component.is_file():
                if allow_fallback:
                    return None
                raise FileNotFoundError(f"required {name} model component does not exist: {component}")
            if not _verify_component_checksum(
                component,
                component_metadata,
                name,
                allow_fallback=allow_fallback,
            ):
                return None
            return component

        booster_path = usable_component(booster_path, booster_metadata, "booster")
        bayesian_path = usable_component(bayesian_path, bayesian_metadata, "bayesian")
        calibrator_path = usable_component(calibrator_path, calibrator_metadata, "calibrator")

        bayesian = SnapshotValueModel()
        if bayesian_path is not None:
            try:
                bayesian = SnapshotValueModel.load(bayesian_path)
            except (OSError, KeyError, TypeError, ValueError) as exc:
                if not allow_fallback:
                    raise ValueError(f"could not load Bayesian component {bayesian_path}: {exc}") from exc
        booster = None
        if booster_path is not None:
            try:
                import lightgbm as lgb
            except ImportError as exc:
                if not allow_fallback:
                    raise RuntimeError("LightGBM is required to load the booster component") from exc
            else:
                try:
                    booster = lgb.Booster(model_file=str(booster_path))
                except Exception as exc:
                    if not allow_fallback:
                        raise ValueError(f"could not load booster component {booster_path}: {exc}") from exc
        calibrator = None
        if calibrator_path is not None:
            try:
                from Noah.training.calibration import PlattCalibrator
                calibrator = PlattCalibrator.from_dict(json.loads(calibrator_path.read_text(encoding="utf-8")))
            except (ImportError, OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                if not allow_fallback:
                    raise ValueError(f"could not load calibrator component {calibrator_path}: {exc}") from exc
        if booster is None and bayesian_path is None and not allow_fallback:
            raise ValueError("replay model manifest has no usable model components")
        blend = float(manifest.get("booster_weight", 1.0 - float(metadata.get("small_model_blend", 0.2))))
        return cls(
            bayesian=bayesian,
            booster=booster,
            booster_weight=blend,
            calibrator=calibrator,
            feature_names=feature_names,
        )

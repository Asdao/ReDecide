"""Deployable Bayesian + LightGBM replay-value ensemble."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
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

_MAP_NAMES = tuple(name.removeprefix("map_is_") for name in REPLAY_FEATURE_NAMES if name.startswith("map_is_"))
_BOMB_SITES = tuple(name.removeprefix("bomb_site_is_") for name in REPLAY_FEATURE_NAMES if name.startswith("bomb_site_is_"))


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _code(value: Any) -> float:
    digest = hashlib.blake2b(str(value or "unknown").encode(), digest_size=4).digest()
    return float(int.from_bytes(digest, "big") % 100_000)


def snapshot_features(snapshot: dict[str, Any]) -> list[float]:
    """Build the same 14-column vector used by the full replay trainer."""

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

    def predict(self, snapshot: dict[str, Any]) -> ReplayValuePrediction:
        bayesian_probability = self.bayesian.predict_ct_win(snapshot)
        booster_probability: float | None = None
        if self.booster is not None:
            prediction = self.booster.predict([snapshot_features(snapshot)])
            booster_probability = float(prediction[0] if hasattr(prediction, "__getitem__") else prediction)
        if booster_probability is None:
            probability = bayesian_probability
        else:
            probability = (
                self.booster_weight * booster_probability
                + (1.0 - self.booster_weight) * bayesian_probability
            )
        calibrated = self.calibrator is not None
        if self.calibrator is not None:
            probability = float(self.calibrator.predict([probability])[0])
        probability = min(1.0, max(0.0, probability))
        sample_count = self.bayesian.sample_count(snapshot)
        uncertainty = 1.0 / math.sqrt(sample_count + 1.0)
        return ReplayValuePrediction(
            probability=probability,
            sample_count=sample_count,
            uncertainty=uncertainty,
            bayesian_probability=bayesian_probability,
            booster_probability=booster_probability,
            calibrated=calibrated,
        )

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

        manifest = {
            "version": 1,
            "feature_names": list(self.feature_names),
            "booster_weight": self.booster_weight,
            "booster": str(booster_path) if booster_path else None,
            "bayesian": str(bayesian_path) if bayesian_path else None,
            "calibrator": str(calibrator_path) if calibrator_path else None,
        }
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    @classmethod
    def load(
        cls,
        path: str | Path,
        *,
        bayesian_path: str | Path | None = None,
        calibrator_path: str | Path | None = None,
    ) -> "ReplayValueEnsemble":
        source = Path(path)
        manifest: dict[str, Any] = {}
        booster_path: Path | None = source
        if source.suffix.lower() == ".json":
            payload = json.loads(source.read_text(encoding="utf-8"))
            if payload.get("type") == "platt":
                raise ValueError("a calibrator is not a replay-value model manifest")
            if "feature_names" in payload and "booster" in payload:
                manifest = payload
                booster_value = manifest.get("booster")
                booster_path = Path(booster_value) if booster_value else None
                if booster_path is not None and not booster_path.is_absolute() and not booster_path.exists():
                    booster_path = source.parent / booster_path
                bayesian_path = bayesian_path or manifest.get("bayesian")
                calibrator_path = calibrator_path or manifest.get("calibrator")
                if bayesian_path is not None:
                    bayesian_path = Path(bayesian_path)
                if calibrator_path is not None:
                    calibrator_path = Path(calibrator_path)
        metadata_path = booster_path.with_suffix(booster_path.suffix + ".json") if booster_path else None
        metadata = {}
        if metadata_path is not None and metadata_path.exists():
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        feature_names = tuple(manifest.get("feature_names") or metadata.get("feature_names") or REPLAY_FEATURE_NAMES)
        bayesian = SnapshotValueModel()
        if bayesian_path is not None:
            bayesian_file = Path(bayesian_path)
            if not bayesian_file.is_absolute() and not bayesian_file.exists() and source.suffix.lower() == ".json":
                bayesian_file = source.parent / bayesian_file
            if bayesian_file.exists():
                bayesian = SnapshotValueModel.load(bayesian_file)
        booster = None
        if booster_path is not None and booster_path.exists():
            try:
                import lightgbm as lgb
            except ImportError:
                booster = None
            else:
                booster = lgb.Booster(model_file=str(booster_path))
        calibrator = None
        if calibrator_path is not None:
            calibrator_file = Path(calibrator_path)
            if not calibrator_file.is_absolute() and not calibrator_file.exists() and source.suffix.lower() == ".json":
                calibrator_file = source.parent / calibrator_file
            if calibrator_file.exists():
                from training.calibration import PlattCalibrator

                calibrator = PlattCalibrator.from_dict(json.loads(calibrator_file.read_text(encoding="utf-8")))
        blend = float(manifest.get("booster_weight", 1.0 - float(metadata.get("small_model_blend", 0.2))))
        return cls(
            bayesian=bayesian,
            booster=booster,
            booster_weight=blend,
            calibrator=calibrator,
            feature_names=feature_names,
        )

"""Stable object-oriented interface for runtime model inference."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Any

from .core.model import (
    ActionFrequencyModel,
    ReplayValueEnsemble,
    ReplayValuePrediction,
    ZoneTransitionModel,
)


class ModelError(RuntimeError):
    """Raised when a public model operation cannot be completed."""


@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Runtime artifact selection and fallback policy."""

    releases_dir: Path = Path("model/artifacts/releases")
    version: str | None = None
    manifest_path: Path | None = None
    action_model_path: Path | None = None
    transition_model_path: Path | None = None
    allow_fallback: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "releases_dir", Path(self.releases_dir))
        for field_name in ("manifest_path", "action_model_path", "transition_model_path"):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, Path(value))
        if self.version is not None:
            version_path = Path(self.version)
            if version_path.name != self.version or self.version in {"", ".", ".."}:
                raise ValueError("version must be one directory name")


@dataclass(frozen=True, slots=True)
class ModelStatus:
    release_path: Path
    manifest_path: Path
    has_booster: bool
    has_action_model: bool
    has_transition_model: bool


class ReplayModel:
    """Load and query all deployed replay models without exposing internals."""

    def __init__(
        self,
        ensemble: ReplayValueEnsemble,
        *,
        release_path: Path,
        manifest_path: Path,
        action_model: ActionFrequencyModel | None = None,
        transition_model: ZoneTransitionModel | None = None,
    ) -> None:
        self._ensemble = ensemble
        self._action_model = action_model
        self._transition_model = transition_model
        self._release_path = release_path
        self._manifest_path = manifest_path

    @classmethod
    def load(cls, config: ModelConfig | None = None) -> "ReplayModel":
        """Load an explicit or active release using the configured fallback policy."""

        selected = config or ModelConfig()
        try:
            release = _resolve_release(selected)
            manifest = selected.manifest_path or (release / "full_replay_value.manifest.json")
            action_path = selected.action_model_path or (release / "action_frequency.json")
            transition_path = selected.transition_model_path or (release / "zone_transitions.json")
            ensemble = ReplayValueEnsemble.load(manifest, allow_fallback=selected.allow_fallback)
            action_model = ActionFrequencyModel.load(action_path) if action_path.is_file() else None
            transition_model = ZoneTransitionModel.load(transition_path) if transition_path.is_file() else None
            return cls(
                ensemble,
                release_path=release,
                manifest_path=manifest,
                action_model=action_model,
                transition_model=transition_model,
            )
        except Exception as exc:
            raise ModelError(f"could not load replay model: {exc}") from exc

    @property
    def status(self) -> ModelStatus:
        """Describe which optional runtime components are available."""

        return ModelStatus(
            release_path=self._release_path,
            manifest_path=self._manifest_path,
            has_booster=self._ensemble.has_booster,
            has_action_model=self._action_model is not None,
            has_transition_model=self._transition_model is not None,
        )

    def predict(self, snapshot: Mapping[str, Any]) -> ReplayValuePrediction:
        """Predict CT round-win probability from one canonical snapshot."""

        try:
            return self._ensemble.predict(snapshot)
        except Exception as exc:
            raise ModelError(f"could not predict replay value: {exc}") from exc

    def predict_probability(self, snapshot: Mapping[str, Any]) -> float:
        """Return only the CT round-win probability."""

        return self.predict(snapshot).probability

    def action_probabilities(
        self,
        *,
        map_name: str,
        side: str,
        zone: str,
        legal_actions: Iterable[str],
    ) -> Mapping[str, float]:
        """Score legal movement actions from structured state fields."""

        try:
            model = self._action_model or ActionFrequencyModel()
            return model.score_actions(
                _action_state_key(map_name=map_name, side=side, zone=zone),
                legal_actions,
            )
        except Exception as exc:
            raise ModelError(f"could not score replay actions: {exc}") from exc

    def choose_action(
        self,
        *,
        map_name: str,
        side: str,
        zone: str,
        legal_actions: Iterable[str],
    ) -> str:
        """Choose the highest-probability legal movement action."""

        probabilities = self.action_probabilities(
            map_name=map_name,
            side=side,
            zone=zone,
            legal_actions=legal_actions,
        )
        return max(probabilities, key=lambda action: (probabilities[action], action))

    def zone_probabilities(
        self,
        previous_zone: str,
        *,
        map_name: str,
        side: str,
    ) -> Mapping[str, float]:
        """Return probabilities for the player's next observed zone."""

        try:
            if self._transition_model is None:
                return {previous_zone: 1.0}
            return self._transition_model.probabilities(
                previous_zone,
                side=side,
                map_name=map_name,
            )
        except Exception as exc:
            raise ModelError(f"could not score zone transitions: {exc}") from exc

    def predict_next_zone(self, previous_zone: str, *, map_name: str, side: str) -> str:
        """Return the most likely next observed zone."""

        probabilities = self.zone_probabilities(previous_zone, map_name=map_name, side=side)
        return max(probabilities, key=lambda zone: (probabilities[zone], zone))


def _resolve_release(config: ModelConfig) -> Path:
    if config.manifest_path is not None:
        return config.manifest_path.parent
    root = config.releases_dir
    if config.version is not None:
        return root / config.version
    pointer = root / "current.json"
    if pointer.is_file():
        payload = json.loads(pointer.read_text(encoding="utf-8"))
        version = payload.get("version") if isinstance(payload, dict) else None
        if not isinstance(version, str) or not version:
            raise ValueError(f"active model pointer is invalid: {pointer}")
        return root / version
    v2 = root / "v2"
    return v2 if v2.is_dir() else root


def _action_state_key(*, map_name: str, side: str, zone: str) -> str:
    return "|".join(
        (
            str(map_name or "unknown").lower(),
            str(side or "unknown").lower(),
            str(zone or "unknown"),
        )
    )

"""Stable object-oriented interface for runtime model inference."""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .core.model import (
    ActionFrequencyModel,
    EngagementLightGBMBundle,
    EngagementModel,
    FullLightGBMModel,
    ReplayValueEnsemble,
    ReplayValuePrediction,
    SmallStatisticalModel,
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
    engagement_model_path: Path | None = None
    engagement_lightgbm_path: Path | None = None
    candidate_model_path: Path | None = None
    allow_fallback: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "releases_dir", Path(self.releases_dir))
        for field_name in (
            "manifest_path",
            "action_model_path",
            "transition_model_path",
            "engagement_model_path",
            "engagement_lightgbm_path",
            "candidate_model_path",
        ):
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
    has_engagement_model: bool
    has_engagement_booster: bool
    has_candidate_model: bool


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
        engagement_model: EngagementModel | None = None,
        engagement_booster: EngagementLightGBMBundle | None = None,
        candidate_model: FullLightGBMModel | SmallStatisticalModel | None = None,
    ) -> None:
        self._ensemble = ensemble
        self._action_model = action_model
        self._transition_model = transition_model
        self._engagement_model = engagement_model
        self._engagement_booster = engagement_booster
        self._candidate_model = candidate_model
        self._release_path = release_path
        self._manifest_path = manifest_path

    @classmethod
    def load(cls, config: ModelConfig | None = None) -> ReplayModel:
        """Load an explicit or active release using the configured fallback policy."""

        selected = config or ModelConfig()
        try:
            release = _resolve_release(selected)
            manifest = selected.manifest_path or (release / "full_replay_value.manifest.json")
            action_path = selected.action_model_path or (release / "action_frequency.json")
            transition_path = selected.transition_model_path or (release / "zone_transitions.json")
            engagement_path = selected.engagement_model_path or (release / "engagement_model.json")
            engagement_lightgbm_path = selected.engagement_lightgbm_path or (release / "engagement_lightgbm.json")
            candidate_path = selected.candidate_model_path or (release / "candidate_action_value.txt")
            explicit_engagement_path = selected.engagement_model_path is not None
            explicit_engagement_lightgbm_path = selected.engagement_lightgbm_path is not None
            explicit_candidate_path = selected.candidate_model_path is not None
            release_manifest_path = release / "release_manifest.json"
            if release_manifest_path.is_file():
                from Noah.training.contracts import ModelReleaseManifest

                release_manifest = ModelReleaseManifest.load(release_manifest_path)
                if release_manifest.version != release.name:
                    raise ValueError("release manifest version does not match release directory")
                release_manifest.validate(release, require_checksums=not selected.allow_fallback)
            ensemble = ReplayValueEnsemble.load(manifest, allow_fallback=selected.allow_fallback)
            action_model = ActionFrequencyModel.load(action_path) if action_path.is_file() else None
            transition_model = ZoneTransitionModel.load(transition_path) if transition_path.is_file() else None
            if engagement_path.is_file():
                engagement_model = EngagementModel.load(engagement_path)
            elif explicit_engagement_path and not selected.allow_fallback:
                raise FileNotFoundError(f"configured engagement model does not exist: {engagement_path}")
            else:
                engagement_model = None
            engagement_booster = None
            if engagement_lightgbm_path.is_file():
                try:
                    engagement_booster = EngagementLightGBMBundle.load(engagement_lightgbm_path)
                except (ImportError, RuntimeError, OSError, ValueError, json.JSONDecodeError):
                    # The native LightGBM dependency is optional at runtime;
                    # the statistical artifact remains fully usable.
                    if not selected.allow_fallback:
                        raise
                    engagement_booster = None
            elif explicit_engagement_lightgbm_path and not selected.allow_fallback:
                raise FileNotFoundError(
                    f"configured engagement LightGBM model does not exist: {engagement_lightgbm_path}"
                )
            candidate_model = None
            if candidate_path.is_file():
                try:
                    from Noah.training.analysis_harness import load_candidate_model

                    candidate_model = load_candidate_model(candidate_path)
                except (ImportError, RuntimeError, OSError, ValueError, SyntaxError, json.JSONDecodeError):
                    if not selected.allow_fallback:
                        raise
                    candidate_model = None
            elif (release / "small_statistical.json").is_file():
                if explicit_candidate_path and not selected.allow_fallback:
                    raise FileNotFoundError(f"configured candidate model does not exist: {candidate_path}")
                candidate_model = SmallStatisticalModel.load(release / "small_statistical.json")
            return cls(
                ensemble,
                release_path=release,
                manifest_path=manifest,
                action_model=action_model,
                transition_model=transition_model,
                engagement_model=engagement_model,
                engagement_booster=engagement_booster,
                candidate_model=candidate_model,
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
            has_engagement_model=self._engagement_model is not None,
            has_engagement_booster=self._engagement_booster is not None,
            has_candidate_model=self._candidate_model is not None,
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

    def analyse_match(
        self,
        replay: Mapping[str, Any],
        *,
        sample_every: int = 1,
        include_terminal: bool = True,
        include_other_events: bool = False,
        max_timeline_points: int | None = None,
        top_swing_count: int = 10,
    ) -> dict[str, Any]:
        """Build a deterministic full-match timeline report.

        The reporting implementation remains in the offline training package
        so it can be used without changing the model artifact format.  This
        facade passes itself as the predictor, keeping callers independent of
        LightGBM/Bayesian implementation details.
        """

        try:
            from Noah.training.full_match_report import build_full_match_report

            return build_full_match_report(
                replay,
                model=self,
                sample_every=sample_every,
                include_terminal=include_terminal,
                include_other_events=include_other_events,
                max_timeline_points=max_timeline_points,
                top_swing_count=top_swing_count,
            )
        except Exception as exc:
            raise ModelError(f"could not analyse replay match: {exc}") from exc

    def analyse_replay(
        self,
        replay: Mapping[str, Any],
        *,
        moment_threshold: float = 0.08,
        max_moments: int | None = 25,
        min_support: int = 5,
        recommendation_margin: float = 0.05,
        sample_every: int = 8,
        probability_of_improvement_threshold: float = 0.8,
        expected_regret_threshold: float | None = None,
        credible_level: float = 0.9,
        max_interval_width: float = 0.8,
        posterior_samples: int = 5000,
        posterior_seed: int = 7,
    ) -> dict[str, Any]:
        """Run key-moment and probability-thresholded alternative analysis.

        Legacy ``decision_class`` values remain in the response.  Additive
        ``probability_decision_class`` fields use uncertainty-aware
        probability-of-improvement and expected-regret thresholds; ambiguous
        cases explicitly abstain. ``max_moments=None`` opts into analyzing
        every detected kill/death/bomb moment instead of the default cap.
        """

        try:
            from Noah.training.analysis_harness import (
                HarnessConfig,
                build_replay_analysis,
            )
            from Noah.training.recommendations import (
                ProbabilityLabelThresholds,
                annotate_probability_labels,
            )

            effective_expected_regret = (
                recommendation_margin
                if expected_regret_threshold is None
                else expected_regret_threshold
            )
            report = build_replay_analysis(
                replay,
                self,
                candidate_model=self._candidate_model,
                config=HarnessConfig(
                    moment_threshold=moment_threshold,
                    max_moments=max_moments,
                    min_support=min_support,
                    recommendation_margin=recommendation_margin,
                    sample_every=sample_every,
                    probability_of_improvement_threshold=probability_of_improvement_threshold,
                    expected_regret_threshold=effective_expected_regret,
                    credible_level=credible_level,
                    max_interval_width=max_interval_width,
                    posterior_samples=posterior_samples,
                    posterior_seed=posterior_seed,
                ),
            )
            if report.get("probability_label_schema_version") == "probability_labels_v1":
                return report
            return annotate_probability_labels(
                report,
                thresholds=ProbabilityLabelThresholds(
                    min_support=min_support,
                    probability_of_improvement=probability_of_improvement_threshold,
                    expected_regret=effective_expected_regret,
                    credible_level=credible_level,
                    max_interval_width=max_interval_width,
                    posterior_samples=posterior_samples,
                    seed=posterior_seed,
                ),
            )
        except Exception as exc:
            raise ModelError(f"could not analyse replay decisions: {exc}") from exc

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

    def analyse_engagement(
        self,
        replay: Mapping[str, Any],
        tick: int | None = None,
        player_id: str | None = None,
        *,
        horizon_seconds: Iterable[float] = (1.0, 2.0, 5.0),
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        """Analyse observed player-centric engagement windows.

        The extractor supplies features from the engagement cutoff and labels
        only from the future window.  This method is intentionally descriptive:
        it reports observed outcome probabilities and does not claim a
        counterfactual action was optimal.  If no trained engagement artifact
        is present, a Beta-smoothed statistical prior is used and marked as a
        fallback in the response.
        """

        try:
            from Noah.training.engagement_windows import extract_engagement_windows

            horizons = tuple(float(value) for value in horizon_seconds)
            if not horizons or any(value <= 0 for value in horizons):
                raise ValueError("horizon_seconds must contain positive values")
            if max_rows is not None and max_rows <= 0:
                raise ValueError("max_rows must be positive")
            scorer = self._engagement_model or EngagementModel()
            rows: list[dict[str, Any]] = []
            for horizon in horizons:
                windows = extract_engagement_windows(replay, horizon_seconds=horizon)
                for window in windows:
                    if tick is not None and int(window.get("anchor_tick", -1)) != int(tick):
                        continue
                    if player_id is not None and str(window.get("player_id")) != str(player_id):
                        continue
                    prediction = scorer.predict_dict(window)
                    if self._engagement_booster is not None:
                        booster_prediction = self._engagement_booster.predict_dict(window)
                        blend_weight = (
                            min(0.90, max(0.0, float(prediction.get("confidence", 0.0))))
                            if bool(prediction.get("supported"))
                            else 0.0
                        )
                        for target, value in booster_prediction.items():
                            field = f"{target}_probability"
                            if field in prediction:
                                prediction[field] = (1.0 - blend_weight) * float(prediction[field]) + blend_weight * float(value)
                        prediction["lightgbm_blend_weight"] = blend_weight
                    rows.append(
                        {
                            **window,
                            "prediction": prediction,
                            "model_available": self._engagement_model is not None,
                            "lightgbm_available": self._engagement_booster is not None,
                        }
                    )
                    if max_rows is not None and len(rows) >= max_rows:
                        break
                if max_rows is not None and len(rows) >= max_rows:
                    break
            outcome_counts: dict[str, int] = {}
            for row in rows:
                outcome = str(row.get("outcome") or "none")
                outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1
            header = replay.get("header")
            header = header if isinstance(header, Mapping) else {}
            return {
                "report_type": "engagement_analysis",
                "schema_version": "engagement_analysis_v1",
                "source": str(replay.get("source_path") or replay.get("demo_file") or "unknown"),
                "map_name": str(header.get("map_name") or "unknown"),
                "model_available": self._engagement_model is not None,
                "lightgbm_available": self._engagement_booster is not None,
                "model_type": (
                    "statistical_plus_lightgbm"
                    if self._engagement_booster is not None
                    else "beta_smoothed_engagement"
                    if self._engagement_model is None
                    else "engagement_artifact"
                ),
                "horizons_seconds": list(horizons),
                "filters": {"tick": tick, "player_id": player_id},
                "rows": rows,
                "summary": {"row_count": len(rows), "outcomes": dict(sorted(outcome_counts.items()))},
            }
        except Exception as exc:
            raise ModelError(f"could not analyse engagement: {exc}") from exc

    def score_engagement(self, row: Mapping[str, Any]) -> dict[str, Any]:
        """Score one pre-built decision window, including counterfactual action rows.

        The caller is responsible for supplying leakage-safe history fields.
        Statistical support gates the optional LightGBM blend so an unseen
        action/state cannot be presented as a confident recommendation.
        """

        try:
            scorer = self._engagement_model or EngagementModel()
            prediction = scorer.predict_dict(row)
            if self._engagement_booster is not None:
                booster_prediction = self._engagement_booster.predict_dict(row)
                blend_weight = (
                    min(0.90, max(0.0, float(prediction.get("confidence", 0.0))))
                    if bool(prediction.get("supported"))
                    else 0.0
                )
                for target, value in booster_prediction.items():
                    field = f"{target}_probability"
                    if field in prediction:
                        prediction[field] = (
                            (1.0 - blend_weight) * float(prediction[field])
                            + blend_weight * float(value)
                        )
                prediction["lightgbm_blend_weight"] = blend_weight
            return prediction
        except Exception as exc:
            raise ModelError(f"could not score engagement: {exc}") from exc

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

    def rank_candidate_actions(
        self,
        candidates: Iterable[dict[str, Any]],
        *,
        min_support: int = 5,
        max_entropy: float = 0.95,
    ) -> list[dict[str, Any]]:
        """Rank simulator-generated legal alternatives deterministically."""

        try:
            from Noah.training.recommendations import rank_candidate_actions

            return rank_candidate_actions(
                candidates,
                min_support=min_support,
                max_entropy=max_entropy,
            )
        except Exception as exc:
            raise ModelError(f"could not rank candidate actions: {exc}") from exc

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
        return _resolve_config_path(config.manifest_path).parent
    root = _resolve_config_path(config.releases_dir)
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


def _resolve_config_path(path: Path) -> Path:
    """Resolve configured paths from either the repository root or ``Noah``.

    The packaged source lives under ``Noah/model`` while historical commands
    use ``model/...`` paths.  Prefer the caller's working directory, then the
    package's repository sibling, so default release loading works in both
    layouts without changing explicit absolute paths.
    """

    if path.is_absolute():
        return path
    candidates = (
        Path.cwd() / path,
        Path(__file__).resolve().parents[3] / path,
    )
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _action_state_key(*, map_name: str, side: str, zone: str) -> str:
    return "|".join(
        (
            str(map_name or "unknown").lower(),
            str(side or "unknown").lower(),
            str(zone or "unknown"),
        )
    )

"""Stable object-oriented interface for model training workflows."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.replay_engine.training.build_replay_db import build_database
from backend.replay_engine.training.train_action_models import train_action_models
from backend.replay_engine.training.train_candidate_value import (
    train_candidate_models as train_candidate_value_models,
)
from backend.replay_engine.training.train_full_replay import train as train_replay_value


class TrainingError(RuntimeError):
    """Raised when a public training operation cannot be completed."""


@dataclass(frozen=True, slots=True)
class TrainingConfig:
    """Configuration shared by database preparation and model training."""

    artifact_dir: Path = Path("backend/replay_engine/model/artifacts")
    sample_every: int = 4
    decision_window_seconds: float = 5.0
    action_window_seconds: float = 2.0
    validation_fraction: float = 0.2
    seed: int = 7
    clean_records: bool = False
    allow_event_only: bool = False
    release_version: str | None = None
    tick_rate: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_dir", Path(self.artifact_dir))
        if self.sample_every <= 0:
            raise ValueError("sample_every must be positive")
        if self.decision_window_seconds <= 0:
            raise ValueError("decision_window_seconds must be positive")
        if self.action_window_seconds <= 0:
            raise ValueError("action_window_seconds must be positive")
        if not 0.0 < self.validation_fraction < 1.0:
            raise ValueError("validation_fraction must be between zero and one")
        if self.release_version is not None and not str(self.release_version).strip():
            raise ValueError("release_version must not be empty")
        if self.tick_rate is not None and self.tick_rate <= 0:
            raise ValueError("tick_rate must be positive")


@dataclass(frozen=True, slots=True)
class DatabaseBuildResult:
    database_path: Path
    counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class ReplayTrainingArtifacts:
    booster: Path
    booster_metadata: Path
    bayesian: Path
    calibrator: Path | None
    manifest: Path
    metrics: Path


@dataclass(frozen=True, slots=True)
class ActionTrainingArtifacts:
    action_model: Path
    transition_model: Path
    metrics: Path
    summary: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class CandidateTrainingArtifacts:
    small_model: Path
    full_model: Path | None
    metrics: Path
    summary: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class TrainingRunResult:
    database: DatabaseBuildResult
    replay: ReplayTrainingArtifacts
    actions: ActionTrainingArtifacts | None


class TrainingPipeline:
    """Prepare replay data and train deployable artifacts through one API."""

    def __init__(self, config: TrainingConfig | None = None) -> None:
        self.config = config or TrainingConfig()

    def prepare_database(
        self,
        input_path: str | Path,
        database_path: str | Path,
        *,
        replace: bool = False,
    ) -> DatabaseBuildResult:
        """Build the canonical training database from parsed replay JSONL."""

        source = Path(input_path)
        database = Path(database_path)
        try:
            counts = build_database(
                source,
                database,
                sample_every=self.config.sample_every,
                decision_window_seconds=self.config.decision_window_seconds,
                action_window_seconds=self.config.action_window_seconds,
                replace=replace,
                clean=self.config.clean_records,
            )
            return DatabaseBuildResult(database, counts)
        except Exception as exc:
            raise TrainingError(f"could not build training database from {source}: {exc}") from exc

    def train_replay_model(
        self,
        database_path: str | Path,
        *,
        artifact_dir: str | Path | None = None,
    ) -> ReplayTrainingArtifacts:
        """Train the replay-value ensemble and write one deployable manifest."""

        database = Path(database_path)
        output = Path(artifact_dir) if artifact_dir is not None else self.config.artifact_dir
        booster = output / "full_replay_value.txt"
        booster_metadata = output / "full_replay_value.txt.json"
        bayesian = output / "small_snapshot_value.json"
        calibrator = output / "full_replay_calibrator.json"
        manifest = output / "full_replay_value.manifest.json"
        metrics = output / "full_replay_metrics.json"
        try:
            train_replay_value(
                None,
                booster,
                metrics,
                database_path=database,
                calibrator_path=calibrator,
                manifest_path=manifest,
                snapshot_input=None,
                sample_every=self.config.sample_every,
                decision_window_seconds=self.config.decision_window_seconds,
                # Train a fresh, split-consistent Bayesian artifact for this
                # database run.  An existing artifact is an explicit input
                # only for the streamed workflow.
                small_model_path=None,
                allow_event_only=self.config.allow_event_only,
                seed=self.config.seed,
                validation_fraction=self.config.validation_fraction,
                small_model_output=bayesian,
                verbose=False,
                release_version=self.config.release_version,
                tick_rate=self.config.tick_rate,
            )
            return ReplayTrainingArtifacts(
                booster,
                booster_metadata,
                bayesian,
                calibrator if calibrator.is_file() else None,
                manifest,
                metrics,
            )
        except Exception as exc:
            raise TrainingError(f"could not train replay model from {database}: {exc}") from exc

    def train_action_models(
        self,
        database_path: str | Path,
        *,
        artifact_dir: str | Path | None = None,
    ) -> ActionTrainingArtifacts:
        """Train movement-frequency and zone-transition artifacts."""

        database = Path(database_path)
        output = Path(artifact_dir) if artifact_dir is not None else self.config.artifact_dir
        action_model = output / "action_frequency.json"
        transition_model = output / "zone_transitions.json"
        metrics = output / "action_model_metrics.json"
        try:
            summary = train_action_models(
                None,
                action_model,
                transition_model,
                database_path=database,
                metrics_output=metrics,
            )
            return ActionTrainingArtifacts(action_model, transition_model, metrics, summary)
        except Exception as exc:
            raise TrainingError(f"could not train action models from {database}: {exc}") from exc

    def train_candidate_value_models(
        self,
        candidate_states_path: str | Path,
        rollout_path: str | Path | None = None,
        *,
        labels_path: str | Path | None = None,
        artifact_dir: str | Path | None = None,
        train_full: bool = True,
        max_examples: int | None = None,
    ) -> CandidateTrainingArtifacts:
        """Train support-aware strategic candidate-action models."""

        states = Path(candidate_states_path)
        rollouts = Path(rollout_path) if rollout_path is not None else None
        labels = Path(labels_path) if labels_path is not None else None
        output = Path(artifact_dir) if artifact_dir is not None else self.config.artifact_dir / "candidate"
        try:
            summary = train_candidate_value_models(
                states,
                rollouts,
                output,
                labels_path=labels,
                train_full=train_full,
                max_examples=max_examples,
                seed=self.config.seed,
            )
            full_model = output / "candidate_action_value.txt"
            return CandidateTrainingArtifacts(
                output / "small_statistical.json",
                full_model if full_model.is_file() else None,
                output / "candidate_training_metrics.json",
                summary,
            )
        except Exception as exc:
            raise TrainingError(f"could not train candidate-action models from {states}: {exc}") from exc

    def run(
        self,
        input_path: str | Path,
        database_path: str | Path,
        *,
        replace_database: bool = False,
        include_action_models: bool = True,
        artifact_dir: str | Path | None = None,
    ) -> TrainingRunResult:
        """Run database preparation and all requested training stages."""

        database = self.prepare_database(input_path, database_path, replace=replace_database)
        replay = self.train_replay_model(database.database_path, artifact_dir=artifact_dir)
        actions = (
            self.train_action_models(database.database_path, artifact_dir=artifact_dir)
            if include_action_models
            else None
        )
        return TrainingRunResult(database, replay, actions)

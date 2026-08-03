"""Offline dataset preparation utilities with a stable public facade."""

from .api import (
    ActionTrainingArtifacts,
    DatabaseBuildResult,
    ReplayTrainingArtifacts,
    TrainingConfig,
    TrainingError,
    TrainingPipeline,
    TrainingRunResult,
)
from .full_match_report import (
    analyze_full_match,
    build_full_match_report,
    full_match_report,
)
from .contracts import (
    EngagementAnalysis,
    EngagementFeatures,
    FullMatchAnalysis,
    ModelReleaseManifest,
    SnapshotFeatures,
)

__all__ = [
    "ActionTrainingArtifacts",
    "DatabaseBuildResult",
    "ReplayTrainingArtifacts",
    "TrainingConfig",
    "TrainingError",
    "TrainingPipeline",
    "TrainingRunResult",
    "analyze_full_match",
    "build_full_match_report",
    "full_match_report",
    "EngagementAnalysis",
    "EngagementFeatures",
    "FullMatchAnalysis",
    "ModelReleaseManifest",
    "SnapshotFeatures",
]

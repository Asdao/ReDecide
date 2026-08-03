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
from .contracts import (
    EngagementAnalysis,
    EngagementFeatures,
    FullMatchAnalysis,
    ModelReleaseManifest,
    SnapshotFeatures,
)
from .full_match_report import (
    analyze_full_match,
    build_full_match_report,
    full_match_report,
)


def __getattr__(name: str):
    """Load the optional combined harness lazily to keep ``-m`` execution clean."""

    if name in {"DecisionClass", "HarnessConfig", "build_replay_analysis"}:
        from .analysis_harness import (
            DecisionClass,
            HarnessConfig,
            build_replay_analysis,
        )

        return {
            "DecisionClass": DecisionClass,
            "HarnessConfig": HarnessConfig,
            "build_replay_analysis": build_replay_analysis,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ActionTrainingArtifacts",
    "DatabaseBuildResult",
    "DecisionClass",
    "EngagementAnalysis",
    "EngagementFeatures",
    "FullMatchAnalysis",
    "HarnessConfig",
    "ModelReleaseManifest",
    "ReplayTrainingArtifacts",
    "SnapshotFeatures",
    "TrainingConfig",
    "TrainingError",
    "TrainingPipeline",
    "TrainingRunResult",
    "analyze_full_match",
    "build_full_match_report",
    "build_replay_analysis",
    "full_match_report",
]

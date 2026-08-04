"""Backend adapter for Blackbox's canonical replay extractor.

This module deliberately stops at Blackbox's stable canonical replay types.  The
RE:DECIDE ``DecisionPacket`` does not yet have an executable shared schema, so
packet selection, evidence IDs, and knowledge-boundary filtering belong in the
next adapter layer rather than being invented here....
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from replay_extractor import (
    ExtractorConfig,
    ReplayExtractor,
)
from replay_extractor.models import ReplayRecord
from replay_extractor.segmenter import SegmentedReplay


class _ExtractorFacade(Protocol):
    """Subset of Blackbox's public facade used by this connector."""

    def parse(self, path: str | Path) -> ReplayRecord: ...

    def normalize(self, raw: Mapping[str, Any]) -> ReplayRecord: ...

    def segment(self, replay: ReplayRecord | Mapping[str, Any]) -> SegmentedReplay: ...


class NoahExtractorError(RuntimeError):
    """Stable backend error for replay extraction or normalization failures."""

    def __init__(self, message: str, *, source: str | None = None) -> None:
        super().__init__(message)
        self.source = source


@dataclass(frozen=True, slots=True)
class ExtractedReplay:
    """Canonical replay data returned by the backend-to-Blackbox adapter.

    ``replay`` is Blackbox's normalized record. ``segments`` contains its ordered
    round, event, tick, and heatmap projections for a future decision detector.
    No future-information cutoff is applied by this class yet; that is part of
    the eventual ``DecisionPacket`` exporter.
    """

    replay: ReplayRecord
    segments: SegmentedReplay


class NoahExtractorConnector:
    """Adapt Blackbox's extractor facade to the backend replay boundary."""

    def __init__(
        self,
        config: ExtractorConfig | None = None,
        *,
        extractor: _ExtractorFacade | None = None,
    ) -> None:
        if extractor is not None and config is not None:
            raise ValueError("pass either config or extractor, not both")
        self._extractor = extractor or ReplayExtractor(config)

    def extract(self, path: str | Path) -> ExtractedReplay:
        """Parse, normalize, and segment one replay file.

        Blackbox may use its configured ``.analysis.json`` sidecar fallback.  Any
        parser or segmentation failure is converted into one stable connector
        error for the future API boundary.
        """

        source = Path(path)
        if not source.is_file():
            raise NoahExtractorError(
                f"replay source does not exist or is not a file: {source}",
                source=str(source),
            )
        try:
            replay = self._extractor.parse(source)
            segments = self._extractor.segment(replay)
        except Exception as exc:
            raise NoahExtractorError(
                f"could not extract replay {source}: {exc}",
                source=str(source),
            ) from exc
        return ExtractedReplay(replay=replay, segments=segments)

    def normalize(self, raw: Mapping[str, Any]) -> ExtractedReplay:
        """Normalize and segment an already parsed replay mapping."""

        try:
            replay = self._extractor.normalize(raw)
            segments = self._extractor.segment(replay)
        except Exception as exc:
            raise NoahExtractorError(f"could not normalize replay: {exc}") from exc
        return ExtractedReplay(replay=replay, segments=segments)


__all__ = ["ExtractedReplay", "NoahExtractorConnector", "NoahExtractorError"]

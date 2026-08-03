"""Portable CS2 replay extraction and segmentation package."""

from .api import (
    ExtractorConfig,
    ExtractorError,
    IngestionResult,
    ParseBatchResult,
    ReplayExtractor,
)
from .models import EventRecord, PlayerTick, ReplayRecord, RoundRecord
from .normalize import normalize_record
from .segmenter import SegmentedReplay, segment_replay

__all__ = [
    "EventRecord",
    "ExtractorConfig",
    "ExtractorError",
    "IngestionResult",
    "ParseBatchResult",
    "PlayerTick",
    "ReplayExtractor",
    "ReplayRecord",
    "RoundRecord",
    "SegmentedReplay",
    "normalize_record",
    "segment_replay",
]

"""Stable object-oriented interface for replay extraction."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from .extractor import load_jsonl, parse_demo, parse_directory
from .models import ReplayRecord
from .normalize import normalize_record
from .repository import ReplayRepository
from .segmenter import SegmentedReplay, segment_replay


class ExtractorError(RuntimeError):
    """Raised when a public extraction operation cannot be completed."""


@dataclass(frozen=True, slots=True)
class ExtractorConfig:
    """Configuration shared by all operations on :class:`ReplayExtractor`."""

    tick_interval: int = 32
    tick_rate: float | None = None
    sidecar_fallback: bool = True
    heatmap_cell_size: int = 256

    def __post_init__(self) -> None:
        if self.tick_interval <= 0:
            raise ValueError("tick_interval must be positive")
        if self.tick_rate is not None and self.tick_rate <= 0:
            raise ValueError("tick_rate must be positive when provided")
        if self.heatmap_cell_size <= 0:
            raise ValueError("heatmap_cell_size must be positive")


@dataclass(frozen=True, slots=True)
class ParseBatchResult:
    output_path: Path
    parsed: int
    sidecar_fallbacks: int


@dataclass(frozen=True, slots=True)
class IngestionResult:
    database_path: Path
    ingested: int
    stats: Mapping[str, int]


class ReplayExtractor:
    """Parse, normalize, segment, and store replays through one public API."""

    def __init__(self, config: ExtractorConfig | None = None) -> None:
        self.config = config or ExtractorConfig()

    def parse(self, path: str | Path) -> ReplayRecord:
        """Parse and normalize one native demo into a canonical replay record."""

        source = Path(path)
        try:
            try:
                raw = parse_demo(
                    source,
                    tick_interval=self.config.tick_interval,
                    tick_rate=self.config.tick_rate,
                )
            except Exception as parse_error:
                sidecar = source.with_suffix(".analysis.json")
                if not self.config.sidecar_fallback or not sidecar.is_file():
                    raise
                raw = json.loads(sidecar.read_text(encoding="utf-8"))
                raw["parser"] = "analysis_sidecar"
                raw.setdefault("source_path", source.as_posix())
                raw["parse_warning"] = str(parse_error)
                raw.setdefault("schema_version", 1)
            return normalize_record(raw, default_tick_rate=self.config.tick_rate or 64.0)
        except Exception as exc:
            raise ExtractorError(f"could not parse replay {source}: {exc}") from exc

    def normalize(self, raw: Mapping[str, Any]) -> ReplayRecord:
        """Convert a parser-shaped mapping into the canonical replay model."""

        try:
            return normalize_record(
                dict(raw),
                default_tick_rate=self.config.tick_rate or 64.0,
            )
        except Exception as exc:
            raise ExtractorError(f"could not normalize replay: {exc}") from exc

    def segment(self, replay: ReplayRecord | Mapping[str, Any]) -> SegmentedReplay:
        """Create ordered round, event, tick, and heatmap projections."""

        try:
            canonical = replay if isinstance(replay, ReplayRecord) else self.normalize(replay)
            return segment_replay(canonical, heatmap_cell_size=self.config.heatmap_cell_size)
        except ExtractorError:
            raise
        except Exception as exc:
            raise ExtractorError(f"could not segment replay: {exc}") from exc

    def parse_batch(self, input_dir: str | Path, output_path: str | Path) -> ParseBatchResult:
        """Parse every demo below a directory into one JSONL file."""

        source = Path(input_dir)
        output = Path(output_path)
        try:
            parsed, fallbacks = parse_directory(
                source,
                output,
                tick_interval=self.config.tick_interval,
                tick_rate=self.config.tick_rate,
                sidecar_fallback=self.config.sidecar_fallback,
            )
            return ParseBatchResult(output, parsed, fallbacks)
        except Exception as exc:
            raise ExtractorError(f"could not parse replay directory {source}: {exc}") from exc

    def ingest(self, input_path: str | Path, database_path: str | Path) -> IngestionResult:
        """Normalize and store every JSONL replay in the extractor vault."""

        source = Path(input_path)
        database = Path(database_path)
        repository: ReplayRepository | None = None
        try:
            repository = ReplayRepository(database)
            count = 0
            for raw in load_jsonl(source):
                repository.write(self.segment(raw))
                count += 1
            return IngestionResult(database, count, repository.stats())
        except ExtractorError:
            raise
        except Exception as exc:
            raise ExtractorError(f"could not ingest replay data from {source}: {exc}") from exc
        finally:
            if repository is not None:
                repository.close()

    def stats(self, database_path: str | Path) -> Mapping[str, int]:
        """Return bounded row counts for an extractor vault."""

        database = Path(database_path)
        repository: ReplayRepository | None = None
        try:
            repository = ReplayRepository(database)
            return repository.stats()
        except Exception as exc:
            raise ExtractorError(f"could not inspect replay vault {database}: {exc}") from exc
        finally:
            if repository is not None:
                repository.close()

"""Canonical public/private data locations for the CS2 pipeline.

The repository deliberately keeps redistributable inputs separate from raw
demos, parsed replay data, and user uploads.  The roots can be overridden for
CI or a larger local data volume without changing training code::

    $env:CS2_PUBLIC_DATA_ROOT = "D:/cs2/public"
    $env:CS2_PRIVATE_DATA_ROOT = "D:/cs2/private"

Paths are intentionally relative to the process working directory by default;
this matches the existing command-line workflows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _configured_root(variable: str, default: str) -> Path:
    value = os.environ.get(variable, default).strip()
    return Path(value or default)


@dataclass(frozen=True, slots=True)
class DataPaths:
    """Resolved locations used by download, parsing, training, and testing."""

    public: Path
    private: Path

    @property
    def public_metadata(self) -> Path:
        return self.public / "metadata"

    @property
    def public_processed(self) -> Path:
        return self.public / "processed"

    @property
    def public_maps(self) -> Path:
        return self.public / "maps"

    @property
    def public_benchmark_manifest(self) -> Path:
        return self.public / "benchmark_manifest.json"

    @property
    def public_benchmark_evaluation(self) -> Path:
        return self.public / "benchmark_evaluation.json"

    @property
    def public_dataset_registry(self) -> Path:
        return self.public / "dataset_registry.json"

    @property
    def private_raw_demos(self) -> Path:
        return self.private / "raw_demos"

    @property
    def private_processed(self) -> Path:
        return self.private / "processed"

    @property
    def private_sidecars(self) -> Path:
        return self.private / "sidecars"

    @property
    def private_benchmark_cache(self) -> Path:
        return self.private / "benchmark_cache"

    @property
    def private_databases(self) -> Path:
        return self.private / "databases"

    @property
    def private_features(self) -> Path:
        return self.private / "features"

    @property
    def private_user_uploads(self) -> Path:
        return self.private / "user_uploads"

    @property
    def private_dataset_registry(self) -> Path:
        return self.private / "dataset_registry.json"


def get_data_paths() -> DataPaths:
    """Return the current path configuration, honoring environment overrides."""

    return DataPaths(
        public=_configured_root("CS2_PUBLIC_DATA_ROOT", "data/public"),
        private=_configured_root("CS2_PRIVATE_DATA_ROOT", "data/private"),
    )


DATA_PATHS = get_data_paths()

__all__ = ["DATA_PATHS", "DataPaths", "get_data_paths"]

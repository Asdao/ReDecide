"""Single public entry point for Noah replay analysis."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


def _noah_root() -> Path:
    return Path(__file__).resolve().parent


def _ensure_import_paths() -> None:
    """Make the source checkout usable without caller-managed ``PYTHONPATH``."""

    noah_root = _noah_root()
    for path in (noah_root / "model" / "src", noah_root.parent):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


def load_replay_record(path: str | Path, *, record_index: int = 0) -> dict[str, Any]:
    """Load one replay mapping from a native demo, JSON, or JSONL input."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"replay input does not exist: {source}")
    if source.suffix.lower() == ".dem":
        if record_index != 0:
            raise IndexError("native demo input contains only record index 0")
        _ensure_import_paths()
        from Noah.training.replay_extractor_adapter import parse_extractor_demo

        return parse_extractor_demo(source)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"replay input is empty: {source}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        if not isinstance(payload, (dict, list)):
            raise TypeError("JSON replay input must contain an object or list")
        records = payload if isinstance(payload, list) else [payload]
    if record_index < 0 or record_index >= len(records):
        raise IndexError(f"no replay record at index {record_index}: {source}")
    record = records[record_index]
    if not isinstance(record, dict):
        raise TypeError("selected replay record must be a JSON object")
    return _normalize_replay_record(record)


def _normalize_replay_record(record: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(record)
    if "metadata" in normalized:
        _ensure_import_paths()
        from Noah.training.replay_extractor_adapter import normalize_extractor_record

        return normalize_extractor_record(normalized)
    return normalized


def analyze_replay(
    replay: str | Path | Mapping[str, Any],
    *,
    record_index: int = 0,
    release_dir: str | Path | None = None,
    version: str = "v4",
    candidate_model_path: str | Path | None = None,
    allow_fallback: bool = True,
    model_config: Any | None = None,
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
    """Analyze one replay through the deployed Noah model harness.

    ``replay`` may be a native ``.dem`` path, JSON/JSONL path, canonical
    extractor mapping, or an already-normalized replay mapping. All model
    loading, normalization, candidate scoring, and report construction remain
    behind this function.
    """

    _ensure_import_paths()
    from cs2_sim import ModelConfig, ReplayModel

    if isinstance(replay, Mapping):
        if record_index != 0:
            raise IndexError("a replay mapping contains only record index 0")
        record = _normalize_replay_record(replay)
    else:
        record = load_replay_record(replay, record_index=record_index)

    noah_root = _noah_root()
    releases = (
        Path(release_dir)
        if release_dir is not None
        else noah_root / "model" / "artifacts" / "releases"
    )
    config = model_config
    if config is None:
        config = ModelConfig(
            releases_dir=releases,
            version=version,
            candidate_model_path=(
                Path(candidate_model_path) if candidate_model_path is not None else None
            ),
            allow_fallback=allow_fallback,
        )
    runtime = ReplayModel.load(config)
    return runtime.analyse_replay(
        record,
        moment_threshold=moment_threshold,
        max_moments=max_moments,
        min_support=min_support,
        recommendation_margin=recommendation_margin,
        sample_every=sample_every,
        probability_of_improvement_threshold=probability_of_improvement_threshold,
        expected_regret_threshold=expected_regret_threshold,
        credible_level=credible_level,
        max_interval_width=max_interval_width,
        posterior_samples=posterior_samples,
        posterior_seed=posterior_seed,
    )


__all__ = ["analyze_replay"]

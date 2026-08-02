"""Select compact, high-quality replay sidecars from local Parquet metadata."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

COMPETITIVE_MAPS = {
    "de_ancient",
    "de_anubis",
    "de_dust2",
    "de_inferno",
    "de_mirage",
    "de_nuke",
    "de_overpass",
}


@dataclass(frozen=True)
class SidecarCandidate:
    repo_path: str
    map_name: str
    rounds: int
    kills: int
    stars: int
    match_date: date
    size: int


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def load_candidates(
    metadata_dir: Path,
    *,
    min_rounds: int = 16,
    min_kills: int = 80,
    min_stars: int = 0,
) -> list[SidecarCandidate]:
    """Read valid, complete competitive-map candidates from Parquet files."""

    try:
        import fastparquet
    except ImportError as exc:
        raise RuntimeError(
            "sidecar selection needs fastparquet; install with `pip install .[data]`"
        ) from exc

    parquet_files = sorted(metadata_dir.rglob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"no Parquet metadata found under {metadata_dir}")
    columns = [
        "analysis_file_name",
        "map_name",
        "rounds_count",
        "kills_count",
        "stars",
        "match_date",
        "analysis_bytes",
    ]
    candidates: dict[str, SidecarCandidate] = {}
    for path in parquet_files:
        frame = fastparquet.ParquetFile(path).to_pandas(columns=columns)
        for row in frame.itertuples(index=False):
            repo_path = "" if row.analysis_file_name is None else str(row.analysis_file_name)
            map_name = "" if row.map_name is None else str(row.map_name)
            rounds = _integer(row.rounds_count)
            kills = _integer(row.kills_count)
            stars = _integer(row.stars)
            size = _integer(row.analysis_bytes)
            if (
                not repo_path.endswith(".analysis.json")
                or map_name not in COMPETITIVE_MAPS
                or rounds < min_rounds
                or kills < min_kills
                or stars < min_stars
                or size <= 0
            ):
                continue
            match_date = row.match_date
            if isinstance(match_date, datetime):
                match_date = match_date.date()
            elif not isinstance(match_date, date):
                match_date = date.min
            candidates[repo_path] = SidecarCandidate(
                repo_path=repo_path,
                map_name=map_name,
                rounds=rounds,
                kills=kills,
                stars=stars,
                match_date=match_date,
                size=size,
            )
    return list(candidates.values())


def select_balanced_candidates(
    candidates: list[SidecarCandidate],
    *,
    max_files: int | None = None,
    max_bytes: int | None = None,
) -> list[SidecarCandidate]:
    """Rank within each map, then select round-robin for map diversity."""

    if max_files is not None and max_files <= 0:
        raise ValueError("max_files must be positive")
    if max_bytes is not None and max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    by_map: dict[str, deque[SidecarCandidate]] = defaultdict(deque)
    for candidate in sorted(
        candidates,
        key=lambda item: (
            item.map_name,
            -item.stars,
            -item.match_date.toordinal(),
            -item.rounds,
            item.repo_path,
        ),
    ):
        by_map[candidate.map_name].append(candidate)

    selected: list[SidecarCandidate] = []
    selected_bytes = 0
    map_names = sorted(by_map)
    while map_names and (max_files is None or len(selected) < max_files):
        next_maps: list[str] = []
        for map_name in map_names:
            queue = by_map[map_name]
            if not queue:
                continue
            candidate = queue.popleft()
            if max_bytes is None or selected_bytes + candidate.size <= max_bytes:
                selected.append(candidate)
                selected_bytes += candidate.size
            if queue:
                next_maps.append(map_name)
            if max_files is not None and len(selected) >= max_files:
                break
        map_names = next_maps
    return selected

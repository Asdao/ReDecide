"""Select and download native demos for a sealed, storage-bounded benchmark.

The benchmark is deliberately separate from training.  Candidates come from
the compact Hugging Face metadata Parquet files, while the training database
is used only to exclude demos that were already materialised for training.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sqlite3
from collections import defaultdict, deque
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from Noah.training.download_dataset import DATASET_ID, download_files
from Noah.training.data_paths import DATA_PATHS
from Noah.training.sidecar_catalog import COMPETITIVE_MAPS


SCHEMA_VERSION = 1
DEFAULT_MAX_BYTES = 600_000_000
_HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True, slots=True)
class DemoCandidate:
    repo_path: str
    match_id: str
    map_name: str
    demo_bytes: int
    rounds: int
    kills: int
    stars: int
    match_date: date

    def keys(self) -> set[str]:
        return demo_keys(self.repo_path, self.match_id)


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _date_value(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.min


def _normalise_text(value: Any) -> str:
    return str(value or "").replace("\\", "/").strip().lower()


def demo_keys(*values: Any) -> set[str]:
    """Return path, basename, and stem keys for overlap checks."""

    keys: set[str] = set()
    for value in values:
        text = _normalise_text(value)
        if not text:
            continue
        path = PurePosixPath(text)
        keys.update({text, path.name, path.stem})
    return keys


def load_demo_candidates(metadata_dir: Path) -> list[DemoCandidate]:
    """Load native-demo candidates from the compact metadata Parquet files."""

    try:
        import fastparquet
    except ImportError:
        fastparquet = None
        try:
            import pyarrow.parquet as pyarrow_parquet
        except ImportError as exc:
            raise RuntimeError(
                "benchmark selection needs fastparquet or pyarrow; install with `pip install .[data]`"
            ) from exc

    parquet_files = sorted(metadata_dir.rglob("*.parquet"))
    if not parquet_files:
        raise FileNotFoundError(f"no Parquet metadata found under {metadata_dir}")
    columns = [
        "file_name",
        "match_id",
        "map_name",
        "demo_bytes",
        "rounds_count",
        "kills_count",
        "stars",
        "match_date",
    ]
    candidates: dict[str, DemoCandidate] = {}
    for parquet_file in parquet_files:
        if fastparquet is not None:
            frame = fastparquet.ParquetFile(parquet_file).to_pandas(columns=columns)
        else:
            frame = pyarrow_parquet.read_table(parquet_file, columns=columns).to_pandas()
        for row in frame.itertuples(index=False):
            repo_path = _normalise_text(row.file_name)
            map_name = _normalise_text(row.map_name)
            demo_bytes = _integer(row.demo_bytes)
            if (
                not repo_path.endswith(".dem")
                or map_name not in COMPETITIVE_MAPS
                or demo_bytes <= 0
            ):
                continue
            candidate = DemoCandidate(
                repo_path=repo_path,
                match_id=_normalise_text(row.match_id),
                map_name=map_name,
                demo_bytes=demo_bytes,
                rounds=_integer(row.rounds_count),
                kills=_integer(row.kills_count),
                stars=_integer(row.stars),
                match_date=_date_value(row.match_date),
            )
            candidates[repo_path] = candidate
    return list(candidates.values())


def training_demo_keys(database_path: Path) -> set[str]:
    """Read training replay identities without loading any feature rows."""

    uri = f"file:{database_path.resolve().as_posix()}?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    try:
        rows = connection.execute(
            "SELECT source_path, demo_file, match_id FROM replays"
        ).fetchall()
    finally:
        connection.close()
    keys: set[str] = set()
    for source_path, demo_file, match_id in rows:
        keys.update(demo_keys(source_path, demo_file, match_id))
    return keys


def select_unseen_demos(
    candidates: Iterable[DemoCandidate],
    *,
    excluded_keys: set[str],
    max_files: int = 1,
    max_bytes: int = DEFAULT_MAX_BYTES,
    seed: int = 7,
) -> list[DemoCandidate]:
    """Choose deterministic, map-balanced candidates within the byte budget."""

    if max_files <= 0 or max_bytes <= 0:
        raise ValueError("max_files and max_bytes must be positive")
    by_map: dict[str, deque[DemoCandidate]] = defaultdict(deque)
    for candidate in candidates:
        if candidate.keys() & excluded_keys:
            continue
        by_map[candidate.map_name].append(candidate)
    rng = random.Random(seed)
    for queue in by_map.values():
        values = list(queue)
        rng.shuffle(values)
        values.sort(
            key=lambda item: (
                -item.stars,
                -item.match_date.toordinal(),
                -item.rounds,
                -item.kills,
                item.repo_path,
            )
        )
        queue.clear()
        queue.extend(values)

    selected: list[DemoCandidate] = []
    used_bytes = 0
    map_names = sorted(by_map)
    while map_names and len(selected) < max_files:
        remaining_maps: list[str] = []
        for map_name in map_names:
            queue = by_map[map_name]
            while queue and used_bytes + queue[0].demo_bytes > max_bytes:
                queue.popleft()
            if not queue:
                continue
            candidate = queue.popleft()
            selected.append(candidate)
            used_bytes += candidate.demo_bytes
            if queue:
                remaining_maps.append(map_name)
            if len(selected) >= max_files:
                break
        map_names = remaining_maps
    return selected


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _private_reference(path: Path) -> str | None:
    """Return a portable private-root reference when ``path`` is local data."""

    try:
        relative = path.resolve().relative_to(DATA_PATHS.private.resolve())
    except ValueError:
        return None
    return "private:" + relative.as_posix()


def write_benchmark_manifest(
    manifest_path: Path,
    *,
    output_root: Path,
    selected: Iterable[DemoCandidate],
    training_database: Path,
    dataset_id: str = DATASET_ID,
    revision: str = "main",
) -> dict[str, Any]:
    """Write a manifest only after every selected demo exists locally."""

    entries: list[dict[str, Any]] = []
    root = output_root.resolve()
    for candidate in selected:
        local_path = root / Path(*PurePosixPath(candidate.repo_path).parts)
        if not local_path.is_file():
            raise FileNotFoundError(f"downloaded benchmark demo is missing: {local_path}")
        entries.append(
            {
                **asdict(candidate),
                "match_date": candidate.match_date.isoformat(),
                "local_path": (
                    _private_reference(local_path)
                    or local_path.relative_to(manifest_path.parent.resolve()).as_posix()
                ),
                "bytes": local_path.stat().st_size,
                "sha256": _sha256(local_path),
            }
        )
    if not entries:
        raise ValueError("cannot write an empty benchmark manifest")
    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "type": "held_out_native_demo_benchmark",
        "dataset_id": dataset_id,
        "revision": revision,
        "training_database": (
            _private_reference(training_database)
            or str(training_database.resolve())
        ),
        "training_excluded": True,
        "files": entries,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = manifest_path.with_name(f"{manifest_path.name}.part")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=DATA_PATHS.public_metadata)
    parser.add_argument("--training-database", type=Path, default=DATA_PATHS.private_databases / "cs2_replays_v2.sqlite")
    parser.add_argument("--output", type=Path, default=DATA_PATHS.private_benchmark_cache)
    parser.add_argument("--manifest", type=Path, default=DATA_PATHS.public_benchmark_manifest)
    parser.add_argument("--max-files", type=int, default=1)
    parser.add_argument("--max-gb", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--dataset", default=DATASET_ID)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    max_bytes = int(args.max_gb * 1_000_000_000)
    if max_bytes <= 0:
        raise ValueError("--max-gb must be positive")
    candidates = load_demo_candidates(args.metadata)
    excluded = training_demo_keys(args.training_database)
    selected = select_unseen_demos(
        candidates,
        excluded_keys=excluded,
        max_files=args.max_files,
        max_bytes=max_bytes,
        seed=args.seed,
    )
    if not selected:
        raise ValueError("no unseen demos fit the requested storage budget")
    print(json.dumps([asdict(candidate) for candidate in selected], default=str, indent=2))
    if args.dry_run:
        return 0
    download_files(
        [candidate.repo_path for candidate in selected],
        args.output,
        dataset_id=args.dataset,
        revision=args.revision,
        max_bytes=max_bytes,
    )
    write_benchmark_manifest(
        args.manifest,
        output_root=args.output,
        selected=selected,
        training_database=args.training_database,
        dataset_id=args.dataset,
        revision=args.revision,
    )
    print(f"benchmark manifest written: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

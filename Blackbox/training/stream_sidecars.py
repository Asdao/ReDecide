"""Stream selected replay sidecars into compact snapshot JSONL.

This is the storage-minimal ingestion stage. It keeps only one remote JSON
sidecar in memory at a time, writes compact snapshots incrementally, and does
not persist raw sidecars unless ``--cache-dir`` is supplied.

Example::

    python -m training.stream_sidecars \
        --metadata data/public/metadata \
        --output data/private/processed/analysis_snapshots.jsonl \
        --max-files 500 \
        --max-gb 0.25
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable, Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import Any

from Blackbox.training.download_dataset import (
    DATASET_ID,
    DEFAULT_MAX_BYTES,
    iter_remote_file_chunks,
)
from Blackbox.training.extract_features import extract_snapshots
from Blackbox.training.sidecar_catalog import (
    SidecarCandidate,
    load_candidates,
    select_balanced_candidates,
)

ChunkFetcher = Callable[..., Iterator[bytes]]


def _document_from_chunks(chunks: Iterable[bytes]) -> tuple[dict[str, Any], int]:
    payload = bytearray()
    for chunk in chunks:
        payload.extend(chunk)
    try:
        document = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("downloaded sidecar is not valid JSON") from exc
    if not isinstance(document, dict):
        raise TypeError("downloaded sidecar must contain a JSON object")
    return document, len(payload)


def _cache_document(cache_dir: Path, repo_path: str, payload: bytes) -> None:
    relative = PurePosixPath(repo_path)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe repository path: {repo_path}")
    destination = cache_dir / Path(*relative.parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.name}.part")
    partial.write_bytes(payload)
    partial.replace(destination)


def stream_sidecars_to_snapshots(
    candidates: Iterable[SidecarCandidate],
    output_path: str | Path,
    *,
    dataset_id: str = DATASET_ID,
    revision: str = "main",
    max_bytes: int = DEFAULT_MAX_BYTES,
    cache_dir: str | Path | None = None,
    decision_window_seconds: float = 5.0,
    fetcher: ChunkFetcher = iter_remote_file_chunks,
) -> dict[str, Any]:
    """Stream candidates and write compact snapshots without raw-file storage."""

    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if decision_window_seconds <= 0:
        raise ValueError("decision_window_seconds must be positive")
    selected = list(candidates)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    cache = Path(cache_dir) if cache_dir is not None else None
    partial = output.with_name(f"{output.name}.part")
    downloaded_bytes = 0
    rows_written = 0
    files_processed = 0
    try:
        with partial.open("w", encoding="utf-8") as destination:
            for candidate in selected:
                payload = b"".join(
                    fetcher(
                        candidate.repo_path,
                        dataset_id=dataset_id,
                        revision=revision,
                        max_bytes=max_bytes,
                        already_downloaded=downloaded_bytes,
                    )
                )
                document, size = _document_from_chunks((payload,))
                downloaded_bytes += size
                if cache is not None:
                    _cache_document(cache, candidate.repo_path, payload)
                source = candidate.repo_path
                rows = extract_snapshots(
                    document,
                    source,
                    decision_window_seconds=decision_window_seconds,
                    include_round_start=False,
                    include_round_end=False,
                    include_terminal=False,
                )
                for row in rows:
                    destination.write(json.dumps(row, separators=(",", ":")) + "\n")
                files_processed += 1
                rows_written += len(rows)
                destination.flush()
    except Exception:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(output)
    return {
        "files_selected": len(selected),
        "files_processed": files_processed,
        "bytes_streamed": downloaded_bytes,
        "snapshot_rows": rows_written,
        "output": str(output),
        "cache_dir": str(cache) if cache is not None else None,
    }


def select_and_stream(
    metadata_dir: str | Path,
    output_path: str | Path,
    *,
    max_files: int | None = 500,
    max_bytes: int = DEFAULT_MAX_BYTES,
    min_rounds: int = 16,
    min_kills: int = 80,
    min_stars: int = 0,
    dataset_id: str = DATASET_ID,
    revision: str = "main",
    cache_dir: str | Path | None = None,
    decision_window_seconds: float = 5.0,
) -> dict[str, Any]:
    """Select quality-filtered candidates from metadata and stream them."""

    candidates = load_candidates(
        Path(metadata_dir),
        min_rounds=min_rounds,
        min_kills=min_kills,
        min_stars=min_stars,
    )
    selected = select_balanced_candidates(
        candidates,
        max_files=max_files,
        max_bytes=max_bytes,
    )
    if not selected:
        raise ValueError("no sidecars matched the requested quality filters")
    return stream_sidecars_to_snapshots(
        selected,
        output_path,
        dataset_id=dataset_id,
        revision=revision,
        max_bytes=max_bytes,
        cache_dir=cache_dir,
        decision_window_seconds=decision_window_seconds,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, default=Path("data/public/metadata"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/private/processed/analysis_snapshots.jsonl"),
    )
    parser.add_argument("--cache-dir", type=Path, default=None)
    parser.add_argument("--dataset", default=DATASET_ID)
    parser.add_argument("--revision", default="main")
    parser.add_argument("--max-gb", type=float, default=0.25)
    parser.add_argument("--max-files", type=int, default=500)
    parser.add_argument("--min-rounds", type=int, default=16)
    parser.add_argument("--min-kills", type=int, default=80)
    parser.add_argument("--min-stars", type=int, default=0)
    parser.add_argument("--decision-window-seconds", type=float, default=5.0)
    args = parser.parse_args()
    if args.max_gb <= 0:
        raise ValueError("--max-gb must be positive")
    result = select_and_stream(
        args.metadata,
        args.output,
        max_files=args.max_files,
        max_bytes=int(args.max_gb * 1_000_000_000),
        min_rounds=args.min_rounds,
        min_kills=args.min_kills,
        min_stars=args.min_stars,
        dataset_id=args.dataset,
        revision=args.revision,
        cache_dir=args.cache_dir,
        decision_window_seconds=args.decision_window_seconds,
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["select_and_stream", "stream_sidecars_to_snapshots"]

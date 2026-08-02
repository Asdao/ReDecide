"""Stream selected CS2 dataset files without downloading the full archive.

Examples:

    python -m training.download_dataset metadata --output data/small/metadata
    python -m training.download_dataset list
    python -m training.download_dataset files \
        --file demos/shard-example/match/map.dem \
        --output data/full --max-gb 1

The raw demo files are mirrored by the dataset maintainer from public tournament
sources. Check the source and tournament terms before redistributing them.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Iterable


DATASET_ID = "blanchon/cs2_dataset_demo"
DATASET_API = "https://huggingface.co/api/datasets"
DATASET_RESOLVE = "https://huggingface.co/datasets"
DEFAULT_MAX_BYTES = 1_000_000_000
CHUNK_SIZE = 1024 * 1024


class DownloadLimitError(RuntimeError):
    """Raised when a download would exceed the configured byte budget."""


def _request(url: str) -> urllib.request.Request:
    return urllib.request.Request(
        url,
        headers={"User-Agent": "cs2-sim-dataset-downloader/0.1"},
    )


def list_dataset_files(
    dataset_id: str = DATASET_ID,
    *,
    path_in_repo: str = "data",
) -> list[str]:
    """Return repository file paths from a Hugging Face dataset subtree."""
    encoded_id = urllib.parse.quote(dataset_id, safe="/")
    encoded_path = "/".join(
        urllib.parse.quote(part) for part in PurePosixPath(path_in_repo).parts
    )
    tree_path = f"/tree/main/{encoded_path}" if encoded_path else "/tree/main"
    url = f"{DATASET_API}/{encoded_id}{tree_path}?recursive=true&expand=false"
    files: list[str] = []
    while url:
        try:
            with urllib.request.urlopen(_request(url), timeout=60) as response:
                payload = json.load(response)
                next_url = _next_page_url(response.headers.get("Link"))
        except urllib.error.URLError as exc:
            raise RuntimeError(f"could not list dataset files: {exc}") from exc

        if not isinstance(payload, list):
            raise RuntimeError("dataset listing returned an unexpected response")
        files.extend(
            entry["path"]
            for entry in payload
            if entry.get("type") == "file" and isinstance(entry.get("path"), str)
        )
        url = next_url
    return sorted(files)


def _next_page_url(link_header: str | None) -> str | None:
    """Extract the RFC 5988 `rel=next` URL from a response Link header."""
    if not link_header:
        return None
    for link in link_header.split(","):
        url_part, *parameters = link.split(";")
        if any(parameter.strip() == 'rel="next"' for parameter in parameters):
            return url_part.strip().removeprefix("<").removesuffix(">")
    return None


def _validate_repo_path(repo_path: str) -> PurePosixPath:
    path = PurePosixPath(repo_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"unsafe repository path: {repo_path}")
    return path


def _copy_response(
    response: BinaryIO,
    destination: Path,
    *,
    max_bytes: int,
    already_downloaded: int,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f"{destination.name}.part")
    downloaded = 0
    try:
        with partial.open("wb") as output:
            while chunk := response.read(CHUNK_SIZE):
                downloaded += len(chunk)
                if already_downloaded + downloaded > max_bytes:
                    raise DownloadLimitError(
                        f"download budget exceeded while writing {destination}"
                    )
                output.write(chunk)
        os.replace(partial, destination)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    return downloaded


def download_file(
    repo_path: str,
    output_dir: str | Path,
    *,
    dataset_id: str = DATASET_ID,
    max_bytes: int = DEFAULT_MAX_BYTES,
    already_downloaded: int = 0,
) -> tuple[Path, int]:
    """Download one repository file while enforcing a cumulative byte limit."""
    if max_bytes <= 0 or already_downloaded < 0:
        raise ValueError("byte limits must be non-negative and max_bytes must be positive")
    relative_path = _validate_repo_path(repo_path)
    destination = Path(output_dir).resolve() / Path(*relative_path.parts)
    encoded_id = urllib.parse.quote(dataset_id, safe="/")
    encoded_path = "/".join(urllib.parse.quote(part) for part in relative_path.parts)
    url = f"{DATASET_RESOLVE}/{encoded_id}/resolve/main/{encoded_path}"

    try:
        with urllib.request.urlopen(_request(url), timeout=120) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None and already_downloaded + int(content_length) > max_bytes:
                raise DownloadLimitError(f"{repo_path} is larger than the remaining byte budget")
            size = _copy_response(
                response,
                destination,
                max_bytes=max_bytes,
                already_downloaded=already_downloaded,
            )
    except urllib.error.URLError as exc:
        raise RuntimeError(f"could not download {repo_path}: {exc}") from exc
    return destination, size


def download_files(
    repo_paths: Iterable[str],
    output_dir: str | Path,
    *,
    dataset_id: str = DATASET_ID,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[Path]:
    """Download files sequentially, stopping before the cumulative limit."""
    downloaded = 0
    destinations: list[Path] = []
    for repo_path in repo_paths:
        destination, size = download_file(
            repo_path,
            output_dir,
            dataset_id=dataset_id,
            max_bytes=max_bytes,
            already_downloaded=downloaded,
        )
        destinations.append(destination)
        downloaded += size
        print(f"downloaded {repo_path} ({size:,} bytes)")
    print(f"total downloaded: {downloaded:,} bytes")
    return destinations


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=DATASET_ID, help="Hugging Face dataset id")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="list metadata files")
    list_parser.set_defaults(action="list")

    metadata_parser = subparsers.add_parser("metadata", help="download only Parquet metadata")
    metadata_parser.add_argument(
        "--output",
        default="data/small/metadata",
        help="small compact metadata destination",
    )
    metadata_parser.add_argument("--max-gb", type=float, default=1.0)
    metadata_parser.set_defaults(action="metadata")

    files_parser = subparsers.add_parser("files", help="download explicitly selected files")
    files_parser.add_argument("--file", action="append", required=True, dest="files")
    files_parser.add_argument(
        "--output",
        default="data/full",
        help="full replay/demo destination",
    )
    files_parser.add_argument("--max-gb", type=float, default=1.0)
    files_parser.set_defaults(action="files")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "list":
        for path in list_dataset_files(args.dataset, path_in_repo=""):
            print(path)
        return 0

    max_bytes = int(args.max_gb * 1_000_000_000)
    if max_bytes <= 0:
        raise ValueError("--max-gb must be positive")

    if args.command == "metadata":
        files = [path for path in list_dataset_files(args.dataset) if path.endswith(".parquet")]
        download_files(files, args.output, dataset_id=args.dataset, max_bytes=max_bytes)
    else:
        download_files(args.files, args.output, dataset_id=args.dataset, max_bytes=max_bytes)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DownloadLimitError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

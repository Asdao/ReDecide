"""Stream selected CS2 dataset files without downloading the full archive.

Examples:

    python -m training.download_dataset metadata --output data/public/metadata
    python -m training.download_dataset list
    python -m training.download_dataset files \
        --file demos/shard-example/match/map.dem \
        --output data/private/raw_demos --max-gb 1
    python -m training.download_dataset sidecars --max-files 500
    python -m training.download_dataset locked \
        --manifest training/sidecars_manifest.json

The raw demo files are mirrored by the dataset maintainer from public tournament
sources. Check the source and tournament terms before redistributing them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath
from typing import BinaryIO

from Noah.training.data_paths import DATA_PATHS

DATASET_ID = "blanchon/cs2_dataset_demo"
DATASET_API = "https://huggingface.co/api/datasets"
DATASET_RESOLVE = "https://huggingface.co/datasets"
DEFAULT_MAX_BYTES = 1_000_000_000
CHUNK_SIZE = 1024 * 1024
MANIFEST_VERSION = 1


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
            raise TypeError("dataset listing returned an unexpected response")
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_manifest(
    input_dir: str | Path,
    manifest_path: str | Path,
    *,
    dataset_id: str = DATASET_ID,
    revision: str = "main",
) -> dict[str, object]:
    """Record the exact files in a downloaded dataset subset.

    Paths are stored relative to ``input_dir`` using POSIX separators, so the
    manifest can be used on Windows, macOS, and Linux alike.  The normal
    sidecar directory already contains the repository's ``demos/`` prefix.
    """
    root = Path(input_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"manifest input directory does not exist: {root}")
    files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(".part")
    )
    if not files:
        raise ValueError(f"manifest input directory is empty: {root}")

    entries: list[dict[str, object]] = []
    for path in files:
        relative_path = path.relative_to(root).as_posix()
        _validate_repo_path(relative_path)
        entries.append(
            {
                "path": relative_path,
                "bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "dataset_id": dataset_id,
        "revision": revision,
        "files": entries,
        "total_bytes": sum(int(entry["bytes"]) for entry in entries),
    }
    destination = Path(manifest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f"{destination.name}.part")
    try:
        temporary.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        raise
    return manifest


def load_manifest(manifest_path: str | Path) -> dict[str, object]:
    """Load and validate a locked dataset manifest."""
    try:
        manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"could not read manifest {manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ValueError("unsupported or missing dataset manifest version")
    dataset_id = manifest.get("dataset_id")
    revision = manifest.get("revision", "main")
    files = manifest.get("files")
    if not isinstance(dataset_id, str) or not dataset_id:
        raise ValueError("manifest dataset_id must be a non-empty string")
    if not isinstance(revision, str) or not revision:
        raise ValueError("manifest revision must be a non-empty string")
    if not isinstance(files, list) or not files:
        raise ValueError("manifest files must be a non-empty list")
    validated: list[dict[str, object]] = []
    seen: set[str] = set()
    for entry in files:
        if not isinstance(entry, dict):
            raise TypeError("manifest file entries must be objects")
        repo_path = entry.get("path")
        size = entry.get("bytes")
        digest = entry.get("sha256")
        if not isinstance(repo_path, str) or repo_path in seen:
            raise ValueError(f"manifest contains an invalid or duplicate path: {repo_path}")
        _validate_repo_path(repo_path)
        if not isinstance(size, int) or size < 0:
            raise ValueError(f"manifest has invalid byte count for {repo_path}")
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError(f"manifest has invalid SHA-256 for {repo_path}")
        seen.add(repo_path)
        validated.append({"path": repo_path, "bytes": size, "sha256": digest.lower()})
    manifest["files"] = sorted(validated, key=lambda entry: str(entry["path"]))
    return manifest


def verify_manifest(input_dir: str | Path, manifest_path: str | Path) -> list[str]:
    """Return differences between a local directory and a locked manifest."""
    root = Path(input_dir).resolve()
    manifest = load_manifest(manifest_path)
    entries = manifest["files"]
    assert isinstance(entries, list)
    expected = {str(entry["path"]): entry for entry in entries}
    actual = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file() and not path.name.endswith(".part")
    } if root.is_dir() else {}
    differences: list[str] = []
    for repo_path, entry in expected.items():
        path = actual.get(repo_path)
        if path is None:
            differences.append(f"missing: {repo_path}")
            continue
        expected_bytes = int(entry["bytes"])
        if path.stat().st_size != expected_bytes:
            differences.append(
                f"size mismatch: {repo_path} (expected {expected_bytes}, got {path.stat().st_size})"
            )
            continue
        if _sha256(path) != str(entry["sha256"]).lower():
            differences.append(f"SHA-256 mismatch: {repo_path}")
    for repo_path in sorted(set(actual) - set(expected)):
        differences.append(f"unexpected: {repo_path}")
    return differences


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
    revision: str = "main",
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
    encoded_revision = urllib.parse.quote(revision, safe="")
    url = f"{DATASET_RESOLVE}/{encoded_id}/resolve/{encoded_revision}/{encoded_path}"

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


def iter_remote_file_chunks(
    repo_path: str,
    *,
    dataset_id: str = DATASET_ID,
    revision: str = "main",
    max_bytes: int = DEFAULT_MAX_BYTES,
    already_downloaded: int = 0,
) -> Iterator[bytes]:
    """Yield one remote file in bounded chunks without writing it to disk."""

    if max_bytes <= 0 or already_downloaded < 0:
        raise ValueError("byte limits must be non-negative and max_bytes must be positive")
    relative_path = _validate_repo_path(repo_path)
    encoded_id = urllib.parse.quote(dataset_id, safe="/")
    encoded_path = "/".join(urllib.parse.quote(part) for part in relative_path.parts)
    encoded_revision = urllib.parse.quote(revision, safe="")
    url = f"{DATASET_RESOLVE}/{encoded_id}/resolve/{encoded_revision}/{encoded_path}"
    try:
        with urllib.request.urlopen(_request(url), timeout=120) as response:
            content_length = response.headers.get("Content-Length")
            if content_length is not None and already_downloaded + int(content_length) > max_bytes:
                raise DownloadLimitError(f"{repo_path} is larger than the remaining byte budget")
            downloaded = 0
            while chunk := response.read(CHUNK_SIZE):
                downloaded += len(chunk)
                if already_downloaded + downloaded > max_bytes:
                    raise DownloadLimitError(
                        f"download budget exceeded while streaming {repo_path}"
                    )
                yield chunk
    except urllib.error.URLError as exc:
        raise RuntimeError(f"could not download {repo_path}: {exc}") from exc


def download_files(
    repo_paths: Iterable[str],
    output_dir: str | Path,
    *,
    dataset_id: str = DATASET_ID,
    revision: str = "main",
    max_bytes: int = DEFAULT_MAX_BYTES,
    skip_existing: bool = False,
) -> list[Path]:
    """Download files sequentially, stopping before the cumulative limit."""
    downloaded = 0
    destinations: list[Path] = []
    for repo_path in repo_paths:
        relative_path = _validate_repo_path(repo_path)
        destination = Path(output_dir).resolve() / Path(*relative_path.parts)
        if skip_existing and destination.exists():
            print(f"already present: {repo_path}")
            destinations.append(destination)
            continue
        destination, size = download_file(
            repo_path,
            output_dir,
            dataset_id=dataset_id,
            revision=revision,
            max_bytes=max_bytes,
            already_downloaded=downloaded,
        )
        destinations.append(destination)
        downloaded += size
        print(f"downloaded {repo_path} ({size:,} bytes)")
    print(f"total downloaded: {downloaded:,} bytes")
    return destinations


def download_manifest(
    manifest_path: str | Path,
    output_dir: str | Path,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
) -> list[Path]:
    """Download exactly the files in a manifest and verify every checksum."""
    manifest = load_manifest(manifest_path)
    dataset_id = str(manifest["dataset_id"])
    revision = str(manifest.get("revision", "main"))
    entries = manifest["files"]
    assert isinstance(entries, list)
    downloaded = 0
    destinations: list[Path] = []
    for entry in entries:
        repo_path = str(entry["path"])
        expected_bytes = int(entry["bytes"])
        expected_sha256 = str(entry["sha256"]).lower()
        destination = Path(output_dir).resolve() / Path(*_validate_repo_path(repo_path).parts)
        if destination.exists() and destination.stat().st_size == expected_bytes:
            if _sha256(destination) == expected_sha256:
                print(f"already verified: {repo_path}")
                destinations.append(destination)
                continue
            print(f"checksum changed, re-downloading: {repo_path}")
        destination, size = download_file(
            repo_path,
            output_dir,
            dataset_id=dataset_id,
            revision=revision,
            max_bytes=max_bytes,
            already_downloaded=downloaded,
        )
        if size != expected_bytes or _sha256(destination) != expected_sha256:
            raise RuntimeError(f"checksum verification failed for {repo_path}")
        destinations.append(destination)
        downloaded += size
        print(f"downloaded and verified {repo_path} ({size:,} bytes)")
    print(f"manifest complete: {len(destinations):,} files, {downloaded:,} bytes downloaded")
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
        default=str(DATA_PATHS.public_metadata),
        help="public compact metadata destination",
    )
    metadata_parser.add_argument("--max-gb", type=float, default=1.0)
    metadata_parser.set_defaults(action="metadata")

    files_parser = subparsers.add_parser("files", help="download explicitly selected files")
    files_parser.add_argument("--file", action="append", required=True, dest="files")
    files_parser.add_argument(
        "--output",
        default=str(DATA_PATHS.private_raw_demos),
        help="private replay/demo destination",
    )
    files_parser.add_argument("--max-gb", type=float, default=1.0)
    files_parser.set_defaults(action="files")

    sidecars_parser = subparsers.add_parser(
        "sidecars",
        help="download map-balanced, quality-filtered analysis JSON files",
    )
    sidecars_parser.add_argument("--metadata", type=Path, default=DATA_PATHS.public_metadata)
    sidecars_parser.add_argument("--output", default=str(DATA_PATHS.private_sidecars))
    sidecars_parser.add_argument("--max-gb", type=float, default=0.25)
    sidecars_parser.add_argument("--max-files", type=int, default=500)
    sidecars_parser.add_argument("--min-rounds", type=int, default=16)
    sidecars_parser.add_argument("--min-kills", type=int, default=80)
    sidecars_parser.add_argument("--min-stars", type=int, default=0)
    sidecars_parser.set_defaults(action="sidecars")

    lock_parser = subparsers.add_parser(
        "lock",
        help="write a checksum manifest for an existing downloaded directory",
    )
    lock_parser.add_argument("--input", required=True, type=Path)
    lock_parser.add_argument("--output", required=True, type=Path)
    lock_parser.add_argument("--revision", default="main")
    lock_parser.set_defaults(action="lock")

    locked_parser = subparsers.add_parser(
        "locked",
        help="download exactly the files in a checksum manifest",
    )
    locked_parser.add_argument("--manifest", required=True, type=Path)
    locked_parser.add_argument("--output", default=str(DATA_PATHS.private_sidecars))
    locked_parser.add_argument("--max-gb", type=float, default=1.0)
    locked_parser.set_defaults(action="locked")

    verify_parser = subparsers.add_parser(
        "verify",
        help="verify a local directory against a checksum manifest",
    )
    verify_parser.add_argument("--manifest", required=True, type=Path)
    verify_parser.add_argument("--input", required=True, type=Path)
    verify_parser.set_defaults(action="verify")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    if args.command == "list":
        for path in list_dataset_files(args.dataset, path_in_repo=""):
            print(path)
        return 0

    if args.command == "lock":
        manifest = create_manifest(
            args.input,
            args.output,
            dataset_id=args.dataset,
            revision=args.revision,
        )
        print(f"manifest written: {args.output} ({len(manifest['files']):,} files)")
        return 0

    if args.command == "verify":
        differences = verify_manifest(args.input, args.manifest)
        if differences:
            for difference in differences:
                print(difference, file=sys.stderr)
            return 2
        print(f"verified: {args.input} matches {args.manifest}")
        return 0

    max_bytes = int(args.max_gb * 1_000_000_000)
    if max_bytes <= 0:
        raise ValueError("--max-gb must be positive")

    if args.command == "metadata":
        files = [path for path in list_dataset_files(args.dataset) if path.endswith(".parquet")]
        download_files(files, args.output, dataset_id=args.dataset, max_bytes=max_bytes)
    elif args.command == "files":
        download_files(args.files, args.output, dataset_id=args.dataset, max_bytes=max_bytes)
    elif args.command == "locked":
        download_manifest(args.manifest, args.output, max_bytes=max_bytes)
    else:
        from Noah.training.sidecar_catalog import (
            load_candidates,
            select_balanced_candidates,
        )

        candidates = load_candidates(
            args.metadata,
            min_rounds=args.min_rounds,
            min_kills=args.min_kills,
            min_stars=args.min_stars,
        )
        selected = select_balanced_candidates(
            candidates,
            max_files=args.max_files,
            max_bytes=max_bytes,
        )
        if not selected:
            raise ValueError("no sidecars matched the requested quality filters")
        selected_bytes = sum(candidate.size for candidate in selected)
        map_counts: dict[str, int] = {}
        for candidate in selected:
            map_counts[candidate.map_name] = map_counts.get(candidate.map_name, 0) + 1
        print(
            f"selected {len(selected):,} sidecars ({selected_bytes:,} estimated bytes) "
            f"across maps: {json.dumps(map_counts, sort_keys=True)}"
        )
        download_files(
            [candidate.repo_path for candidate in selected],
            args.output,
            dataset_id=args.dataset,
            max_bytes=max_bytes,
            skip_existing=True,
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (DownloadLimitError, RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc

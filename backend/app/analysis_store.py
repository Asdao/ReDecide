"""Atomic persistence helpers for per-analysis JSON state and results."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote
from uuid import uuid4

from backend.storage.blob import (
    BlobStorageNotFound,
    analysis_blob_store,
    blob_storage_enabled,
)


def analysis_store_root() -> Path:
    """Return the directory that holds persisted analysis artifacts."""

    return Path(os.getenv("REDECIDE_ANALYSIS_STORE", "data/runtime/analysis"))


def analysis_state_path(analysis_id: str, *, root: str | Path | None = None) -> Path:
    """Return the JSON path used to store the mutable analysis state."""

    return _analysis_artifact_path(analysis_id, "state.json", root=root)


def analysis_result_path(analysis_id: str, *, root: str | Path | None = None) -> Path:
    """Return the JSON path used to store the final analysis result."""

    return _analysis_artifact_path(analysis_id, "result.json", root=root)


def save_analysis_state(
    analysis_id: str,
    payload: Mapping[str, Any],
    *,
    root: str | Path | None = None,
) -> Path:
    """Atomically persist the current analysis state."""

    if blob_storage_enabled():
        analysis_blob_store().put_json(
            f"{_blob_analysis_id(analysis_id)}/state.json", payload
        )
        return analysis_state_path(analysis_id, root=root)

    path = analysis_state_path(analysis_id, root=root)
    _atomic_json_write(path, payload)
    return path


def load_analysis_state(
    analysis_id: str, *, root: str | Path | None = None
) -> dict[str, Any]:
    """Load the persisted analysis state for one analysis job."""

    if blob_storage_enabled():
        try:
            return analysis_blob_store().get_json(
                f"{_blob_analysis_id(analysis_id)}/state.json"
            )
        except BlobStorageNotFound as exc:
            raise FileNotFoundError(f"analysis state not found: {analysis_id}") from exc

    return _atomic_json_read(
        analysis_state_path(analysis_id, root=root), artifact_name="analysis state"
    )


def save_analysis_result(
    analysis_id: str,
    payload: Mapping[str, Any],
    *,
    root: str | Path | None = None,
) -> Path:
    """Atomically persist the final analysis result."""

    if blob_storage_enabled():
        analysis_blob_store().put_json(
            f"{_blob_analysis_id(analysis_id)}/result.json", payload
        )
        return analysis_result_path(analysis_id, root=root)

    path = analysis_result_path(analysis_id, root=root)
    _atomic_json_write(path, payload)
    return path


def load_analysis_result(
    analysis_id: str, *, root: str | Path | None = None
) -> dict[str, Any]:
    """Load the persisted final analysis result for one analysis job."""

    if blob_storage_enabled():
        try:
            return analysis_blob_store().get_json(
                f"{_blob_analysis_id(analysis_id)}/result.json"
            )
        except BlobStorageNotFound as exc:
            raise FileNotFoundError(f"analysis result not found: {analysis_id}") from exc

    return _atomic_json_read(
        analysis_result_path(analysis_id, root=root), artifact_name="analysis result"
    )


def _analysis_artifact_path(
    analysis_id: str, filename: str, *, root: str | Path | None = None
) -> Path:
    safe_analysis_id = quote(analysis_id, safe="-_.")
    store_root = Path(root) if root is not None else analysis_store_root()
    return store_root / safe_analysis_id / filename


def _blob_analysis_id(analysis_id: str) -> str:
    """Use the same conservative identifier normalization as filesystem paths."""

    return quote(analysis_id, safe="-_.")


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json_read(path: Path, *, artifact_name: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"{artifact_name} not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{artifact_name} must be a JSON object")
    return payload


__all__ = [
    "analysis_result_path",
    "analysis_store_root",
    "analysis_state_path",
    "load_analysis_result",
    "load_analysis_state",
    "save_analysis_result",
    "save_analysis_state",
]

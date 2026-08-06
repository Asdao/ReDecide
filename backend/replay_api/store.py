"""Shared filesystem artifacts between the replay and coaching APIs."""

from __future__ import annotations

import json
import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

from backend.storage.blob import (
    BlobStorageNotFound,
    blob_storage_enabled,
    replay_blob_store,
)

_REPLAY_ID = re.compile(r"^[0-9a-f]{32}$")


def replay_root() -> Path:
    configured = os.getenv("REDECIDE_REPLAY_STORE")
    if configured:
        return Path(configured)
    if os.getenv("VERCEL"):
        return Path(tempfile.gettempdir()) / "redecide" / "replays"
    return Path("data/runtime/replays")


def save_replay_artifacts(
    replay_id: str,
    *,
    visualization: Mapping[str, Any],
    coaching: Mapping[str, Any],
) -> Path | str:
    """Persist the two outputs produced after one native-demo parse."""

    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        store = replay_blob_store()
        store.put_json(f"{replay_id}/visualization.json", visualization)
        store.put_json(f"{replay_id}/coaching.json", coaching)
        return store.url(f"{replay_id}/visualization.json")
    directory = save_visualization_artifact(replay_id, visualization)
    save_coaching_artifact(replay_id, coaching)
    return directory


def save_visualization_artifact(replay_id: str, payload: Mapping[str, Any]) -> Path | str:
    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        return replay_blob_store().put_json(f"{replay_id}/visualization.json", payload).url
    directory = replay_root() / replay_id
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(directory / "visualization.json", payload)
    return directory


def save_coaching_artifact(replay_id: str, payload: Mapping[str, Any]) -> Path | str:
    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        return replay_blob_store().put_json(f"{replay_id}/coaching.json", payload).url
    directory = replay_root() / replay_id
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(directory / "coaching.json", payload)
    return directory


def save_replay_manifest(replay_id: str, payload: Mapping[str, Any]) -> Path | str:
    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        return replay_blob_store().put_json(f"{replay_id}/manifest.json", payload).url
    directory = replay_root() / replay_id
    directory.mkdir(parents=True, exist_ok=True)
    _atomic_json_write(directory / "manifest.json", payload)
    return directory


def unlock_visualization(replay_id: str) -> dict[str, Any]:
    """Allow the frontend to download full replay data after coaching."""

    manifest = load_replay_manifest(replay_id)
    manifest["coaching_status"] = "complete"
    manifest["visualization_unlocked"] = True
    save_replay_manifest(replay_id, manifest)
    return manifest


def load_replay_manifest(replay_id: str) -> dict[str, Any]:
    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        try:
            return replay_blob_store().get_json(f"{replay_id}/manifest.json")
        except BlobStorageNotFound as exc:
            raise FileNotFoundError(f"replay manifest not found: {replay_id}") from exc
    path = replay_root() / replay_id / "manifest.json"
    if not path.is_file():
        raise FileNotFoundError(f"replay manifest not found: {replay_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("replay manifest must be a JSON object")
    return payload


def visualization_path(replay_id: str) -> Path | str:
    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        try:
            return replay_blob_store().url(f"{replay_id}/visualization.json")
        except Exception as exc:
            raise FileNotFoundError(f"replay artifact not found: {replay_id}") from exc
    return replay_root() / replay_id / "visualization.json"


def load_coaching_replay(replay_id: str) -> dict[str, Any]:
    """Load only the coaching branch for the coaching FastAPI."""

    _validate_replay_id(replay_id)
    if blob_storage_enabled():
        try:
            return replay_blob_store().get_json(f"{replay_id}/coaching.json")
        except BlobStorageNotFound as exc:
            raise FileNotFoundError(f"replay artifact not found: {replay_id}") from exc
    path = replay_root() / replay_id / "coaching.json"
    if not path.is_file():
        raise FileNotFoundError(f"replay artifact not found: {replay_id}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("coaching replay artifact must be a JSON object")
    return payload


def _validate_replay_id(replay_id: str) -> None:
    if not _REPLAY_ID.fullmatch(replay_id):
        raise ValueError("invalid replay_id")


def _atomic_json_write(path: Path, payload: Mapping[str, Any]) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(payload), ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "load_coaching_replay",
    "load_replay_manifest",
    "replay_root",
    "save_coaching_artifact",
    "save_replay_artifacts",
    "save_replay_manifest",
    "save_visualization_artifact",
    "unlock_visualization",
    "visualization_path",
]

"""Stage, validate, activate, and roll back deployable model bundles.

Bundles are ordinary directories containing a replay-value manifest and its
component files.  The store deliberately uses only local filesystem
operations so a downloaded archive can be verified before it becomes active.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from cs2_sim.core.model import (
    REPLAY_FEATURE_NAMES,
    SUPPORTED_FEATURE_SCHEMA_VERSIONS,
)

from .contracts import ModelReleaseManifest

_HASH_CHUNK_SIZE = 1024 * 1024
_MANIFEST_NAMES = (
    "release_manifest.json",
    "full_replay_value.manifest.json",
    "manifest.json",
)
_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_RELEASE_REQUIRED_COMPONENTS = frozenset({"feature_schema", "full_replay_manifest"})


class BundleError(RuntimeError):
    """Raised when a model release is invalid or cannot be activated."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_version(version: str) -> str:
    if not _VERSION_RE.fullmatch(version):
        raise BundleError(f"invalid bundle version: {version!r}")
    return version


def find_manifest(root: str | Path) -> Path:
    """Find the bundle manifest at the root of a release directory."""

    directory = Path(root).expanduser().resolve()
    if directory.is_file():
        return directory
    for name in _MANIFEST_NAMES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    raise BundleError(f"model bundle has no supported manifest: {directory}")


def _load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BundleError(f"could not read model bundle manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BundleError("model bundle manifest must be a JSON object")
    names = tuple(payload.get("feature_names") or ())
    if names != REPLAY_FEATURE_NAMES:
        raise BundleError("model bundle feature schema does not match this application")
    schema_version = int(payload.get("feature_schema_version", payload.get("schema_version", 1)))
    if schema_version not in SUPPORTED_FEATURE_SCHEMA_VERSIONS:
        raise BundleError(
            f"unsupported model bundle feature schema {schema_version}; "
            f"expected one of {sorted(SUPPORTED_FEATURE_SCHEMA_VERSIONS)}"
        )
    return payload


def _validate_release_manifest(
    manifest_path: Path,
    *,
    expected_version: str | None = None,
    require_checksums: bool = False,
) -> dict[str, Any]:
    """Validate the complete release manifest and return its JSON payload.

    ``ModelReleaseManifest`` owns the component/path/checksum and feature-schema
    checks.  This wrapper adds release-store invariants that are intentionally
    stricter than the standalone contract: a published release must identify
    its directory version, include the feature contract and replay manifest,
    and point optional dataset/metrics metadata at files inside the release.
    """

    try:
        release = ModelReleaseManifest.load(manifest_path)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise BundleError(f"could not read release manifest {manifest_path}: {exc}") from exc

    bundle_root = manifest_path.parent.resolve()
    version = expected_version or bundle_root.name
    if release.version != version:
        raise BundleError(
            f"release manifest version {release.version!r} does not match "
            f"expected release {version!r}"
        )

    missing = sorted(_RELEASE_REQUIRED_COMPONENTS.difference(release.components))
    if missing:
        raise BundleError(
            "release manifest is incomplete; missing required components: "
            + ", ".join(missing)
        )

    # ModelReleaseManifest.validate checks every declared component.  Keep the
    # exception type at the bundle boundary stable for callers of this module.
    try:
        release.validate(bundle_root, require_checksums=require_checksums)
    except (OSError, TypeError, ValueError) as exc:
        raise BundleError(f"invalid release manifest {manifest_path}: {exc}") from exc

    # These fields are paths in the contract, but are not component entries.
    # Validate them here so a release cannot advertise metadata that is absent
    # or escapes the bundle root.
    for name in ("dataset_manifest", "metrics"):
        value = getattr(release, name)
        if value is None:
            continue
        if not isinstance(value, str) or not value:
            raise BundleError(f"release manifest {name} path must be a non-empty string")
        candidate = (bundle_root / value).resolve() if not Path(value).is_absolute() else Path(value).resolve()
        try:
            candidate.relative_to(bundle_root)
        except ValueError as exc:
            raise BundleError(f"release manifest {name} escapes bundle directory: {candidate}") from exc
        if not candidate.is_file():
            raise BundleError(f"release manifest {name} is missing: {candidate}")

    return release.to_dict()


def _component_metadata(payload: dict[str, Any], name: str) -> dict[str, Any] | None:
    components = payload.get("components")
    if isinstance(components, dict) and isinstance(components.get(name), dict):
        return components[name]
    value = payload.get(name)
    return {"path": value} if isinstance(value, str) else None


def _component_path(manifest: Path, metadata: dict[str, Any]) -> Path:
    value = metadata.get("path")
    if not isinstance(value, str) or not value:
        raise BundleError("model bundle component path must be a non-empty string")
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.resolve()
    return (manifest.parent / candidate).resolve()


def validate_bundle(
    root: str | Path,
    *,
    require_checksums: bool = False,
) -> dict[str, Any]:
    """Validate manifest, component containment, sizes, and SHA-256 hashes."""

    manifest = find_manifest(root)
    if manifest.name == "release_manifest.json":
        return _validate_release_manifest(
            manifest,
            require_checksums=require_checksums,
        )
    payload = _load_manifest(manifest)
    bundle_root = manifest.parent.resolve()
    found_component = False
    for name in ("booster", "bayesian", "calibrator", "engagement_model", "engagement"):
        metadata = _component_metadata(payload, name)
        if metadata is None or metadata.get("path") is None:
            continue
        found_component = True
        component = _component_path(manifest, metadata)
        try:
            component.relative_to(bundle_root)
        except ValueError as exc:
            raise BundleError(f"{name} component escapes the bundle directory: {component}") from exc
        if not component.is_file():
            raise BundleError(f"missing {name} component: {component}")
        expected_bytes = metadata.get("bytes")
        expected_hash = metadata.get("sha256")
        if require_checksums and (expected_bytes is None or expected_hash is None):
            raise BundleError(f"{name} component is missing checksum metadata")
        if expected_bytes is not None and int(expected_bytes) != component.stat().st_size:
            raise BundleError(f"{name} component size mismatch: {component}")
        if expected_hash is not None and str(expected_hash).lower() != _sha256(component):
            raise BundleError(f"{name} component checksum mismatch: {component}")
    if not found_component:
        raise BundleError("model bundle contains no model components")
    return payload


class ModelBundleStore:
    """Filesystem release store with atomic current-pointer updates."""

    def __init__(self, releases_dir: str | Path, *, pointer_name: str = "current.json") -> None:
        self.root = Path(releases_dir).expanduser().resolve()
        self.pointer = self.root / pointer_name
        self.root.mkdir(parents=True, exist_ok=True)

    def stage(
        self,
        source: str | Path,
        *,
        version: str,
        require_checksums: bool = False,
    ) -> Path:
        """Copy and verify a local bundle, then atomically publish its release dir."""

        version = _safe_version(version)
        source_path = Path(source).expanduser().resolve()
        source_root = source_path.parent if source_path.is_file() else source_path
        if not source_root.is_dir():
            raise BundleError(f"bundle source directory does not exist: {source_root}")
        validate_bundle(source_root, require_checksums=require_checksums)
        destination = self.root / version
        if os.path.lexists(destination):
            raise BundleError(f"bundle version already exists: {destination}")
        staging_root = self.root / ".staging"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging = staging_root / f"{version}-{uuid.uuid4().hex}"
        try:
            shutil.copytree(source_root, staging)
            staged_manifest = find_manifest(staging)
            if staged_manifest.name == "release_manifest.json":
                _validate_release_manifest(
                    staged_manifest,
                    expected_version=version,
                    require_checksums=require_checksums,
                )
            else:
                validate_bundle(staging, require_checksums=require_checksums)
            # os.replace would silently replace an existing release in a race.
            # os.rename is atomic on one filesystem and fails if the target was
            # created after the initial existence check.
            os.rename(staging, destination)
        except FileExistsError as exc:
            raise BundleError(f"bundle version already exists: {destination}") from exc
        except Exception:
            if staging.exists():
                shutil.rmtree(staging)
            raise
        return destination

    def _read_pointer(self) -> dict[str, Any] | None:
        if not self.pointer.exists():
            return None
        try:
            payload = json.loads(self.pointer.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BundleError(f"could not read active model pointer: {exc}") from exc
        if not isinstance(payload, dict) or not isinstance(payload.get("version"), str):
            raise BundleError("active model pointer is invalid")
        return payload

    def activate(self, version: str, *, require_checksums: bool = False) -> Path:
        version = _safe_version(version)
        destination = (self.root / version).resolve()
        try:
            destination.relative_to(self.root)
        except ValueError as exc:
            raise BundleError("bundle version escapes release directory") from exc
        if not destination.is_dir():
            raise BundleError(f"bundle version does not exist: {version}")
        validate_bundle(destination, require_checksums=require_checksums)
        previous = self._read_pointer()
        payload = {
            "pointer_version": 1,
            "version": version,
            "previous_version": previous.get("version") if previous else None,
        }
        temporary = self.pointer.with_name(f"{self.pointer.name}.{uuid.uuid4().hex}.part")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.pointer)
        return destination

    def current(self, *, validate: bool = True) -> Path:
        payload = self._read_pointer()
        if payload is None:
            raise BundleError("no active model bundle")
        version = _safe_version(str(payload["version"]))
        destination = self.root / version
        if validate:
            validate_bundle(destination)
        return destination

    def rollback(self, *, require_checksums: bool = False) -> Path:
        payload = self._read_pointer()
        if payload is None or not payload.get("previous_version"):
            raise BundleError("no previous model bundle is available for rollback")
        return self.activate(str(payload["previous_version"]), require_checksums=require_checksums)

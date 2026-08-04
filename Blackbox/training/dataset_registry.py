"""Versioned registry for reproducible public/private dataset projections.

The registry contains metadata only; it never copies or removes dataset files.
Training, validation, and benchmark entries are kept as match-level groups so
the same match cannot accidentally appear in two evaluation roles.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from Blackbox.training.data_paths import DATA_PATHS

REGISTRY_SCHEMA_VERSION = 1
DATASET_ROLES = frozenset({"training", "validation", "benchmark", "rejected"})
VISIBILITIES = frozenset({"public", "private"})
_HASH_CHUNK_SIZE = 1024 * 1024


class DatasetRegistryError(ValueError):
    """Raised when a registry or dataset entry violates its contract."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_HASH_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _portable_path(path: Path) -> str:
    resolved = path.expanduser().resolve()
    for root, prefix in ((DATA_PATHS.public, "public:"), (DATA_PATHS.private, "private:")):
        try:
            return prefix + resolved.relative_to(root.resolve()).as_posix()
        except ValueError:
            continue
    return resolved.as_posix()


def _local_path(value: str | Path) -> Path:
    text = str(value).replace("\\", "/")
    for prefix, root in (("public:", DATA_PATHS.public), ("private:", DATA_PATHS.private)):
        if text.startswith(prefix):
            return (root / text.removeprefix(prefix)).resolve()
    return Path(value).expanduser().resolve()


def file_manifest(path: str | Path) -> list[dict[str, Any]]:
    """Return deterministic size/checksum metadata for a file or directory."""

    root = _local_path(path)
    if root.is_file():
        return [{"path": root.name, "bytes": root.stat().st_size, "sha256": _sha256(root)}]
    if not root.is_dir():
        raise FileNotFoundError(f"dataset path does not exist: {root}")
    entries: list[dict[str, Any]] = []
    for item in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(
            {
                "path": item.relative_to(root).as_posix(),
                "bytes": item.stat().st_size,
                "sha256": _sha256(item),
            }
        )
    return entries


@dataclass(frozen=True, slots=True)
class DatasetRecord:
    """One registered immutable dataset projection."""

    dataset_id: str
    role: str
    visibility: str
    path: str
    format: str = "parquet"
    schema_version: str = "snapshot_action_parquet_v1"
    feature_schema_version: str = "unknown"
    group_field: str = "match_id"
    groups: tuple[str, ...] = ()
    rows: dict[str, int] = field(default_factory=dict)
    source_database: str | None = None
    files: tuple[dict[str, Any], ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)
    rejection_reason: str | None = None
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.dataset_id.strip():
            raise DatasetRegistryError("dataset_id must not be empty")
        if self.role not in DATASET_ROLES:
            raise DatasetRegistryError(f"unsupported dataset role: {self.role}")
        if self.visibility not in VISIBILITIES:
            raise DatasetRegistryError(f"unsupported dataset visibility: {self.visibility}")
        if self.group_field != "match_id":
            raise DatasetRegistryError("dataset grouping must use match_id")
        if self.role == "rejected" and not str(self.rejection_reason or "").strip():
            raise DatasetRegistryError("rejected datasets require a rejection_reason")
        if any(not str(group).strip() for group in self.groups):
            raise DatasetRegistryError("dataset groups must be non-empty strings")
        if any(int(value) < 0 for value in self.rows.values()):
            raise DatasetRegistryError("dataset row counts cannot be negative")
        if not self.created_at:
            object.__setattr__(self, "created_at", datetime.now(UTC).isoformat())

    @property
    def key(self) -> tuple[str, str]:
        return self.dataset_id, self.role

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["groups"] = list(self.groups)
        payload["files"] = [dict(item) for item in self.files]
        return payload

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> DatasetRecord:
        if not isinstance(payload, dict):
            raise DatasetRegistryError("dataset entry must be an object")
        fields = {
            "dataset_id": str(payload.get("dataset_id") or ""),
            "role": str(payload.get("role") or ""),
            "visibility": str(payload.get("visibility") or ""),
            "path": str(payload.get("path") or ""),
            "format": str(payload.get("format") or "parquet"),
            "schema_version": str(payload.get("schema_version") or "snapshot_action_parquet_v1"),
            "feature_schema_version": str(payload.get("feature_schema_version") or "unknown"),
            "group_field": str(payload.get("group_field") or "match_id"),
            "groups": tuple(sorted({str(value) for value in payload.get("groups", [])})),
            "rows": {str(key): int(value) for key, value in (payload.get("rows") or {}).items()},
            "source_database": payload.get("source_database"),
            "files": tuple(dict(item) for item in payload.get("files", []) if isinstance(item, dict)),
            "metadata": dict(payload.get("metadata") or {}),
            "rejection_reason": payload.get("rejection_reason"),
            "created_at": str(payload.get("created_at") or ""),
        }
        return cls(**fields)


class DatasetRegistry:
    """Read/write registry with atomic updates and group-overlap checks."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.records: list[DatasetRecord] = []

    @classmethod
    def load(cls, path: str | Path) -> DatasetRegistry:
        registry = cls(path)
        if not registry.path.exists():
            return registry
        try:
            payload = json.loads(registry.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise DatasetRegistryError(f"could not read dataset registry: {registry.path}") from exc
        if not isinstance(payload, dict) or int(payload.get("schema_version", -1)) != REGISTRY_SCHEMA_VERSION:
            raise DatasetRegistryError("unsupported dataset registry schema version")
        entries = payload.get("datasets")
        if not isinstance(entries, list):
            raise DatasetRegistryError("dataset registry datasets must be a list")
        registry.records = [DatasetRecord.from_dict(entry) for entry in entries]
        registry.validate()
        return registry

    def validate(self) -> None:
        seen_keys: set[tuple[str, str]] = set()
        groups: dict[str, DatasetRecord] = {}
        for record in self.records:
            if record.key in seen_keys:
                raise DatasetRegistryError(f"duplicate dataset registry entry: {record.key}")
            seen_keys.add(record.key)
            for group in record.groups:
                previous = groups.get(group)
                if previous is not None and previous.key != record.key:
                    raise DatasetRegistryError(
                        f"match group {group!r} appears in both {previous.key} and {record.key}"
                    )
                groups[group] = record

    def register(self, record: DatasetRecord, *, replace: bool = False) -> None:
        existing_index = next((index for index, item in enumerate(self.records) if item.key == record.key), None)
        previous = self.records[existing_index] if existing_index is not None else None
        if existing_index is not None:
            if not replace:
                raise DatasetRegistryError(f"dataset registry entry already exists: {record.key}")
            self.records.pop(existing_index)
        self.records.append(record)
        try:
            self.validate()
        except Exception:
            self.records.pop()
            if previous is not None and existing_index is not None:
                self.records.insert(existing_index, previous)
            raise

    def save(self) -> None:
        self.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": REGISTRY_SCHEMA_VERSION,
            "datasets": [record.to_dict() for record in self.records],
        }
        temporary = self.path.with_name(f"{self.path.name}.part")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self.path)

    def find(self, dataset_id: str, *, role: str | None = None) -> list[DatasetRecord]:
        return [
            record
            for record in self.records
            if record.dataset_id == dataset_id and (role is None or record.role == role)
        ]


def make_record(
    *,
    dataset_id: str,
    role: str,
    visibility: str,
    path: str | Path,
    groups: Iterable[str],
    rows: dict[str, int],
    source_database: str | Path | None = None,
    feature_schema_version: str = "unknown",
    metadata: dict[str, Any] | None = None,
    rejection_reason: str | None = None,
) -> DatasetRecord:
    """Build a registry record and collect checksums for its projection files."""

    local = _local_path(path)
    return DatasetRecord(
        dataset_id=dataset_id,
        role=role,
        visibility=visibility,
        path=_portable_path(local),
        groups=tuple(sorted({str(group) for group in groups})),
        rows={str(key): int(value) for key, value in rows.items()},
        source_database=_portable_path(_local_path(source_database)) if source_database else None,
        feature_schema_version=str(feature_schema_version),
        files=tuple(file_manifest(local)),
        metadata=dict(metadata or {}),
        rejection_reason=rejection_reason,
    )


def _default_registry(visibility: str) -> Path:
    return (DATA_PATHS.public if visibility == "public" else DATA_PATHS.private) / "dataset_registry.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create an empty registry")
    init_parser.add_argument("--registry", type=Path, default=DATA_PATHS.public / "dataset_registry.json")

    add_parser = subparsers.add_parser("add", help="register an existing dataset projection")
    add_parser.add_argument("--registry", type=Path)
    add_parser.add_argument("--dataset-id", required=True)
    add_parser.add_argument("--role", choices=sorted(DATASET_ROLES), required=True)
    add_parser.add_argument("--visibility", choices=sorted(VISIBILITIES), required=True)
    add_parser.add_argument("--path", type=Path, required=True)
    add_parser.add_argument("--source-database", type=Path)
    add_parser.add_argument("--feature-schema-version", default="unknown")
    add_parser.add_argument("--match-id", action="append", default=[])
    add_parser.add_argument("--rows-json", type=Path)
    add_parser.add_argument("--replace", action="store_true")
    add_parser.add_argument("--rejection-reason")

    list_parser = subparsers.add_parser("list", help="list registered datasets")
    list_parser.add_argument("--registry", type=Path, default=DATA_PATHS.public / "dataset_registry.json")
    validate_parser = subparsers.add_parser("validate", help="validate registry and match grouping")
    validate_parser.add_argument("--registry", type=Path, default=DATA_PATHS.public / "dataset_registry.json")
    args = parser.parse_args()

    if args.command == "init":
        registry = DatasetRegistry(args.registry)
        registry.save()
        print(f"dataset registry written: {args.registry}")
        return 0
    registry_path = args.registry
    if args.command == "add":
        registry_path = registry_path or _default_registry(args.visibility)
        rows: dict[str, int] = {}
        if args.rows_json:
            rows = {str(key): int(value) for key, value in json.loads(args.rows_json.read_text(encoding="utf-8")).items()}
        registry = DatasetRegistry.load(registry_path)
        record = make_record(
            dataset_id=args.dataset_id,
            role=args.role,
            visibility=args.visibility,
            path=args.path,
            groups=args.match_id,
            rows=rows,
            source_database=args.source_database,
            feature_schema_version=args.feature_schema_version,
            rejection_reason=args.rejection_reason,
        )
        registry.register(record, replace=args.replace)
        registry.save()
        print(f"registered {record.dataset_id} ({record.role}) in {registry_path}")
        return 0
    registry = DatasetRegistry.load(registry_path)
    if args.command == "list":
        print(json.dumps([record.to_dict() for record in registry.records], indent=2))
    else:
        print(f"dataset registry valid: {registry_path} ({len(registry.records)} entries)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

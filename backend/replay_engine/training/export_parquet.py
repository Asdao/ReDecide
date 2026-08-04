"""Stream canonical SQLite snapshot/action rows into compact Parquet files.

The exporter is read-only with respect to SQLite and writes a new versioned
directory.  Rows retain ``match_id`` and replay/round/tick identity, while
model features are stored as typed numeric columns instead of large JSON
payloads.  Optional registry registration happens only after the export is
complete.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from backend.replay_engine.training.data_paths import DATA_PATHS
from backend.replay_engine.training.dataset_registry import DatasetRegistry, make_record
from backend.replay_engine.training.replay_repository import ReplayRepository

try:
    from cs2_sim.core.model import REPLAY_FEATURE_NAMES
except ImportError:  # pragma: no cover - package import is configured by pyproject
    REPLAY_FEATURE_NAMES = ()


EXPORT_SCHEMA_VERSION = "snapshot_action_parquet_v1"
_HASH_SIZE = 16


@dataclass(frozen=True, slots=True)
class ExportResult:
    output_dir: Path
    snapshots_path: Path | None
    actions_path: Path | None
    snapshot_rows: int
    action_rows: int
    match_ids: tuple[str, ...]
    registry_path: Path | None


def _require_pyarrow() -> tuple[Any, Any]:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise RuntimeError("Parquet export requires pyarrow; install with `pip install .[full]`") from exc
    return pa, pq


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _group(row: dict[str, Any]) -> str:
    value = row.get("match_id")
    if value not in (None, ""):
        return str(value)
    replay = row.get("replay_id")
    return f"replay:{replay}" if replay not in (None, "") else "unknown"


def _source(row: dict[str, Any], visibility: str) -> tuple[str | None, str]:
    value = str(row.get("source") or row.get("source_path") or "")
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:_HASH_SIZE]
    return (None if visibility == "public" else value), digest


def _player_reference(value: Any, visibility: str) -> str:
    """Avoid publishing Steam IDs while keeping deterministic joins in public data."""

    text = str(value or "")
    if visibility != "public" or not text:
        return text
    return "player:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:_HASH_SIZE]


def _database_ref(database: Path, visibility: str) -> str:
    if visibility != "public":
        return database.as_posix()
    try:
        relative = database.relative_to(DATA_PATHS.private.resolve())
    except ValueError:
        return "private:source/" + database.name
    return "private:" + relative.as_posix()


def _safe_metadata(values: dict[str, str], visibility: str) -> dict[str, str]:
    if visibility != "public":
        return dict(values)
    return {
        key: ("redacted" if "path" in key.lower() or "file" in key.lower() else value)
        for key, value in values.items()
    }


def _snapshot_schema(pa: Any, metadata: dict[bytes, bytes]) -> Any:
    fields = [
        ("dataset_id", pa.string()),
        ("role", pa.string()),
        ("visibility", pa.string()),
        ("match_id", pa.string()),
        ("replay_id", pa.int64()),
        ("snapshot_id", pa.int64()),
        ("source_path", pa.string()),
        ("source_hash", pa.string()),
        ("round_num", pa.int32()),
        ("tick", pa.int64()),
        ("map_name", pa.string()),
        ("elapsed_seconds", pa.float64()),
        ("ct_alive", pa.int16()),
        ("t_alive", pa.int16()),
        ("alive_difference", pa.int16()),
        ("kills_seen", pa.int32()),
        ("bomb_planted", pa.bool_()),
        ("bomb_site", pa.string()),
        ("label_ct_win", pa.int8()),
    ]
    # Prefix model columns so fields such as ``ct_alive`` and
    # ``bomb_planted`` do not collide with the human-readable metadata fields
    # above.  The prefix is deterministic and keeps the model feature name
    # visible without storing a JSON blob.
    fields.extend((f"feature_{name}", pa.float64()) for name in REPLAY_FEATURE_NAMES)
    return pa.schema(fields, metadata=metadata)


def _action_schema(pa: Any, metadata: dict[bytes, bytes]) -> Any:
    return pa.schema(
        [
            ("dataset_id", pa.string()),
            ("role", pa.string()),
            ("visibility", pa.string()),
            ("match_id", pa.string()),
            ("replay_id", pa.int64()),
            ("action_id", pa.int64()),
            ("source_path", pa.string()),
            ("source_hash", pa.string()),
            ("map_name", pa.string()),
            ("round_num", pa.int32()),
            ("tick", pa.int64()),
            ("next_tick", pa.int64()),
            ("player_id", pa.string()),
            ("side", pa.string()),
            ("current_zone", pa.string()),
            ("next_zone", pa.string()),
            ("action", pa.string()),
            ("horizon_ticks", pa.int32()),
            ("legal_actions_json", pa.string()),
            ("outcome_json", pa.string()),
        ],
        metadata=metadata,
    )


def _metadata(
    *,
    pa: Any,
    dataset_id: str,
    role: str,
    visibility: str,
    database: Path,
    source_metadata: dict[str, str],
) -> dict[bytes, bytes]:
    payload = {
        "dataset_id": dataset_id,
        "role": role,
        "visibility": visibility,
        "export_schema_version": EXPORT_SCHEMA_VERSION,
        "feature_schema_version": source_metadata.get("feature_schema_version", "unknown"),
        "source_database": _database_ref(database, visibility),
        "source_database_metadata": _safe_metadata(source_metadata, visibility),
        "group_field": "match_id",
    }
    return {str(key).encode(): json.dumps(value, sort_keys=True).encode() for key, value in payload.items()}


def _arrow_table(pa: Any, rows: list[dict[str, Any]], schema: Any) -> Any:
    arrays = {
        field.name: pa.array([row.get(field.name) for row in rows], type=field.type)
        for field in schema
    }
    return pa.table(arrays, schema=schema)


def _write_parquet(
    *,
    pa: Any,
    pq: Any,
    path: Path,
    schema: Any,
    rows: Iterable[dict[str, Any]],
    batch_size: int,
) -> tuple[int, set[str]]:
    writer = pq.ParquetWriter(path, schema, compression="zstd")
    count = 0
    groups: set[str] = set()
    batch: list[dict[str, Any]] = []
    try:
        for row in rows:
            batch.append(row)
            groups.add(str(row["match_id"]))
            if len(batch) >= batch_size:
                writer.write_table(_arrow_table(pa, batch, schema))
                count += len(batch)
                batch.clear()
        if batch:
            writer.write_table(_arrow_table(pa, batch, schema))
            count += len(batch)
    finally:
        writer.close()
    return count, groups


def _snapshot_rows(
    rows: Iterable[dict[str, Any]],
    *,
    dataset_id: str,
    role: str,
    visibility: str,
    selected_groups: set[str] | None,
) -> Iterable[dict[str, Any]]:
    for row in rows:
        group = _group(row)
        if selected_groups is not None and group not in selected_groups:
            continue
        source_path, source_hash = _source(row, visibility)
        snapshot = row.get("snapshot") or {}
        features = row.get("features") or {}
        yield {
            "dataset_id": dataset_id,
            "role": role,
            "visibility": visibility,
            "match_id": group,
            "replay_id": int(row.get("replay_id") or 0),
            "snapshot_id": int(row.get("snapshot_id") or 0),
            "source_path": source_path,
            "source_hash": source_hash,
            "round_num": int(row.get("round_num") or 0),
            "tick": int(row.get("tick") or 0),
            "map_name": str(snapshot.get("map_name") or "unknown"),
            "elapsed_seconds": _number(snapshot.get("elapsed_seconds")),
            "ct_alive": int(snapshot.get("ct_alive") or 0),
            "t_alive": int(snapshot.get("t_alive") or 0),
            "alive_difference": int(snapshot.get("alive_difference") or 0),
            "kills_seen": int(snapshot.get("kills_seen") or 0),
            "bomb_planted": bool(snapshot.get("bomb_planted")),
            "bomb_site": snapshot.get("bomb_site"),
            "label_ct_win": int(row.get("label_ct_win") or 0),
            **{
                f"feature_{name}": _number(features.get(name, snapshot.get(name)))
                for name in REPLAY_FEATURE_NAMES
            },
        }


def _action_rows(
    rows: Iterable[dict[str, Any]],
    *,
    dataset_id: str,
    role: str,
    visibility: str,
    selected_groups: set[str] | None,
) -> Iterable[dict[str, Any]]:
    for row in rows:
        group = _group(row)
        if selected_groups is not None and group not in selected_groups:
            continue
        source_path, source_hash = _source(row, visibility)
        yield {
            "dataset_id": dataset_id,
            "role": role,
            "visibility": visibility,
            "match_id": group,
            "replay_id": int(row.get("replay_id") or 0),
            "action_id": int(row.get("action_id") or 0),
            "source_path": source_path,
            "source_hash": source_hash,
            "map_name": row.get("map_name"),
            "round_num": int(row.get("round_num") or 0),
            "tick": int(row.get("tick") or 0),
            "next_tick": int(row.get("next_tick") or 0),
            "player_id": _player_reference(row.get("player_id"), visibility),
            "side": row.get("side"),
            "current_zone": row.get("current_zone"),
            "next_zone": row.get("next_zone"),
            "action": str(row.get("action") or "unknown"),
            "horizon_ticks": int(row.get("horizon_ticks") or 0),
            "legal_actions_json": json.dumps(row.get("legal_actions") or [], sort_keys=True),
            "outcome_json": json.dumps(row.get("outcome") or {}, sort_keys=True),
        }


def export_sqlite_to_parquet(
    database_path: str | Path,
    output_dir: str | Path,
    *,
    dataset_id: str = "replay_features_v1",
    role: str = "training",
    visibility: str = "private",
    registry_path: str | Path | None = None,
    match_ids: Sequence[str] | None = None,
    include_snapshots: bool = True,
    include_actions: bool = True,
    batch_size: int = 4096,
) -> ExportResult:
    """Export rows in one pass per table and optionally register the result."""

    if role not in {"training", "validation", "benchmark", "rejected"}:
        raise ValueError(f"unsupported dataset role: {role}")
    if visibility not in {"public", "private"}:
        raise ValueError(f"unsupported dataset visibility: {visibility}")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if not include_snapshots and not include_actions:
        raise ValueError("at least one of snapshots/actions must be exported")
    pa, pq = _require_pyarrow()
    database = Path(database_path).expanduser().resolve()
    target = Path(output_dir).expanduser().resolve()
    if target.exists():
        raise FileExistsError(f"refusing to overwrite existing export directory: {target}")
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.parent / f".{target.name}.{uuid.uuid4().hex}.part"
    selected = {str(value) for value in match_ids} if match_ids else None
    snapshot_count = action_count = 0
    groups: set[str] = set()
    snapshot_path: Path | None = None
    action_path: Path | None = None
    try:
        staging.mkdir()
        with ReplayRepository(database) as repository:
            source_metadata = repository.metadata()
            metadata_values = _safe_metadata(source_metadata, visibility)
            metadata = _metadata(
                pa=pa,
                dataset_id=dataset_id,
                role=role,
                visibility=visibility,
                database=database,
                source_metadata=metadata_values,
            )
            if include_snapshots:
                snapshot_path = staging / "snapshots.parquet"
                snapshot_count, snapshot_groups = _write_parquet(
                    pa=pa,
                    pq=pq,
                    path=snapshot_path,
                    schema=_snapshot_schema(pa, metadata),
                    rows=_snapshot_rows(
                        repository.iter_snapshot_rows(),
                        dataset_id=dataset_id,
                        role=role,
                        visibility=visibility,
                        selected_groups=selected,
                    ),
                    batch_size=batch_size,
                )
                groups.update(snapshot_groups)
            if include_actions:
                action_path = staging / "actions.parquet"
                action_count, action_groups = _write_parquet(
                    pa=pa,
                    pq=pq,
                    path=action_path,
                    schema=_action_schema(pa, metadata),
                    rows=_action_rows(
                        repository.iter_actions(),
                        dataset_id=dataset_id,
                        role=role,
                        visibility=visibility,
                        selected_groups=selected,
                    ),
                    batch_size=batch_size,
                )
                groups.update(action_groups)
            if selected is not None and not groups.issuperset(selected):
                missing = sorted(selected - groups)
                raise ValueError(f"requested match groups were not found: {missing[:5]}")
            metadata_payload = {
                "dataset_id": dataset_id,
                "role": role,
                "visibility": visibility,
                "schema_version": EXPORT_SCHEMA_VERSION,
                "feature_schema_version": source_metadata.get("feature_schema_version", "unknown"),
                "group_field": "match_id",
                "match_ids": sorted(groups),
                "rows": {"snapshots": snapshot_count, "actions": action_count},
                "source_database": _database_ref(database, visibility),
                "source_database_metadata": metadata_values,
            }
            (staging / "metadata.json").write_text(json.dumps(metadata_payload, indent=2) + "\n", encoding="utf-8")
        os.replace(staging, target)
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    registry_destination: Path | None = None
    if registry_path is not None:
        registry_destination = Path(registry_path)
        registry = DatasetRegistry.load(registry_destination)
        record = make_record(
            dataset_id=dataset_id,
            role=role,
            visibility=visibility,
            path=target,
            groups=sorted(groups),
            rows={"snapshots": snapshot_count, "actions": action_count},
            source_database=database,
            feature_schema_version=json.loads((target / "metadata.json").read_text(encoding="utf-8"))["feature_schema_version"],
            metadata={"export_schema_version": EXPORT_SCHEMA_VERSION},
        )
        registry.register(record)
        registry.save()
    return ExportResult(
        output_dir=target,
        snapshots_path=target / "snapshots.parquet" if include_snapshots else None,
        actions_path=target / "actions.parquet" if include_actions else None,
        snapshot_rows=snapshot_count,
        action_rows=action_count,
        match_ids=tuple(sorted(groups)),
        registry_path=registry_destination,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-id", default="replay_features_v1")
    parser.add_argument("--role", choices=("training", "validation", "benchmark", "rejected"), default="training")
    parser.add_argument("--visibility", choices=("public", "private"), default="private")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--match-id", action="append", default=[])
    parser.add_argument("--snapshots-only", action="store_true")
    parser.add_argument("--actions-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=4096)
    args = parser.parse_args()
    if args.snapshots_only and args.actions_only:
        parser.error("--snapshots-only and --actions-only are mutually exclusive")
    registry = args.registry or (
        DATA_PATHS.public if args.visibility == "public" else DATA_PATHS.private
    ) / "dataset_registry.json"
    result = export_sqlite_to_parquet(
        args.database,
        args.output,
        dataset_id=args.dataset_id,
        role=args.role,
        visibility=args.visibility,
        registry_path=registry,
        match_ids=args.match_id,
        include_snapshots=not args.actions_only,
        include_actions=not args.snapshots_only,
        batch_size=args.batch_size,
    )
    print(json.dumps({"output": result.output_dir.as_posix(), "snapshots": result.snapshot_rows, "actions": result.action_rows, "matches": list(result.match_ids)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

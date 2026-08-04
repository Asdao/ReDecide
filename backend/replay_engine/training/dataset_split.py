"""Deterministic, group-aware dataset fingerprints and train/holdout splits.

Replay observations are highly correlated within a demo (and often within a
match).  This module keeps those observations together so evaluation cannot
silently train on one tick and test on another tick from the same replay.
The helpers accept dictionaries from either the JSONL pipeline or the SQLite
repository and never mutate the input rows.
"""

from __future__ import annotations

import hashlib
import json
import random
from collections.abc import Iterable, Sequence
from typing import Any


SPLIT_SCHEMA_VERSION = "grouped_match_v1"


def _text(value: Any, default: str = "unknown") -> str:
    if value in (None, ""):
        return default
    return str(value)


def group_id(row: dict[str, Any], *, index: int = 0) -> str:
    """Return the stable match/replay group identifier for an observation.

    ``match_id`` is preferred when present.  Parsed JSONL commonly has only a
    source path, so that is the next safe boundary.  The final index fallback
    is intentionally unique: it avoids accidental leakage when a malformed
    row has no identifying metadata.
    """

    for key in ("match_id", "match", "source", "source_path", "demo_file", "replay_id"):
        value = row.get(key)
        if isinstance(value, dict):
            value = value.get("match_id") or value.get("source_path")
        if value not in (None, ""):
            return _text(value)
    payload = row.get("payload")
    if isinstance(payload, dict):
        for key in ("match_id", "source", "source_path", "demo_file"):
            if payload.get(key) not in (None, ""):
                return _text(payload[key])
    return f"row:{index}"


def _canonical(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _canonical(value[key]) for key in sorted(value)}
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    if isinstance(value, float):
        return round(value, 8)
    return value


def dataset_fingerprint(rows: Iterable[dict[str, Any]], *, schema_version: str = "unknown") -> str:
    """Hash row identity and labels, excluding volatile feature payloads."""

    observations = []
    for index, row in enumerate(rows):
        observations.append(
            {
                "group": group_id(row, index=index),
                "round": row.get("round_num"),
                "tick": row.get("tick"),
                "label": row.get("label_ct_win", row.get("action")),
            }
        )
    observations.sort(key=lambda value: json.dumps(value, sort_keys=True, default=str))
    payload = {"schema_version": schema_version, "rows": observations}
    return hashlib.sha256(
        json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def split_fingerprint(
    train_rows: Sequence[dict[str, Any]],
    validation_rows: Sequence[dict[str, Any]],
    *,
    seed: int,
    validation_fraction: float,
) -> str:
    """Hash group assignments and split settings for report compatibility."""

    train_groups = sorted({group_id(row, index=index) for index, row in enumerate(train_rows)})
    validation_groups = sorted(
        {group_id(row, index=index) for index, row in enumerate(validation_rows)}
    )
    payload = {
        "version": SPLIT_SCHEMA_VERSION,
        "seed": int(seed),
        "validation_fraction": float(validation_fraction),
        "train_groups": train_groups,
        "validation_groups": validation_groups,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def grouped_split(
    rows: Sequence[dict[str, Any]],
    *,
    validation_fraction: float = 0.2,
    seed: int = 7,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    """Split rows by match/source and return serializable split metadata."""

    if not rows:
        raise ValueError("cannot split an empty dataset")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    groups: dict[str, list[dict[str, Any]]] = {}
    for index, row in enumerate(rows):
        groups.setdefault(group_id(row, index=index), []).append(row)
    group_names = sorted(groups)
    if len(group_names) < 2:
        raise ValueError("need at least two match/source groups for a held-out split")
    shuffled = list(group_names)
    random.Random(seed).shuffle(shuffled)
    validation_count = max(1, int(round(len(shuffled) * validation_fraction)))
    validation_count = min(len(shuffled) - 1, validation_count)
    validation_groups = set(shuffled[-validation_count:])
    # Reconstruct by position so duplicate dictionaries remain separate rows.
    train_rows = []
    validation_rows = []
    for index, row in enumerate(rows):
        (validation_rows if group_id(row, index=index) in validation_groups else train_rows).append(row)
    metadata = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "seed": int(seed),
        "validation_fraction": float(validation_fraction),
        "group_field": "match_id|source_path",
        "train_groups": sorted({group_id(row, index=i) for i, row in enumerate(train_rows)}),
        "validation_groups": sorted({group_id(row, index=i) for i, row in enumerate(validation_rows)}),
        "split_fingerprint": split_fingerprint(
            train_rows,
            validation_rows,
            seed=seed,
            validation_fraction=validation_fraction,
        ),
    }
    return train_rows, validation_rows, metadata


def evaluation_metadata(
    rows: Sequence[dict[str, Any]],
    *,
    train_rows: Sequence[dict[str, Any]],
    validation_rows: Sequence[dict[str, Any]],
    feature_schema_version: str = "unknown",
    seed: int = 7,
    validation_fraction: float = 0.2,
) -> dict[str, Any]:
    """Build metadata that must match before model reports are compared."""

    train_groups = {group_id(row, index=i) for i, row in enumerate(train_rows)}
    validation_groups = {group_id(row, index=i) for i, row in enumerate(validation_rows)}
    overlap = train_groups & validation_groups
    if overlap:
        raise ValueError(f"group leakage detected: {sorted(overlap)[:3]}")
    return {
        "feature_schema_version": str(feature_schema_version),
        "dataset_fingerprint": dataset_fingerprint(rows, schema_version=feature_schema_version),
        "split_fingerprint": split_fingerprint(
            train_rows,
            validation_rows,
            seed=seed,
            validation_fraction=validation_fraction,
        ),
        "split_schema_version": SPLIT_SCHEMA_VERSION,
        "train_groups": sorted(train_groups),
        "validation_groups": sorted(validation_groups),
    }

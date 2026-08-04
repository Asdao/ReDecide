"""Split candidate states and rollout/rubric labels by complete replay groups.

Candidate rows from one demo are correlated.  This utility keeps every
``record_index`` together and writes explicit train/held-out files so the
evaluation command cannot accidentally score the training rows. Either
aggregate simulator rollouts or a compact ``candidate_label_v1`` sidecar may
be supplied.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

_ENGINE_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _ENGINE_ROOT.parent
for _path in (_ENGINE_ROOT / "model" / "src", _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from backend.replay_engine.training.candidate_labels import candidate_decision_key, load_candidate_labels
from backend.replay_engine.training.candidate_rollouts import load_candidate_rows

SPLIT_SCHEMA_VERSION = "candidate_split_v1"


def _load_rollouts(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise TypeError(f"rollout line {line_number} must be an object")
            rows.append(value)
    return rows


def _key(row: dict[str, Any]) -> tuple[str, str, str]:
    return candidate_decision_key(row)


def _group(row: dict[str, Any]) -> str:
    value = row.get("group_id")
    if value is None:
        value = row.get("record_index")
    return str(value) if value is not None else str(row.get("source") or "unknown")


def _load_labels(path: str | Path) -> list[dict[str, Any]]:
    return load_candidate_labels(path)


def _state_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    groups = sorted({_group(row) for row in rows})
    return {
        "schema_version": "candidate_state_v1",
        "summary": {
            "schema_version": "candidate_state_v1",
            "kills_seen": len(rows),
            "rows_emitted": len(rows),
            "kills_skipped": 0,
            "skip_reasons": {},
            "record_groups": groups,
        },
        "rows": rows,
    }


def split_candidate_dataset(
    candidate_states_path: str | Path,
    rollout_path: str | Path | None,
    output_dir: str | Path,
    *,
    labels_path: str | Path | None = None,
    validation_fraction: float = 0.2,
    seed: int = 7,
) -> dict[str, Any]:
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    states = load_candidate_rows(candidate_states_path)
    rollouts = _load_rollouts(rollout_path) if rollout_path is not None else []
    labels = _load_labels(labels_path) if labels_path is not None else []
    if not rollouts and not labels:
        raise ValueError("either rollout_path or labels_path is required")
    groups = sorted({_group(row) for row in states})
    if len(groups) < 2:
        raise ValueError("need at least two complete replay groups for a held-out split")
    shuffled = list(groups)
    random.Random(seed).shuffle(shuffled)
    validation_count = max(1, round(len(shuffled) * validation_fraction))
    validation_count = min(len(shuffled) - 1, validation_count)
    validation_groups = set(shuffled[-validation_count:])
    train_states = [row for row in states if _group(row) not in validation_groups]
    heldout_states = [row for row in states if _group(row) in validation_groups]
    state_keys = {_key(row) for row in states}
    matched_rollouts = [row for row in rollouts if _key(row) in state_keys]
    group_by_key = {_key(row): _group(row) for row in states}
    train_rollouts = [row for row in matched_rollouts if group_by_key[_key(row)] not in validation_groups]
    heldout_rollouts = [row for row in matched_rollouts if group_by_key[_key(row)] in validation_groups]
    label_group_by_key = {_key(row): _group(row) for row in states}
    matched_labels = [row for row in labels if _key(row) in state_keys]
    train_labels = [row for row in matched_labels if label_group_by_key[_key(row)] not in validation_groups]
    heldout_labels = [row for row in matched_labels if label_group_by_key[_key(row)] in validation_groups]
    if rollouts and (not train_rollouts or not heldout_rollouts):
        raise ValueError("candidate split produced an empty train or held-out rollout set")
    if labels_path is not None and (not train_labels or not heldout_labels):
        raise ValueError("candidate split produced an empty train or held-out label set")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "train_states": output / "train_candidate_states.json",
        "heldout_states": output / "heldout_candidate_states.json",
        "train_rollouts": output / "train_candidate_rollouts.jsonl",
        "heldout_rollouts": output / "heldout_candidate_rollouts.jsonl",
        "train_labels": output / "train_candidate_labels.jsonl",
        "heldout_labels": output / "heldout_candidate_labels.jsonl",
    }
    files["train_states"].write_text(json.dumps(_state_payload(train_states), indent=2) + "\n", encoding="utf-8")
    files["heldout_states"].write_text(json.dumps(_state_payload(heldout_states), indent=2) + "\n", encoding="utf-8")
    for name, rows in (("train_rollouts", train_rollouts), ("heldout_rollouts", heldout_rollouts)):
        files[name].write_text(
            "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    for name, rows in (("train_labels", train_labels), ("heldout_labels", heldout_labels)):
        if labels_path is not None:
            files[name].write_text(
                "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in rows),
                encoding="utf-8",
            )
    manifest = {
        "schema_version": SPLIT_SCHEMA_VERSION,
        "seed": seed,
        "validation_fraction": validation_fraction,
        "group_field": "record_index",
        "train_groups": sorted(set(groups) - validation_groups),
        "heldout_groups": sorted(validation_groups),
        "train_states": len(train_states),
        "heldout_states": len(heldout_states),
        "train_rollouts": len(train_rollouts),
        "heldout_rollouts": len(heldout_rollouts),
        "train_labels": len(train_labels),
        "heldout_labels": len(heldout_labels),
    }
    (output / "candidate_split_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_states", type=Path)
    parser.add_argument("rollouts_or_output", type=Path)
    parser.add_argument("output_dir", type=Path, nargs="?")
    parser.add_argument("--labels", type=Path, default=None)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    if args.labels is not None and args.output_dir is None:
        rollout_path = None
        output_dir = args.rollouts_or_output
    elif args.output_dir is not None:
        rollout_path = args.rollouts_or_output
        output_dir = args.output_dir
    else:
        parser.error("output_dir is required unless --labels is supplied")
    print(json.dumps(split_candidate_dataset(
        args.candidate_states,
        rollout_path,
        output_dir,
        labels_path=args.labels,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SPLIT_SCHEMA_VERSION", "main", "split_candidate_dataset"]

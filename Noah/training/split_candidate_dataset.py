"""Split candidate states and rollout labels by complete replay groups.

Candidate rows from one demo are correlated.  This utility keeps every
``record_index`` together and writes explicit train/held-out files so the
evaluation command cannot accidentally score the training rows.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any

_NOAH_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _NOAH_ROOT.parent
for _path in (_NOAH_ROOT / "model" / "src", _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from Noah.training.candidate_rollouts import load_candidate_rows

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
    group = row.get("record_index")
    group_value = str(group) if group is not None else str(row.get("source") or "")
    return (
        group_value,
        str((row.get("event") or {}).get("event_id") or row.get("event_id") or ""),
        str(row.get("actor_id") or ""),
    )


def _group(row: dict[str, Any]) -> str:
    value = row.get("record_index")
    return str(value) if value is not None else str(row.get("source") or "unknown")


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
    rollout_path: str | Path,
    output_dir: str | Path,
    *,
    validation_fraction: float = 0.2,
    seed: int = 7,
) -> dict[str, Any]:
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    states = load_candidate_rows(candidate_states_path)
    rollouts = _load_rollouts(rollout_path)
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
    if not train_rollouts or not heldout_rollouts:
        raise ValueError("candidate split produced an empty train or held-out rollout set")
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    files = {
        "train_states": output / "train_candidate_states.json",
        "heldout_states": output / "heldout_candidate_states.json",
        "train_rollouts": output / "train_candidate_rollouts.jsonl",
        "heldout_rollouts": output / "heldout_candidate_rollouts.jsonl",
    }
    files["train_states"].write_text(json.dumps(_state_payload(train_states), indent=2) + "\n", encoding="utf-8")
    files["heldout_states"].write_text(json.dumps(_state_payload(heldout_states), indent=2) + "\n", encoding="utf-8")
    for name, rows in (("train_rollouts", train_rollouts), ("heldout_rollouts", heldout_rollouts)):
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
    }
    (output / "candidate_split_manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate_states", type=Path)
    parser.add_argument("rollouts", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--validation-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(split_candidate_dataset(
        args.candidate_states,
        args.rollouts,
        args.output_dir,
        validation_fraction=args.validation_fraction,
        seed=args.seed,
    ), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["SPLIT_SCHEMA_VERSION", "main", "split_candidate_dataset"]

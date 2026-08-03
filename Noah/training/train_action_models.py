"""Train action-frequency and zone-transition models from inferred labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterator

from cs2_sim.core.model import ActionFrequencyModel, ZoneTransitionModel
from Noah.training.dataset_split import dataset_fingerprint, group_id
from Noah.training.replay_repository import ReplayRepository
from Noah.training.data_paths import DATA_PATHS


ACTION_SCHEMA_VERSION = "movement_tendency_v2"


def action_map(row: dict[str, Any]) -> str:
    """Extract a map name from canonical, JSONL, or repository action rows."""

    value = row.get("map_name") or row.get("map")
    if value in (None, "") and isinstance(row.get("payload"), dict):
        payload = row["payload"]
        value = payload.get("map_name") or payload.get("map")
    return str(value or "unknown")


def action_state_key(row: dict[str, Any]) -> str:
    """Map-aware state key for movement-tendency predictions."""

    return "|".join(
        (
            action_map(row),
            str(row.get("side") or "unknown").lower(),
            str(row.get("current_zone") or "unknown"),
        )
    )


def train_action_models(
    input_path: Path | None,
    action_output: Path,
    transition_output: Path,
    *,
    database_path: Path | None = None,
    metrics_output: Path | None = None,
) -> dict[str, Any]:
    action_model = ActionFrequencyModel()
    transition_model = ZoneTransitionModel()
    rows: list[dict[str, Any]] = []
    if database_path is not None:
        with ReplayRepository(database_path) as repository:
            rows = list(repository.iter_actions())
    else:
        if input_path is None:
            raise ValueError("input_path is required when database_path is not provided")
        with input_path.open(encoding="utf-8") as source:
            lines: Iterator[str] = source
            for line in lines:
                if not line.strip():
                    continue
                rows.append(json.loads(line))
    rows_seen = len(rows)
    if rows_seen == 0:
        raise ValueError("action JSONL contains no rows")
    action_output.parent.mkdir(parents=True, exist_ok=True)
    transition_output.parent.mkdir(parents=True, exist_ok=True)
    for row in rows:
        side = str(row.get("side") or "unknown")
        current_zone = str(row.get("current_zone") or "unknown")
        next_zone = str(row.get("next_zone") or "unknown")
        action_model.observe(action_state_key(row), str(row.get("action") or "unknown"))
        transition_model.observe(current_zone, next_zone, side=side, map_name=action_map(row))
    action_model.save(action_output)
    transition_model.save(transition_output)
    metrics = {
        "schema_version": ACTION_SCHEMA_VERSION,
        "rows": rows_seen,
        "action_states": action_model.state_count,
        "transition_states": transition_model.state_count,
        "actions": list(action_model.actions),
        "zones": list(transition_model.zones),
        "map_names": sorted({action_map(row) for row in rows}),
        "dataset_fingerprint": dataset_fingerprint(rows, schema_version=ACTION_SCHEMA_VERSION),
        "role": "deployed_movement_tendency_model",
        "groups": sorted({group_id(row, index=index) for index, row in enumerate(rows)}),
    }
    if metrics_output is not None:
        metrics_output.parent.mkdir(parents=True, exist_ok=True)
        metrics_output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DATA_PATHS.private_processed / "player_actions.jsonl")
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--action-output", type=Path, default=Path("model/artifacts/action_frequency.json"))
    parser.add_argument("--transition-output", type=Path, default=Path("model/artifacts/zone_transitions.json"))
    parser.add_argument("--metrics", type=Path, default=Path("model/artifacts/action_model_metrics.json"))
    args = parser.parse_args()
    metrics = train_action_models(
        args.input,
        args.action_output,
        args.transition_output,
        database_path=args.database,
        metrics_output=args.metrics,
    )
    print(f"[actions] rows={metrics['rows']} states={metrics['action_states']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

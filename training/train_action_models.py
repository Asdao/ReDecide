"""Train action-frequency and zone-transition models from inferred labels."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from cs2_sim.core.model import ActionFrequencyModel, ZoneTransitionModel
from training.replay_repository import ReplayRepository


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
    rows_seen = 0
    if database_path is not None:
        with ReplayRepository(database_path) as repository:
            for row in repository.iter_actions():
                side = str(row.get("side") or "unknown")
                current_zone = str(row.get("current_zone") or "unknown")
                next_zone = str(row.get("next_zone") or "unknown")
                action_model.observe(f"{side}|{current_zone}", str(row.get("action") or "unknown"))
                transition_model.observe(current_zone, next_zone, side=side)
                rows_seen += 1
    else:
        if input_path is None:
            raise ValueError("input_path is required when database_path is not provided")
        rows_seen = 0
        for line in input_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            side = str(row.get("side") or "unknown")
            current_zone = str(row.get("current_zone") or "unknown")
            next_zone = str(row.get("next_zone") or "unknown")
            action_model.observe(f"{side}|{current_zone}", str(row.get("action") or "unknown"))
            transition_model.observe(current_zone, next_zone, side=side)
            rows_seen += 1
    if rows_seen == 0:
        raise ValueError("action JSONL contains no rows")
    action_output.parent.mkdir(parents=True, exist_ok=True)
    transition_output.parent.mkdir(parents=True, exist_ok=True)
    action_model.save(action_output)
    transition_model.save(transition_output)
    metrics = {
        "rows": rows_seen,
        "action_states": action_model.state_count,
        "transition_states": transition_model.state_count,
        "actions": list(action_model.actions),
        "zones": list(transition_model.zones),
    }
    if metrics_output is not None:
        metrics_output.parent.mkdir(parents=True, exist_ok=True)
        metrics_output.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path("data/full/processed/player_actions.jsonl"))
    parser.add_argument("--database", type=Path, default=None)
    parser.add_argument("--action-output", type=Path, default=Path("models/action_frequency.json"))
    parser.add_argument("--transition-output", type=Path, default=Path("models/zone_transitions.json"))
    parser.add_argument("--metrics", type=Path, default=Path("models/action_model_metrics.json"))
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

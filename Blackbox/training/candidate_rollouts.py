"""Generate compact multi-seed simulator outcomes for candidate states.

The input rows come from :mod:`Blackbox.training.candidate_states` and contain a
strictly pre-event simulator state.  This module deliberately stores only
aggregate wins/losses per legal action; event traces are not training data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

# Keep the direct CLI usable from a clean checkout.
_NOAH_ROOT = Path(__file__).resolve().parents[1]
_WORKSPACE_ROOT = _NOAH_ROOT.parent
for _path in (_NOAH_ROOT / "model" / "src", _WORKSPACE_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from cs2_sim.actions import Action, ActionType
from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim.config import SimConfig
from cs2_sim.policy import ActionPolicy
from cs2_sim.simulator import Simulator
from cs2_sim.state import BombState, GameState, PlayerState, Team

from Blackbox.training.candidate_states import CANDIDATE_STATE_SCHEMA_VERSION

ROLLOUT_SCHEMA_VERSION = "candidate_rollout_v1"


class _FirstActionPolicy(ActionPolicy):
    def __init__(self, player_id: str, action: Action, seed: int) -> None:
        self.player_id = player_id
        self.action = action
        self.baseline = BaselinePolicy(seed=seed)
        self.used = False

    def choose_action(
        self,
        state: GameState,
        player_id: str,
        legal: tuple[Action, ...],
    ) -> Action:
        if player_id == self.player_id and not self.used and self.action in legal:
            self.used = True
            return self.action
        return self.baseline.choose_action(state, player_id, legal)


def _action_from_name(name: str) -> Action:
    action_name, separator, target = str(name).partition(":")
    try:
        action_type = ActionType(action_name)
    except ValueError as exc:
        raise ValueError(f"unknown candidate action: {name}") from exc
    return Action(action_type, target if separator else None)


def deserialize_state(payload: Mapping[str, Any]) -> GameState:
    """Restore only the simulator state fields emitted by candidate_states."""

    players: dict[str, PlayerState] = {}
    for raw in payload.get("players") or ():
        if not isinstance(raw, Mapping):
            continue
        player_id = str(raw.get("player_id") or "")
        if not player_id:
            continue
        players[player_id] = PlayerState(
            player_id=player_id,
            team=Team(str(raw.get("team") or "t").lower()),
            zone=str(raw.get("zone") or "unknown"),
            health=max(0, min(100, int(raw.get("health", 100)))),
            alive=bool(raw.get("alive", True)),
            has_bomb=bool(raw.get("has_bomb", False)),
            utility_count=max(0, int(raw.get("utility_count", 0))),
        )
    if not players:
        raise ValueError("candidate state contains no players")
    bomb_state = BombState(str(payload.get("bomb_state") or BombState.NONE.value))
    bomb_time = payload.get("bomb_time_remaining")
    return GameState(
        players,
        bomb_state=bomb_state,
        bomb_site=str(payload.get("bomb_site") or "A_SITE"),
        bomb_carrier=payload.get("bomb_carrier"),
        bomb_zone=payload.get("bomb_zone"),
        bomb_time_remaining=None if bomb_time is None else float(bomb_time),
        time_seconds=float(payload.get("time_seconds") or 0.0),
    )


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, Mapping) and isinstance(payload.get("rows"), Sequence):
        return [dict(row) for row in payload["rows"] if isinstance(row, Mapping)]
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes)):
        return [dict(row) for row in payload if isinstance(row, Mapping)]
    if isinstance(payload, Mapping):
        return [dict(payload)]
    raise TypeError("candidate input must contain candidate-state objects")


def load_candidate_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    text = source.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"candidate input is empty: {source}")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = [json.loads(line) for line in text.splitlines() if line.strip()]
    rows = _rows_from_payload(payload)
    for row in rows:
        if row.get("schema_version") != CANDIDATE_STATE_SCHEMA_VERSION:
            raise ValueError("candidate input has an unsupported state schema")
    return rows


def simulate_candidate_row(
    row: Mapping[str, Any],
    *,
    rollouts: int = 8,
    seed: int = 7,
    sim_config: SimConfig | None = None,
) -> list[dict[str, Any]]:
    """Aggregate simulator outcomes for every legal action in one row."""

    if rollouts <= 0:
        raise ValueError("rollouts must be positive")
    player_id = str(row.get("actor_id") or "")
    state = deserialize_state(row.get("state") or {})
    player = state.player(player_id)
    action_names = [str(name) for name in row.get("legal_actions") or ()]
    if not action_names:
        return []
    config = sim_config or SimConfig(round_time_seconds=20.0, bomb_time_seconds=10.0)
    results: list[dict[str, Any]] = []
    for action_name in action_names:
        action = _action_from_name(action_name)
        wins = 0
        losses = 0
        player_survivals = 0
        for offset in range(rollouts):
            policy = _FirstActionPolicy(player_id, action, seed + offset)
            result = Simulator(config, policy).run(state)
            if result.winner is player.team:
                wins += 1
            else:
                losses += 1
            final_player = result.final_state.players.get(player_id)
            player_survivals += int(final_player is not None and final_player.alive)
        results.append(
            {
                "schema_version": ROLLOUT_SCHEMA_VERSION,
                "source_state_schema": row["schema_version"],
                "source": row.get("source"),
                "record_index": row.get("record_index"),
                "map_name": row.get("map_name"),
                "round_num": row.get("round_num"),
                "decision_tick": row.get("decision_tick"),
                "event_id": (row.get("event") or {}).get("event_id"),
                "actor_id": player_id,
                "state_key": row.get("state_key"),
                "action": action_name,
                "rollouts": rollouts,
                "wins": wins,
                "losses": losses,
                "round_win_probability": wins / rollouts,
                "player_survival_probability": player_survivals / rollouts,
                "round_outcome_target": "team_round_win",
                # The compact simulator currently has no weapon/damage model;
                # this is a simulator-final-state diagnostic, not a CS2 death
                # probability.  Keep the provenance explicit for trainers.
                "survival_target": "simulator_final_alive_no_combat",
            }
        )
    return results


def generate_rollouts(
    rows: Iterable[Mapping[str, Any]],
    *,
    rollouts: int = 8,
    seed: int = 7,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        if max_rows is not None and index >= max_rows:
            break
        output.extend(simulate_candidate_row(row, rollouts=rollouts, seed=seed + index * rollouts))
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="candidate-state JSON or JSONL")
    parser.add_argument("output", type=Path, help="aggregated rollout JSONL")
    parser.add_argument("--rollouts", type=int, default=8)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--max-rows", type=int, default=None)
    args = parser.parse_args()
    rows = generate_rollouts(
        load_candidate_rows(args.input),
        rollouts=args.rollouts,
        seed=args.seed,
        max_rows=args.max_rows,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        "".join(json.dumps(row, separators=(",", ":"), sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    print(json.dumps({"schema_version": ROLLOUT_SCHEMA_VERSION, "rows": len(rows)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ROLLOUT_SCHEMA_VERSION",
    "deserialize_state",
    "generate_rollouts",
    "load_candidate_rows",
    "main",
    "simulate_candidate_row",
]

"""Train a monitored bootstrap pair of CS2 models from simulator examples.

The downloaded metadata contains match-level rows but no action labels, so it
cannot yet train an action policy honestly.  This command creates labelled
candidate-action examples by evaluating the deterministic simulator.  It is a
bootstrap model, not a replacement for replay-derived training.

Run from the repository root with the source tree on ``PYTHONPATH``::

    $env:PYTHONPATH = "src"
    python -m training.train_models --states 200
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

from cs2_sim.actions import Action
from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim.config import SimConfig
from cs2_sim.core.model import FullLightGBMModel, SmallStatisticalModel, TrainingExample
from cs2_sim.policy import ActionPolicy
from cs2_sim.rules import legal_actions
from cs2_sim.simulator import Simulator
from cs2_sim.state import BombState, GameState, PlayerState, Team


class FirstActionPolicy(ActionPolicy):
    """Force one candidate for one player, then use the baseline policy."""

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


def _make_state(rng: random.Random, index: int) -> tuple[GameState, str]:
    """Create a compact state with a meaningful plant/defuse decision."""

    planted = index % 3 == 0
    carried = not planted and index % 2 == 0
    bomb_state = BombState.PLANTED if planted else BombState.CARRIED if carried else BombState.NONE
    zones = ("T_SPAWN", "A_MAIN", "B_MAIN", "MID", "A_SITE", "B_SITE", "CT_SPAWN")
    players: dict[str, PlayerState] = {}
    for team, prefix in ((Team.T, "t"), (Team.CT, "ct")):
        for number in range(1, 4):
            player_id = f"{prefix}{number}"
            zone = "A_SITE" if planted and team is Team.CT and number == 1 else rng.choice(zones)
            if carried and team is Team.T and number == 1:
                zone = "A_SITE"
            players[player_id] = PlayerState(
                player_id,
                team,
                zone,
                health=rng.randint(40, 100),
                utility_count=rng.randint(0, 2),
                has_bomb=carried and team is Team.T and number == 1,
            )
    state = GameState(
        players,
        bomb_state=bomb_state,
        bomb_site="A_SITE",
        bomb_time_remaining=rng.uniform(5.0, 10.0) if planted else None,
    )
    return state, "ct1" if planted else "t1"


def generate_examples(state_count: int, seed: int) -> list[list[TrainingExample]]:
    rng = random.Random(seed)
    config = SimConfig(round_time_seconds=20.0, bomb_time_seconds=10.0)
    groups: list[list[TrainingExample]] = []
    started = time.perf_counter()
    progress_step = max(1, state_count // 10)
    for index in range(state_count):
        state, player_id = _make_state(rng, index)
        candidates = legal_actions(state, player_id)
        group: list[TrainingExample] = []
        for action in candidates:
            policy = FirstActionPolicy(player_id, action, seed + index)
            result = Simulator(config, policy).run(state)
            player_team = state.player(player_id).team
            group.append(
                TrainingExample(
                    state=state,
                    player_id=player_id,
                    action=action,
                    success=result.winner is player_team,
                )
            )
        groups.append(group)
        if (index + 1) % progress_step == 0 or index + 1 == state_count:
            elapsed = time.perf_counter() - started
            examples = sum(len(group) for group in groups)
            print(
                f"[generate] {index + 1}/{state_count} states, "
                f"{examples} examples, {elapsed:.1f}s",
                flush=True,
            )
    return groups


def _metrics(model: FullLightGBMModel, examples: list[TrainingExample]) -> dict[str, float]:
    probabilities = [model.predict_probability(x.state, x.player_id, x.action) for x in examples]
    labels = [float(x.success) for x in examples]
    eps = 1e-7
    log_loss = -sum(
        label * math.log(max(eps, p)) + (1.0 - label) * math.log(max(eps, 1.0 - p))
        for p, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    brier = sum((p - label) ** 2 for p, label in zip(probabilities, labels, strict=True)) / len(labels)
    accuracy = sum((p >= 0.5) == bool(label) for p, label in zip(probabilities, labels, strict=True)) / len(labels)
    return {"log_loss": log_loss, "brier": brier, "accuracy": accuracy}


def small_decision_metrics(
    model: SmallStatisticalModel,
    groups: list[list[TrainingExample]],
    *,
    seed: int,
) -> dict[str, float]:
    """Compare small-model calls with rules, baseline policy, and simulator outcomes."""

    legal_calls = 0
    baseline_matches = 0
    chosen_successes = 0
    opportunities = 0
    successful_opportunities = 0
    for index, group in enumerate(groups):
        if not group:
            continue
        state = group[0].state
        player_id = group[0].player_id
        legal = tuple(example.action for example in group)
        chosen = model.choose_action(state, player_id, legal)
        legal_calls += int(chosen in legal)
        baseline = BaselinePolicy(seed=seed + index).choose_action(state, player_id, legal)
        baseline_matches += int(chosen == baseline)
        chosen_example = next(example for example in group if example.action == chosen)
        chosen_successes += int(chosen_example.success)
        if any(example.success for example in group):
            opportunities += 1
            successful_opportunities += int(chosen_example.success)
    total = len(groups)
    return {
        "legal_action_rate": legal_calls / total if total else 0.0,
        "baseline_agreement": baseline_matches / total if total else 0.0,
        "chosen_action_success_rate": chosen_successes / total if total else 0.0,
        "oracle_opportunity_accuracy": (
            successful_opportunities / opportunities if opportunities else 0.0
        ),
        "evaluated_states": float(total),
        "states_with_winning_action": float(opportunities),
    }


def train(state_count: int, seed: int, output_dir: Path) -> None:
    groups = generate_examples(state_count, seed)
    rng = random.Random(seed)
    rng.shuffle(groups)
    split = max(1, int(len(groups) * 0.8))
    train_groups = groups[:split]
    validation_groups = groups[split:]
    train_examples = [example for group in train_groups for example in group]
    validation_examples = [example for group in validation_groups for example in group]
    print(
        f"[split] train={len(train_examples)} validation={len(validation_examples)}",
        flush=True,
    )

    small = SmallStatisticalModel()
    for example in train_examples:
        small.observe(
            example.state,
            example.player_id,
            example.action,
            success=example.success,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    small_path = output_dir / "small_statistical.json"
    small.save(small_path)
    small_metrics = small_decision_metrics(small, validation_groups, seed=seed)
    print(f"[small] saved {small_path}", flush=True)
    print(f"[small] validation {json.dumps(small_metrics, sort_keys=True)}", flush=True)

    full = FullLightGBMModel(small_model=small)
    started = time.perf_counter()
    print("[full] training LightGBM...", flush=True)
    full.fit(train_examples, validation_examples=validation_examples, num_boost_round=80)
    print(f"[full] trained in {time.perf_counter() - started:.1f}s", flush=True)
    full_path = output_dir / "full_lightgbm.txt"
    full.save(full_path)
    metrics = _metrics(full, validation_examples)
    print(f"[full] validation {json.dumps(metrics, sort_keys=True)}", flush=True)
    (output_dir / "bootstrap_metrics.json").write_text(
        json.dumps(
            {
                "source": "simulator_bootstrap",
                "states": state_count,
                "train_examples": len(train_examples),
                "validation_examples": len(validation_examples),
                "small_decision_metrics": small_metrics,
                "full_candidate_metrics": metrics,
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--states", type=int, default=200)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output", type=Path, default=Path("models"))
    args = parser.parse_args()
    if args.states <= 0:
        raise ValueError("--states must be positive")
    train(args.states, args.seed, args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

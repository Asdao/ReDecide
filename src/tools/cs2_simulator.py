"""
CS2 Simulator Tool for baseline game policy simulations.
"""

from typing import Dict, Any, Optional
from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim import SimConfig
from cs2_sim.simulator import Simulator
from cs2_sim.state import GameState


def run_cs2_simulation(state: GameState, seed: int = 7) -> Dict[str, Any]:
    """Run a deterministic CS2 game state simulation."""
    simulator = Simulator(SimConfig(), BaselinePolicy(seed=seed))
    result = simulator.run(state)
    return {
        "winner": result.winner.name if result.winner else None,
        "time_seconds": result.final_state.time_seconds,
        "events_count": len(result.events),
        "events": [
            {
                "time_seconds": e.time_seconds,
                "kind": e.kind,
                "player_id": e.player_id
            }
            for e in result.events
        ]
    }

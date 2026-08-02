from cs2_sim.actions import ActionType
from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim.config import SimConfig
from cs2_sim.simulator import Simulator
from cs2_sim.state import BombState, GameState, PlayerState, Team


def build_example_state() -> GameState:
    """Create a small deterministic scenario for local experimentation."""
    players = {
        "t1": PlayerState("t1", Team.T, zone="A_SITE", has_bomb=True),
        "t2": PlayerState("t2", Team.T, zone="A_MAIN"),
        "ct1": PlayerState("ct1", Team.CT, zone="CT_SPAWN"),
        "ct2": PlayerState("ct2", Team.CT, zone="A_SITE"),
    }
    return GameState(players=players, bomb_state=BombState.CARRIED, bomb_site="A_SITE")


def main() -> None:
    simulator = Simulator(SimConfig(), BaselinePolicy(seed=7))
    result = simulator.run(build_example_state())
    print(f"winner={result.winner} time={result.final_state.time_seconds:.2f}s")
    print(f"events={len(result.events)}")
    for event in result.events:
        print(f"{event.time_seconds:6.2f}s {event.kind}: {event.player_id or '-'}")


if __name__ == "__main__":
    main()

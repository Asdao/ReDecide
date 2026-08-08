"""
RE:DECIDE AI Agent Main Entry Point.

Run local simulation demo:
    python main.py

Run FastAPI API server:
    python main.py --server
"""

import sys
import argparse
from pathlib import Path

# Ensure repository packages are on sys.path
REPO_ROOT = Path(__file__).resolve().parent
PATHS_TO_ADD = [
    REPO_ROOT,
    REPO_ROOT / "src",
    REPO_ROOT / "backend",
    REPO_ROOT / "backend" / "replay_engine" / "model" / "src",
    REPO_ROOT / "backend" / "replay_engine" / "extractor" / "src",
]
for p in PATHS_TO_ADD:
    p_str = str(p)
    if p.is_dir() and p_str not in sys.path:
        sys.path.insert(0, p_str)

from cs2_sim.baseline_policy import BaselinePolicy
from cs2_sim import SimConfig
from cs2_sim.simulator import Simulator
from cs2_sim.state import BombState, GameState, PlayerState, Team
from src.utils.logger import get_logger

logger = get_logger("redecide_main")


def build_example_state() -> GameState:
    """Create a small deterministic scenario for local experimentation."""
    players = {
        "t1": PlayerState("t1", Team.T, zone="A_SITE", has_bomb=True),
        "t2": PlayerState("t2", Team.T, zone="A_MAIN"),
        "ct1": PlayerState("ct1", Team.CT, zone="CT_SPAWN"),
        "ct2": PlayerState("ct2", Team.CT, zone="A_SITE"),
    }
    return GameState(players=players, bomb_state=BombState.CARRIED, bomb_site="A_SITE")


def run_demo() -> None:
    """Execute the CS2 Baseline Simulator demo."""
    logger.info("Starting RE:DECIDE CS2 Simulator Demo...")
    simulator = Simulator(SimConfig(), BaselinePolicy(seed=7))
    result = simulator.run(build_example_state())
    print("=" * 60)
    print(f"RE:DECIDE Agent Simulation Result")
    print("=" * 60)
    print(f"Winner       : {result.winner}")
    print(f"Final Time   : {result.final_state.time_seconds:.2f}s")
    print(f"Total Events : {len(result.events)}")
    print("-" * 60)
    for event in result.events:
        print(f"  {event.time_seconds:6.2f}s | {event.kind:<20} | {event.player_id or '-'}")
    print("=" * 60)


def start_server(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start the FastAPI backend server."""
    import uvicorn
    logger.info(f"Starting FastAPI server on http://{host}:{port}...")
    uvicorn.run("backend.app.main:app", host=host, port=port, reload=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="RE:DECIDE AI Agent Launcher")
    parser.add_argument("--server", action="store_true", help="Start the FastAPI backend server")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address for the server")
    parser.add_argument("--port", type=int, default=8000, help="Port for the server")
    args = parser.parse_args()

    if args.server:
        start_server(host=args.host, port=args.port)
    else:
        run_demo()


if __name__ == "__main__":
    main()

"""Fixed JSON-in/JSON-out boundary for the CS2 simulator.

The bridge is intentionally a small, dependency-free process boundary.  It
accepts one JSON request on stdin and emits exactly one JSON envelope on
stdout.  Diagnostic logging is never written to stdout.  Invoke it directly
from the repository root, for example::

    python agent-harness/src/cs2_sim/agent_bridge.py <<<'{"version":1,...}'

The request and response schemas are versioned independently of the Python
simulator internals so a TypeScript tool adapter can validate the boundary.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_MAX_EVENTS = 100
MAX_EVENTS = 1_000
MIN_SEED = -(2**31)
MAX_SEED = 2**31 - 1

_TOP_LEVEL_FIELDS = frozenset({"version", "operation", "arguments"})
_ARGUMENT_FIELDS = frozenset({"seed", "scenario", "policy", "max_events"})
_SCENARIOS = frozenset({"example", "planted"})
_POLICIES = frozenset({"baseline", "bayesian"})


def _project_source_dir() -> Path:
    """Find the repository simulator source tree from this sibling package."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "model" / "src" / "cs2_sim"
        if (candidate / "simulator.py").is_file() and candidate != here.parent:
            return candidate.parent
    # This fallback is useful when a test copies the bridge file to a temp dir;
    # importing then produces the normal stable INTERNAL_ERROR envelope.
    return here.parents[3] / "model" / "src"


def _ensure_simulator_importable() -> None:
    source = _project_source_dir()
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


_ensure_simulator_importable()

from cs2_sim.baseline_policy import BaselinePolicy  # noqa: E402
from cs2_sim.bayesian_policy import BayesianPolicy  # noqa: E402
from cs2_sim.config import SimConfig  # noqa: E402
from cs2_sim.simulator import Simulator  # noqa: E402
from cs2_sim.state import BombState, GameState, PlayerState, Team  # noqa: E402


def _error(code: str, message: str) -> dict[str, Any]:
    """Build an intentionally non-sensitive failure envelope."""

    return {
        "version": PROTOCOL_VERSION,
        "ok": False,
        "error": {"code": code, "message": message},
    }


def _success(data: Mapping[str, Any]) -> dict[str, Any]:
    return {"version": PROTOCOL_VERSION, "ok": True, "data": dict(data)}


def _is_int(value: Any) -> bool:
    # bool is an int subclass but is never a valid protocol integer.
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_request(request: Mapping[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    unknown = set(request) - _TOP_LEVEL_FIELDS
    if unknown:
        return None, _error("INVALID_REQUEST", "Request contains unsupported fields.")
    version = request.get("version")
    if not _is_int(version):
        return None, _error("INVALID_REQUEST", "version must be an integer.")
    if version != PROTOCOL_VERSION:
        return None, _error("UNSUPPORTED_VERSION", "Unsupported protocol version.")
    operation = request.get("operation")
    if not isinstance(operation, str) or not operation:
        return None, _error("INVALID_REQUEST", "operation must be a non-empty string.")
    if operation != "simulate_round":
        return None, _error("UNKNOWN_OPERATION", "Unknown operation.")
    arguments = request.get("arguments", {})
    if not isinstance(arguments, Mapping):
        return None, _error("INVALID_ARGUMENTS", "arguments must be an object.")
    unknown_args = set(arguments) - _ARGUMENT_FIELDS
    if unknown_args:
        return None, _error("INVALID_ARGUMENTS", "Arguments contain unsupported fields.")

    seed = arguments.get("seed", 0)
    if not _is_int(seed) or not MIN_SEED <= seed <= MAX_SEED:
        return None, _error("INVALID_SEED", "seed must be a bounded integer.")
    scenario = arguments.get("scenario", "example")
    if not isinstance(scenario, str) or scenario not in _SCENARIOS:
        return None, _error("INVALID_SCENARIO", "Unknown scenario.")
    policy = arguments.get("policy", "baseline")
    if not isinstance(policy, str) or policy not in _POLICIES:
        return None, _error("INVALID_POLICY", "Unknown policy.")
    max_events = arguments.get("max_events", DEFAULT_MAX_EVENTS)
    if not _is_int(max_events) or not 1 <= max_events <= MAX_EVENTS:
        return None, _error("LIMIT_EXCEEDED", "max_events is outside the allowed range.")
    return {
        "seed": seed,
        "scenario": scenario,
        "policy": policy,
        "max_events": max_events,
    }, None


def _example_state() -> GameState:
    return GameState(
        players={
            "t1": PlayerState("t1", Team.T, zone="A_SITE", has_bomb=True),
            "t2": PlayerState("t2", Team.T, zone="A_MAIN"),
            "ct1": PlayerState("ct1", Team.CT, zone="CT_SPAWN"),
            "ct2": PlayerState("ct2", Team.CT, zone="A_SITE"),
        },
        bomb_state=BombState.CARRIED,
        bomb_site="A_SITE",
    )


def _planted_state() -> GameState:
    return GameState(
        players={
            "t1": PlayerState("t1", Team.T, zone="A_MAIN"),
            "t2": PlayerState("t2", Team.T, zone="A_SITE"),
            "ct1": PlayerState("ct1", Team.CT, zone="A_SITE"),
            "ct2": PlayerState("ct2", Team.CT, zone="CT_SPAWN"),
        },
        bomb_state=BombState.PLANTED,
        bomb_site="A_SITE",
        bomb_time_remaining=20.0,
    )


def _build_state(scenario: str) -> GameState:
    if scenario == "example":
        return _example_state()
    if scenario == "planted":
        return _planted_state()
    # Validation prevents this branch, but retaining a defensive error keeps
    # future edits from silently selecting a scenario.
    raise ValueError("unknown scenario")


def _build_policy(name: str, seed: int):
    if name == "baseline":
        return BaselinePolicy(seed=seed)
    if name == "bayesian":
        return BayesianPolicy(seed=seed)
    raise ValueError("unknown policy")


def _event_to_json(event: Any) -> dict[str, Any]:
    details = dict(sorted(event.details.items()))
    return {
        "time_seconds": float(event.time_seconds),
        "kind": event.kind,
        "player_id": event.player_id,
        "details": details,
    }


def _state_summary(state: GameState) -> dict[str, Any]:
    players = {
        player_id: {
            "team": player.team.value,
            "zone": player.zone,
            "health": player.health,
            "alive": player.alive,
        }
        for player_id, player in sorted(state.players.items())
    }
    return {
        "time_seconds": float(state.time_seconds),
        "bomb_state": state.bomb_state.value,
        "bomb_time_remaining": state.bomb_time_remaining,
        "players": players,
    }


def _run_simulation(arguments: Mapping[str, Any]) -> dict[str, Any]:
    seed = int(arguments["seed"])
    scenario = str(arguments["scenario"])
    policy_name = str(arguments["policy"])
    max_events = int(arguments["max_events"])
    state = _build_state(scenario)
    result = Simulator(SimConfig(), _build_policy(policy_name, seed)).run(state)
    serialized = [_event_to_json(event) for event in result.events]
    # Keep outcome-changing events useful for explanation while enforcing an
    # explicit output bound.  The full count remains available for metrics.
    # If no such event exists (for example, a very short custom future
    # scenario), fall back to the chronological prefix.
    key_events = [
        event
        for event in serialized
        if event["kind"] in {"bomb_detonated", "action_rejected"}
        or event["details"].get("action") in {"plant", "defuse"}
    ]
    if not key_events:
        key_events = serialized
    key_events = key_events[:max_events]
    return {
        "seed": seed,
        "scenario": scenario,
        "policy": policy_name,
        "winner": result.winner.value if result.winner is not None else None,
        "duration_seconds": float(result.final_state.time_seconds),
        "event_count": len(serialized),
        "events_truncated": len(serialized) > max_events,
        "key_events": key_events,
        "final_state": _state_summary(result.final_state),
    }


def handle_request(raw: str | bytes | Mapping[str, Any]) -> dict[str, Any]:
    """Parse and execute one request without raising protocol-facing errors."""

    try:
        if isinstance(raw, bytes):
            if len(raw) > MAX_REQUEST_BYTES:
                return _error("LIMIT_EXCEEDED", "Request exceeds the size limit.")
            try:
                raw = raw.decode("utf-8")
            except UnicodeDecodeError:
                return _error("INVALID_JSON", "Input is not valid UTF-8 JSON.")
        if isinstance(raw, str):
            try:
                request_bytes = len(raw.encode("utf-8"))
            except UnicodeEncodeError:
                return _error("INVALID_JSON", "Input is not valid UTF-8 JSON.")
            if request_bytes > MAX_REQUEST_BYTES:
                return _error("LIMIT_EXCEEDED", "Request exceeds the size limit.")
            try:
                request = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                return _error("INVALID_JSON", "Input is not valid JSON.")
        else:
            request = raw
        if not isinstance(request, Mapping):
            return _error("INVALID_REQUEST", "Request must be a JSON object.")
        arguments, error = _validate_request(request)
        if error is not None:
            return error
        assert arguments is not None
        return _success(_run_simulation(arguments))
    except Exception:
        # Never expose simulator internals or tracebacks to the model.  The
        # traceback, if needed during local development, belongs on stderr.
        return _error("INTERNAL_ERROR", "The simulation could not be completed.")


def _encode_response(response: Mapping[str, Any]) -> str:
    encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) <= MAX_RESPONSE_BYTES:
        return encoded
    return json.dumps(
        _error("LIMIT_EXCEEDED", "Response exceeds the size limit."),
        separators=(",", ":"),
    )


def main() -> int:
    raw = sys.stdin.buffer.read()
    response = handle_request(raw)
    sys.stdout.write(_encode_response(response) + "\n")
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

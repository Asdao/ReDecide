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
import os
import re
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
DEFAULT_MAX_EVENTS = 100
MAX_EVENTS = 1_000
MAX_REPLAY_PATH_LENGTH = 2_048
DEFAULT_MAX_DECISIONS = 100
MAX_DECISIONS = 500
DEFAULT_MAX_TIMELINE_POINTS = 120
MAX_TIMELINE_POINTS = 500
MIN_SEED = -(2**31)
MAX_SEED = 2**31 - 1

_TOP_LEVEL_FIELDS = frozenset({"version", "operation", "arguments"})
_ARGUMENT_FIELDS = frozenset(
    {
        "seed",
        "scenario",
        "policy",
        "max_events",
        "replay_path",
        "max_decisions",
        "max_timeline_points",
        "sample_every",
        "version",
        "decision_id",
    }
)
_SCENARIOS = frozenset({"example", "planted"})
_POLICIES = frozenset({"baseline", "bayesian"})
_REPLAY_SUFFIXES = frozenset({".dem", ".json", ".jsonl"})


def _project_source_dir() -> Path:
    """Find the repository simulator source tree from this sibling package."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        for relative in (Path("model/src/cs2_sim"), Path("Blackbox/model/src/cs2_sim")):
            candidate = parent / relative
            if (candidate / "simulator.py").is_file() and candidate != here.parent:
                return candidate.parent
    # This fallback is useful when a test copies the bridge file to a temp dir;
    # importing then produces the normal stable INTERNAL_ERROR envelope.
    return here.parents[3] / "Blackbox" / "model" / "src"


def _ensure_simulator_importable() -> None:
    source = _project_source_dir()
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))


_ensure_simulator_importable()

from cs2_sim.baseline_policy import BaselinePolicy  # noqa: E402
from cs2_sim.bayesian_policy import BayesianPolicy  # noqa: E402
from cs2_sim import SimConfig  # noqa: E402
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
    arguments = request.get("arguments", {})
    if not isinstance(arguments, Mapping):
        return None, _error("INVALID_ARGUMENTS", "arguments must be an object.")
    unknown_args = set(arguments) - _ARGUMENT_FIELDS
    if unknown_args:
        return None, _error("INVALID_ARGUMENTS", "Arguments contain unsupported fields.")

    if operation == "analyze_replay":
        replay_path = arguments.get("replay_path")
        if not isinstance(replay_path, str) or not replay_path.strip():
            return None, _error("INVALID_REPLAY_PATH", "replay_path must be a non-empty path.")
        if len(replay_path) > MAX_REPLAY_PATH_LENGTH:
            return None, _error("LIMIT_EXCEEDED", "replay_path is too long.")
        source = Path(replay_path).expanduser()
        if source.suffix.lower() not in _REPLAY_SUFFIXES:
            return None, _error("INVALID_REPLAY_PATH", "replay_path must point to a .dem, .json, or .jsonl file.")
        if not source.is_file():
            return None, _error("REPLAY_NOT_FOUND", "Replay file does not exist.")
        allowed_replay = os.environ.get("HARNESS_REPLAY_FILE", "").strip()
        if allowed_replay and source.resolve() != Path(allowed_replay).expanduser().resolve():
            return None, _error("REPLAY_NOT_ALLOWED", "Replay path is not the approved input for this session.")
        max_decisions = arguments.get("max_decisions", DEFAULT_MAX_DECISIONS)
        if not _is_int(max_decisions) or not 1 <= max_decisions <= MAX_DECISIONS:
            return None, _error("LIMIT_EXCEEDED", "max_decisions is outside the allowed range.")
        max_timeline_points = arguments.get("max_timeline_points", DEFAULT_MAX_TIMELINE_POINTS)
        if not _is_int(max_timeline_points) or not 1 <= max_timeline_points <= MAX_TIMELINE_POINTS:
            return None, _error("LIMIT_EXCEEDED", "max_timeline_points is outside the allowed range.")
        sample_every = arguments.get("sample_every", 8)
        if not _is_int(sample_every) or not 1 <= sample_every <= 256:
            return None, _error("LIMIT_EXCEEDED", "sample_every is outside the allowed range.")
        version = arguments.get("version")
        if version is not None and (not isinstance(version, str) or not 0 < len(version) <= 32):
            return None, _error("INVALID_VERSION", "version must be a short string.")
        decision_id = arguments.get("decision_id")
        if decision_id is not None and (not isinstance(decision_id, str) or not 0 < len(decision_id) <= 256):
            return None, _error("INVALID_DECISION", "decision_id must be a short string.")
        return {
            "replay_path": str(source.resolve()),
            "max_decisions": max_decisions,
            "max_timeline_points": max_timeline_points,
            "sample_every": sample_every,
            "version": version,
            "decision_id": decision_id,
        }, None

    if operation != "simulate_round":
        return None, _error("UNKNOWN_OPERATION", "Unknown operation.")

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


def _project_repository_root() -> Path:
    """Find the repository root containing the Blackbox package."""

    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "Blackbox" / "harness.py").is_file():
            return parent
    return here.parents[3]


def _ensure_noah_importable() -> None:
    root = _project_repository_root()
    for source in (root, root / "Blackbox" / "model" / "src", root / "Blackbox" / "extractor" / "src"):
        if str(source) not in sys.path:
            sys.path.insert(0, str(source))


def _pipeline_result(
    replay: Mapping[str, Any],
    arguments: Mapping[str, Any],
    *,
    decision_id: str | None,
) -> dict[str, Any]:
    from backend.app.replay.pipeline import stream_replay_pipeline

    final = None
    for update in stream_replay_pipeline(
        replay,
        version=arguments.get("version"),
        sample_every=int(arguments["sample_every"]),
        max_decisions=int(arguments["max_decisions"]),
        max_timeline_points=int(arguments["max_timeline_points"]),
        decision_id=decision_id,
    ):
        if update.get("done") is True:
            final = update.get("result")
    if not isinstance(final, Mapping):
        raise RuntimeError("replay pipeline did not produce a final result")
    return dict(final)


def _model_identity_replacements(
    result: Mapping[str, Any],
) -> tuple[dict[str, str], dict[str, str]]:
    """Build deterministic aliases and opaque decision references for Pi."""

    player_ids: set[str] = set()
    display_names: dict[str, str] = {}

    def add_player(player_id: Any, display_name: Any = None) -> None:
        if player_id in (None, ""):
            return
        original = str(player_id)
        player_ids.add(original)
        if display_name not in (None, ""):
            display_names.setdefault(original, str(display_name))

    for player in result.get("players", []):
        if isinstance(player, Mapping):
            add_player(player.get("player_id"), player.get("display_name"))
    for candidate in result.get("decision_candidates", []):
        if isinstance(candidate, Mapping):
            add_player(candidate.get("player_id"), candidate.get("display_name"))
            add_player(candidate.get("opponent_id"))
    selected = result.get("selected_decision")
    if isinstance(selected, Mapping):
        add_player(selected.get("player_id"), selected.get("display_name"))
        add_player(selected.get("opponent_id"))
    for event in result.get("key_events", []):
        if not isinstance(event, Mapping):
            continue
        for player_id in event.get("participant_ids", []):
            add_player(player_id)

    replacements: dict[str, str] = {}
    player_aliases: dict[str, str] = {}
    for index, player_id in enumerate(sorted(player_ids), start=1):
        alias = f"player_{index:02d}"
        player_aliases[player_id] = alias
        replacements[player_id] = alias
        display_name = display_names.get(player_id)
        if display_name:
            replacements[display_name] = f"Player {index:02d}"

    decision_aliases: dict[str, str] = {}
    candidates = [
        candidate
        for candidate in result.get("decision_candidates", [])
        if isinstance(candidate, Mapping) and candidate.get("decision_id") not in (None, "")
    ]
    for index, candidate in enumerate(candidates, start=1):
        original = str(candidate["decision_id"])
        alias = f"decision_{index:03d}"
        decision_aliases[alias] = original
        replacements[original] = alias
    return replacements, decision_aliases


def _replace_model_identifiers(value: Any, replacements: Mapping[str, str]) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _replace_model_identifiers(item, replacements)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_model_identifiers(item, replacements) for item in value]
    if isinstance(value, tuple):
        return [_replace_model_identifiers(item, replacements) for item in value]
    if not isinstance(value, str):
        return value
    exact = replacements.get(value)
    if exact is not None:
        return exact
    redacted = value
    for original in sorted(replacements, key=len, reverse=True):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(original)}(?![A-Za-z0-9])"
        redacted = re.sub(pattern, replacements[original], redacted)
    return redacted


def _redact_model_identifiers(result: Mapping[str, Any]) -> dict[str, Any]:
    replacements, _ = _model_identity_replacements(result)
    redacted = _replace_model_identifiers(dict(result), replacements)
    assert isinstance(redacted, dict)
    redacted["privacy"] = {
        "player_identifiers_redacted": True,
        "player_names_redacted": True,
        "decision_references_opaque": True,
        "alias_scope": "replay_session",
    }
    return redacted


def _run_replay_analysis(arguments: Mapping[str, Any]) -> dict[str, Any]:
    _ensure_noah_importable()
    from Blackbox.harness import load_replay_record

    replay = load_replay_record(str(arguments["replay_path"]))
    requested_decision = arguments.get("decision_id")
    final = _pipeline_result(replay, arguments, decision_id=None)
    if isinstance(requested_decision, str):
        _, decision_aliases = _model_identity_replacements(final)
        original_decisions = {
            str(candidate["decision_id"])
            for candidate in final.get("decision_candidates", [])
            if isinstance(candidate, Mapping) and candidate.get("decision_id") not in (None, "")
        }
        resolved_decision = decision_aliases.get(requested_decision, requested_decision)
        if resolved_decision not in original_decisions:
            raise ValueError("decision_id is not present in this replay")
        final = _pipeline_result(replay, arguments, decision_id=resolved_decision)
    # The reusable backend pipeline retains the full event index for the UI.
    # Pi receives only the bounded evidence/key-event projection so a normal
    # replay cannot overflow the process boundary or expose irrelevant data.
    model_result = dict(final)
    model_result.pop("events", None)
    ui_key_events = list(model_result.get("key_events", []))
    ui_win_estimator = model_result.get("win_estimator")
    model_result["key_events"] = [
        event
        for event in ui_key_events
        if isinstance(event, Mapping) and event.get("is_coaching_anchor") is True
    ]
    model_result["players"] = [
        {
            key: value
            for key, value in player.items()
            if key not in {"event_ids", "key_event_ids"}
        }
        for player in model_result.get("players", [])
        if isinstance(player, Mapping)
    ]
    if isinstance(ui_win_estimator, Mapping):
        model_result["win_estimator"] = {
            key: value
            for key, value in ui_win_estimator.items()
            if key != "timeline"
        }
        model_result["win_estimator"]["timeline_omitted_from_model"] = True
    if isinstance(model_result.get("summary"), Mapping):
        model_result["summary"] = {
            key: value
            for key, value in model_result["summary"].items()
            if key not in {"event_count", "key_event_count"}
        }
    model_result["ui_handoff"] = {
        "events_omitted_from_model": True,
        "replay_markers_omitted_from_model": True,
        "win_estimator_timeline_omitted_from_model": True,
        "selector_function": "extract_players_for_selector",
        "progress_function": "stream_replay_pipeline",
    }
    return _redact_model_identifiers(model_result)


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
        if request.get("operation") == "analyze_replay":
            return _success(_run_replay_analysis(arguments))
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

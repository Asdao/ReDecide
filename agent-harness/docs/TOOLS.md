# Tool protocol

## `analyze_replay`

Loads one server-side replay path (`.dem`, `.json`, or `.jsonl`) through the
Replay Engine extractor and returns an outcome-blind, bounded pipeline report. The
selector creates one candidate per player and round using the first damage
contact as the coaching anchor. Kills are retained in the source replay for
UI/replay markers; they are not used as the only selection filter.

```json
{
  "version": 1,
  "operation": "analyze_replay",
  "arguments": {
    "replay_path": "C:/replays/match.dem",
    "max_decisions": 100,
    "max_timeline_points": 120,
    "sample_every": 8,
    "decision_id": "r1:p7656119:t1200"
  }
}
```

The Pi response contains `players`, first-contact coaching `key_events`,
`decision_candidates`, an optional `selected_decision`, and global win-model
availability metadata. The complete player-addressable event index and CT/T
win-estimator timeline are retained by
`stream_replay_pipeline` for the future UI endpoint and deliberately omitted
from the model payload. Kill/bomb replay markers and the full win-rate timeline
are UI-only; `ui_handoff`
reports that projection. Selecting a
player filters event references, not the CT/T team probability. Future outcome
labels are stripped from the model-facing payload. Paths are read by the
bridge process and are never echoed as absolute paths. In a CLI session
started with `--replay`, the bridge also requires `replay_path` to match that
exact approved file.

When the CLI starts with `--replay`, Pi may omit `replay_path` entirely. The
TypeScript connector injects the pinned path only after model argument
validation, and the Python bridge independently verifies the same path. This
keeps local filesystem paths out of the model prompt and prevents path guesses
from selecting a different replay.

Before the response reaches Pi, the bridge replaces player IDs and display
names with replay-local aliases such as `player_01` and `Player 01`. Decision
IDs become opaque references such as `decision_001`; a follow-up tool call may
send that reference back, and the bridge resolves it to the original decision
only inside the local process. The backend/UI pipeline retains the original
identifiers and never relies on the model-facing aliases.

## `simulate_round`

The model-facing tool accepts a strict JSON object:

| Field | Type | Values / bounds |
| --- | --- | --- |
| `seed` | integer, optional | Signed 32-bit integer; Python defaults to `0` when omitted. |
| `scenario` | string, required by the TypeScript tool | `example` or `planted`. |
| `policy` | string, required by the TypeScript tool | `baseline` or `bayesian`. |
| `max_events` | integer, optional | 1–100; bounds the returned `key_events` list. |

Unknown fields are rejected. Validation happens twice: the TypeScript adapter checks the model call before spawning Python, and the bridge validates the wire request independently.

## Wire envelope

Requests use protocol version 1:

```json
{
  "version": 1,
  "operation": "simulate_round",
  "arguments": {
    "seed": 7,
    "scenario": "example",
    "policy": "baseline",
    "max_events": 3
  }
}
```

Success responses have this shape:

```json
{
  "version": 1,
  "ok": true,
  "data": {
    "seed": 7,
    "scenario": "example",
    "policy": "baseline",
    "winner": "t",
    "duration_seconds": 92.5,
    "event_count": 339,
    "events_truncated": true,
    "key_events": [],
    "final_state": {}
  }
}
```

`key_events` contains outcome-changing events when available, otherwise a chronological prefix. `final_state` includes time, bomb state, remaining bomb time, and a bounded summary of each player. The complete simulator event log is not returned through this tool.

Failure responses never expose tracebacks or simulator internals:

```json
{
  "version": 1,
  "ok": false,
  "error": {"code": "INVALID_SCENARIO", "message": "Unknown scenario."}
}
```

Common stable codes include `INVALID_JSON`, `INVALID_REQUEST`, `UNSUPPORTED_VERSION`, `UNKNOWN_OPERATION`, `INVALID_ARGUMENTS`, `INVALID_SEED`, `INVALID_SCENARIO`, `INVALID_POLICY`, `INVALID_EVENT_LIMIT`, `INVALID_REPLAY_PATH`, `REPLAY_NOT_FOUND`, `REPLAY_NOT_ALLOWED`, `INVALID_VERSION`, `INVALID_DECISION`, `LIMIT_EXCEEDED`, `BRIDGE_TIMEOUT`, `BRIDGE_CANCELLED`, `BRIDGE_PROCESS`, and `INTERNAL_ERROR`.

## Adding a tool

Implement the Python operation and its contract first. Then add a TypeBox schema and semantic validator, a registered adapter with explicit effect/approval/timeout/result limits, policy tests, bridge tests, and documentation. Register it in `src/tools/index.ts` only when the end-to-end path is ready. Do not broaden the bridge operation table or Pi allowlist as a shortcut.

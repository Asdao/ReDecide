# Tool protocol

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

Common stable codes include `INVALID_JSON`, `INVALID_REQUEST`, `UNSUPPORTED_VERSION`, `UNKNOWN_OPERATION`, `INVALID_ARGUMENTS`, `INVALID_SEED`, `INVALID_SCENARIO`, `INVALID_POLICY`, `INVALID_EVENT_LIMIT`, `LIMIT_EXCEEDED`, `BRIDGE_TIMEOUT`, `BRIDGE_CANCELLED`, `BRIDGE_PROCESS`, and `INTERNAL_ERROR`.

## Adding a tool

Implement the Python operation and its contract first. Then add a TypeBox schema and semantic validator, a registered adapter with explicit effect/approval/timeout/result limits, policy tests, bridge tests, and documentation. Register it in `src/tools/index.ts` only when the end-to-end path is ready. Do not broaden the bridge operation table or Pi allowlist as a shortcut.

# Coaching FastAPI

This service owns decision detection, player selection, and coaching. It does
not accept native `.dem` files. A Replay FastAPI upload creates the shared
`replay_id` and the coaching service reads the persisted `coaching.json`
artifact from `REDECIDE_REPLAY_STORE`.

The two services therefore share one parse boundary:

```text
.dem -> Replay FastAPI /api/replay/upload -> Blackbox parses once
                                      ├── visualization.json -> frontend
                                      └── coaching.json -> this API
```

## Run

```powershell
uvicorn backend.app.main:app --port 8000
```

## `GET /api/health`

Response `200`:

```json
{"status":"ok"}
```

## `POST /api/analysis/prepare`

Starts asynchronous preparation. Use exactly one of `replay_id` or `replay`.

### Preferred request: shared replay artifact

```json
{
  "replay_id": "0123456789abcdef0123456789abcdef"
}
```

The API loads `data/runtime/replays/<replay_id>/coaching.json` and runs the
existing replay pipeline. The native `.dem` is not uploaded or parsed again.
When coaching completes successfully, the API unlocks the full visualization
artifact for the frontend Replay API.

The `replay_id` request is the normal production path. The inline `replay`
request is a compatibility path for normalized JSON fixtures and tests.

### Direct normalized JSON request

This compatibility path is useful for fixtures and local tests:

```json
{
  "replay": {
    "replay_id": "match-001",
    "header": {"map_name": "de_mirage", "tick_rate": 64},
    "rounds": [{"round_num": 1, "start": 100, "end": 300}],
    "ticks": [{"round_num": 1, "tick": 164, "steamid": "p1", "player_name": "Player One"}],
    "damages": [{"round_num": 1, "tick": 164, "attacker_steamid": "p1", "victim_steamid": "p2", "dmg_health": 20}],
    "kills": []
  }
}
```

Response `202`:

```json
{
  "analysis_id": "analysis-job-uuid",
  "status": "processing",
  "players_available": false,
  "result_available": false,
  "logs_url": "/api/analysis/analysis-job-uuid/logs",
  "events_url": "/api/analysis/analysis-job-uuid/events",
  "result_url": "/api/analysis/analysis-job-uuid/result"
}
```

Response variables:

| Field | Meaning |
|---|---|
| `analysis_id` | Identifier used by every later analysis route. |
| `status` | Initially `processing`; later `ready`, `complete`, or `failed`. |
| `players_available` | Whether `/players` can return the selector. |
| `result_available` | Whether `/result` contains the completed coaching result. |
| `logs_url` | Relative URL for persisted JSONL progress records. |
| `events_url` | Relative URL for the SSE progress stream. |
| `result_url` | Relative URL for the final UI JSON. |
| `replay_id` | Shared replay artifact ID when the Replay API branch was used. |

### Preparation behavior

The pipeline indexes first-damage decision candidates for all players. It
keeps positions and events available to the deterministic replay pipeline,
but the coach adapter later receives only a bounded outcome-blind payload.

Errors:

- `404`: `replay_id` does not have a coaching artifact.
- `422`: exactly one of `replay_id` or `replay` must be supplied.

## `GET /api/analysis/{analysis_id}`

Returns job status. Poll until `players_available` is `true` or `status` is
`failed`.

Variables:

| Field | Meaning |
|---|---|
| `analysis_id` | Job identifier returned by prepare. |
| `status` | Usually `processing`, `ready`, `complete`, or `failed`. |
| `players_available` | Player selector is ready. |
| `result_available` | Final coaching result is ready. |
| `logs_url` | JSONL progress log endpoint. |
| `events_url` | SSE progress endpoint. |
| `result_url` | Final result endpoint. |

Errors: `404` when `analysis_id` is unknown.

## `GET /api/analysis/{analysis_id}/players`

Returns all selectable players after preparation:

```json
{
  "analysis_id": "analysis-job-uuid",
  "status": "ready",
  "players": [
    {
      "player_id": "p1",
      "display_name": "Player One",
      "side_by_round": {"1": "CT"},
      "rounds": [1],
      "event_ids": ["event-1"],
      "key_event_ids": ["event-1"],
      "decision_ids": ["r1:p1:t164"]
    }
  ]
}
```

`player_id` is the stable value to submit. `display_name` is presentation
only and may be ambiguous.

Errors: `404` when the job is unknown; `202` while preparation is still
running; `200` when the selector is ready.

## `POST /api/analysis/{analysis_id}/run`

Selects one player and invokes the configured coach adapter.

Request:

```json
{"player_id": "p1"}
```

For simple clients, `{"player_name":"Player One"}` is also accepted when
the name identifies exactly one player.

Response `200` is the completed analysis result. The API filters the returned
event and decision lists to the selected player, while keeping the global
team-probability timeline intact.

The successful response has the same JSON shape documented by `/result`.
Replay API jobs also unlock the full visualization artifact as part of this
successful request.

Errors: `404` for an unknown job; `409` before preparation completes; `422`
when the player is invalid or has no eligible decision; `503` when the coach
adapter fails.

## `GET /api/analysis/{analysis_id}/result`

Returns the final UI JSON:

```json
{
  "analysis_id": "analysis-job-uuid",
  "players": [],
  "events": [],
  "key_events": [],
  "decision_candidates": [],
  "selected_decision": {
    "decision_id": "r1:p1:t164",
    "player_id": "p1",
    "player_name": "Player One",
    "decision_open_tick": 164,
    "action_close_tick": 324,
    "observed_action": "IMMEDIATE_REENGAGE"
  },
  "win_estimator": {
    "scope": "global_team_probability",
    "filtered_by_player": false,
    "timeline": []
  },
  "coach_analysis": {
    "decision_id": "r1:p1:t164",
    "player_id": "p1",
    "player_name": "Player One",
    "what_could_be_done_better": "Break line of sight after first contact and wait for support."
  },
  "replay_outcome": {
    "eventual_winner": "T",
    "round_score": {"CT": 12, "T": 16},
    "source": "round_score"
  }
}
```

Important output variables:

| Field | Meaning |
|---|---|
| `events` | Selected-player event markers for the UI. |
| `key_events` | Important damage, kill, and bomb markers. |
| `decision_candidates` | First-contact coaching opportunities. |
| `selected_decision` | The candidate chosen for coaching and its bounded action window. |
| `win_estimator` | Global CT/T probability timeline; it is not player-filtered. |
| `coach_analysis` | Normalized coaching result with decision/player identity and validated coaching text. |
| `replay_outcome` | Post-coaching context; never sent to the outcome-blind coach payload. |

The coach payload removes events after `action_close_tick`, aliases player IDs,
and does not provide the Pi process with a replay path or replay-analysis tool.

Response status: `200` when complete; `202` while coaching has not run; `404`
for an unknown job; `500` when the job has failed.

## `GET /api/analysis/{analysis_id}/events`

Streams Server-Sent Events while the job runs:

```text
event: log
data: {"analysis_id":"...","stage":"players_indexed","progress":25}

event: complete
data: {"analysis_id":"...","stage":"complete","progress":100}
```

Progress is monotonic: preparation occupies approximately `0–50`, player
selection and coaching occupy `55–100`.

Each `log` event contains the safe progress record. A failed job emits a final
`log` event with `stage: "error"`; it does not emit `complete`. The stream
closes when the job reaches `complete` or `failed`. Errors: `404` for an
unknown job.

## `GET /api/analysis/{analysis_id}/logs`

Returns plain-text JSONL progress records. Logs contain safe stage, progress,
and message fields; provider secrets, prompts, local paths, and raw provider
failures are excluded. Stage-specific records may also include
`preparation_progress`, `player_id`, `result_available`, `model_available`,
and other safe progress metadata. The response content type is `text/plain`.
Errors: `404` for an unknown job.

## Coaching runtime configuration

The default `PiCoachAdapter` requires Node.js and installed dependencies under
`agent-harness/node_modules`. It passes the following settings to the Pi
process, with deployment environment variables taking precedence over the
repository `.env`:

| Variable | Meaning |
|---|---|
| `HARNESS_ENV_FILE` | Explicit dotenv file for the Pi process. |
| `HARNESS_MODEL_PROVIDER` | Provider selection. |
| `HARNESS_MODEL` | Model name. |
| `HARNESS_MODEL_BASE_URL` | OpenAI-compatible provider base URL. |
| `HARNESS_MODEL_API` | Provider API mode or endpoint override. |
| `HARNESS_MODEL_API_KEY` | Generic provider credential. |
| `DEEPSEEK_API_KEY` | DeepSeek provider credential. |

Missing Node dependencies or provider failures are returned from `/run` as
`503`; secrets and raw provider output are not written to API logs.

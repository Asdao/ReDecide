# Replay analysis API

> **Integration status:** This replay-job transport is preserved behind
> `backend.app.main.create_app(service=...)` for pipeline integration and
> tests. The default `backend.app.main:app` still exposes the agreed four
> fixture-backed RE:DECIDE endpoints. Do not connect the frontend to the job
> routes until their internal report is adapted into the frozen
> `DecisionPacket` and `DecisionCard` contracts.

The API uses two inputs and three outputs. The replay is uploaded once; the
frontend then chooses a player by stable `player_id` (the displayed name is
only a label). The replay is not uploaded or parsed again for that selection.

## Two inputs

### 1. Prepare the replay

`POST /api/analysis/prepare`

```json
{"replay": {"header": {}, "rounds": [], "ticks": [], "damages": []}}
```

The replay object is the processed telemetry format. The normal fields are:

```json
{
  "replay_id": "match-001",
  "header": {"map_name": "de_mirage", "tick_rate": 64},
  "rounds": [{"round_num": 1, "start": 100, "end": 300}],
  "ticks": [{"round_num": 1, "tick": 164, "steamid": "p1", "player_name": "Player One"}],
  "damages": [{"round_num": 1, "tick": 164, "attacker_steamid": "p1", "victim_steamid": "p2", "dmg_health": 20}],
  "kills": []
}
```

`damages` establish first-contact coaching anchors. `kills` are replay
markers and are not the selector rule. Additional normalized telemetry fields
are preserved for replay rendering and evidence extraction.

The response contains an `analysis_id`. Preparation runs in a background job,
indexes first-damage decisions for all players, and creates a private JSONL
log at `data/runtime/analysis-logs/<analysis_id>.jsonl`.

### 2. Select the player and run coaching

`POST /api/analysis/{analysis_id}/run`

```json
{"player_id": "76561198032889356"}
```

`player_name` is accepted for simple clients, but is rejected when it is
ambiguous. The UI should submit `player_id` from the selector. The server
filters that player's events and candidates, keeps the global CT/T win-rate
timeline intact, and invokes the configured coach adapter. Pi/DeepSeek output
is merged with `merge_pi_output`, which restores the authoritative player name
and decision ID.

The final result is one JSON document shaped like this:

```json
{
  "analysis_id": "uuid",
  "players": [],
  "events": [],
  "key_events": [],
  "decision_candidates": [],
  "selected_decision": {"decision_id": "match-round-player-tick", "player_name": "Player One"},
  "win_estimator": {"scope": "global_team_probability", "timeline": []},
  "coach_analysis": {
    "decision_id": "match-round-player-tick",
    "player_id": "p1",
    "player_name": "Player One",
    "what_could_be_done_better": "Break line of sight after first contact and wait for support."
  }
}
```

## Three outputs

- `GET /api/analysis/{analysis_id}/players` returns the player selector once
  preparation has indexed the replay.
- `GET /api/analysis/{analysis_id}/events` streams structured Server-Sent
  Events (`log` and `complete`) while preparation and coaching run.
- `GET /api/analysis/{analysis_id}/result` returns the final UI JSON, including
  player-filtered events, selected decision, global `win_estimator`, and
  `coach_analysis`.

`GET /api/analysis/{analysis_id}/logs` returns the complete JSONL log. Log
records contain `analysis_id`, stage, progress, and safe messages. Provider
secrets, raw prompts, local paths, and raw provider failures are not written.
Preparation occupies progress 0-50; player selection and coaching occupy
55-100, so the progress bar remains monotonic across both inputs.

The service is intentionally transport-neutral in
`backend/app/orchestration.py`; FastAPI is only the HTTP/SSE adapter in
`backend/app/main.py`. The coaching adapter is injected in tests and must be
connected to the server-side Pi bridge before enabling live model calls.

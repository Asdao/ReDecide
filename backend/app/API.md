# Replay analysis API

The API uses two inputs and three outputs. The replay is uploaded once; the
frontend then chooses a player by stable `player_id` (the displayed name is
only a label). The replay is not uploaded or parsed again for that selection.

## Runnable CLI example

The canonical end-to-end example is [`Noah/backend demo/README.md`](../../Noah/backend%20demo/README.md).
It uses the same FastAPI application that a website calls, with an in-process
HTTP client and no duplicate coaching implementation. Run it from the
repository root:

```powershell
uv run --extra test python "Noah/backend demo/cli.py"
```

The demo loads a real `.dem` first when available, falls back to the normalized
replay JSONL, polls preparation status, lets you select a player, calls the Pi
adapter through `POST /api/analysis/{analysis_id}/run`, and prints only event,
probability, and major-event alternative lines. Use `--player-id` to exercise
the same route sequence without the interactive selector.

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

Poll `GET /api/analysis/{analysis_id}` while `status` is `processing`. Continue
to the player route when `players_available` is `true`; stop when `status` is
`failed`. Clients should not impose a short fixed preparation deadline because
native extraction and full-model inference can legitimately exceed ten
seconds.

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
  },
  "replay_outcome": {
    "eventual_winner": "T",
    "round_score": {"CT": 12, "T": 16},
    "source": "round_score"
  }
}
```

`replay_outcome` is attached only after the Pi coaching call completes. It is
available to the website and CLI for post-match context, but is never included
in the outcome-blind payload sent to Pi.

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
`backend/app/main.py`. The default service uses the server-side
`PiCoachAdapter`, which receives the already-selected outcome-blind decision,
anonymizes it, removes events after `action_close_tick`, and invokes Pi without
giving the agent a replay path or replay-analysis tool. Tests may still inject
a deterministic adapter. Each Pi process inherits deployment environment
variables and receives the repository-root `.env` through `HARNESS_ENV_FILE`
when no explicit dotenv path is already configured. Provider output is
normalized to the two required coaching fields before `merge_pi_output`; the
adapter accepts strict JSON and the narrow unquoted-object rendering produced
by some OpenAI-compatible models. The runtime invokes the installed `tsx`
entrypoint directly with Node; it does not run `pnpm` or dependency installation
inside an API request. Curated `PiCoachError` messages are safe to return with a
503, while unexpected adapter exceptions remain the generic `coaching analysis
failed` response.

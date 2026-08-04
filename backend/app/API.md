# Replay analysis API

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

### Verified deterministic response

The exact response captured from the FastAPI integration test is checked in at
`backend/tests/fixtures/analysis_api_result.json`. It was produced by:

1. posting the processed replay used by `test_analysis_api.py` to
   `/api/analysis/prepare`;
2. waiting for `/api/analysis/{analysis_id}/players` to become ready;
3. selecting player `T One` with `POST /api/analysis/{analysis_id}/run`; and
4. reading `/api/analysis/{analysis_id}/result`.

The verified run returned HTTP `200` and the exact result document has:

- `schema_version: "replay_pipeline_v1"`;
- `report_type: "replay_pipeline_analysis"`;
- two players and two events;
- a first-damage-contact decision candidate for `T One`;
- an outcome-blind summary;
- an unfiltered global `win_estimator`; and
- a `coach_analysis` object containing the deterministic fixture coaching text.

The checked-in JSON is the authoritative example for this replay-pipeline
response. It is intentionally separate from
`backend/tests/fixtures/decision_card.valid.json`, which represents the frozen
RE:DECIDE `DecisionCard` contract rather than the current replay-job result.

The complete verified response is reproduced below without omitting fields:

```json
{
  "coach_analysis": {
    "decision_id": "r1:pt1:t164",
    "player_id": "t1",
    "player_name": "T One",
    "source": "pi",
    "what_could_be_done_better": "Break line of sight after first contact and wait for support."
  },
  "decision_candidates": [
    {
      "action_close_tick": 300,
      "contact_tick": 164,
      "decision_id": "r1:pt1:t164",
      "decision_open_tick": 164,
      "display_name": "T One",
      "event_category": "damage",
      "evidence": [
        "displacement_below_threshold"
      ],
      "observed_action": "hold",
      "observed_action_confidence": 0.88,
      "opponent_id": "ct1",
      "player_id": "t1",
      "role": "attacker",
      "round_number": 1,
      "side": "t"
    }
  ],
  "events": [
    {
      "event_id": "evt:1:r1:t164",
      "event_type": "damage",
      "is_coaching_anchor": true,
      "is_key_event": true,
      "key_event_type": "first_damage_contact",
      "participant_ids": [
        "t1",
        "ct1"
      ],
      "round_number": 1,
      "tick": 164
    },
    {
      "event_id": "evt:2:r1:t240",
      "event_type": "kill",
      "is_coaching_anchor": false,
      "is_key_event": true,
      "key_event_type": "kill_marker",
      "participant_ids": [
        "t1",
        "ct1"
      ],
      "round_number": 1,
      "tick": 240
    }
  ],
  "filter_contract": {
    "global_unfiltered_fields": [
      "win_estimator"
    ],
    "player_event_field": "participant_ids",
    "player_reference_fields": [
      "event_ids",
      "key_event_ids",
      "decision_ids"
    ]
  },
  "key_events": [
    {
      "event_id": "evt:1:r1:t164",
      "event_type": "damage",
      "is_coaching_anchor": true,
      "is_key_event": true,
      "key_event_type": "first_damage_contact",
      "participant_ids": [
        "t1",
        "ct1"
      ],
      "round_number": 1,
      "tick": 164
    },
    {
      "event_id": "evt:2:r1:t240",
      "event_type": "kill",
      "is_coaching_anchor": false,
      "is_key_event": true,
      "key_event_type": "kill_marker",
      "participant_ids": [
        "t1",
        "ct1"
      ],
      "round_number": 1,
      "tick": 240
    }
  ],
  "map_name": "de_mirage",
  "players": [
    {
      "decision_ids": [
        "r1:pct1:t164"
      ],
      "display_name": "CT One",
      "event_ids": [
        "evt:1:r1:t164",
        "evt:2:r1:t240"
      ],
      "key_event_ids": [
        "evt:1:r1:t164",
        "evt:2:r1:t240"
      ],
      "player_id": "ct1",
      "rounds": [
        1
      ],
      "side_by_round": {
        "1": "ct"
      }
    },
    {
      "decision_ids": [
        "r1:pt1:t164"
      ],
      "display_name": "T One",
      "event_ids": [
        "evt:1:r1:t164",
        "evt:2:r1:t240"
      ],
      "key_event_ids": [
        "evt:1:r1:t164",
        "evt:2:r1:t240"
      ],
      "player_id": "t1",
      "rounds": [
        1
      ],
      "side_by_round": {
        "1": "t"
      }
    }
  ],
  "replay_id": "api-flow-test",
  "report_type": "replay_pipeline_analysis",
  "schema_version": "replay_pipeline_v1",
  "selected_decision": {
    "action_close_tick": 300,
    "contact_tick": 164,
    "decision_id": "r1:pt1:t164",
    "decision_open_tick": 164,
    "display_name": "T One",
    "event_category": "damage",
    "evidence": [
      "displacement_below_threshold"
    ],
    "observed_action": "hold",
    "observed_action_confidence": 0.88,
    "opponent_id": "ct1",
    "player_id": "t1",
    "player_name": "T One",
    "role": "attacker",
    "round_number": 1,
    "side": "t"
  },
  "source": "api-flow-test.dem",
  "summary": {
    "analysis_available": true,
    "anchor": "first_damage_contact",
    "anchor_fallback": false,
    "decision_candidate_count": 2,
    "event_count": 2,
    "key_event_count": 2,
    "outcome_blind": true,
    "player_count": 2
  },
  "win_estimator": {
    "filtered_by_player": false,
    "model_available": true,
    "model_type": "replay_value_ensemble_or_fallback",
    "scope": "global_team_probability",
    "timeline": [
      {
        "ct_probability": 0.6440739071353798,
        "round_number": 1,
        "t_probability": 0.3559260928646202,
        "tick": 100,
        "uncertainty": 1.0
      }
    ]
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

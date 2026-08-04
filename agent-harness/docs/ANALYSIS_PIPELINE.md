# Round analysis pipeline

This guide describes the modular path from a simulated round to an explanation and recommendation:

```text
demo -> timeline -> first damage contact per player -> decision index -> Pi explanation
                                      \-> bounded team win estimator
```

The simulator is the source of truth. Pi is the explanation layer. A model may summarize returned facts, but it must not invent events, state, scores, or causes.

## What exists today

The harness exposes `simulate_round` and a first `analyze_replay` vertical slice. `analyze_replay` accepts a server-side `.dem`, `.json`, or `.jsonl` path, uses the extractor's native parser/sidecar fallback, and returns a bounded decision index for every player plus a shared team win-estimator timeline. The model receives facts and identifiers, not the full replay or outcome labels. Kills remain available in the replay for UI markers, but they are not the coaching selector. If a source has no damage stream, the report marks `no_damage_stream` and emits no coaching candidates instead of substituting death-only anchors.

Run the current capability with:

```powershell
pnpm dev -- --prompt "Run seed 7 for the example scenario with the baseline policy"
```

Use the [tool protocol](TOOLS.md) for the current JSON contract.

## Current and target module boundaries

The implemented repository boundaries are:

```text
model/src/cs2_sim/  deterministic rules, state, actions, events, ReplayModel facade
extractor/src/      replay_extractor parsing, normalization, and segmentation
training/           TrainingPipeline facade and offline data/model workflows
agent-harness/src/  Pi-specific TypeScript adapters and local Python bridge
```

Keep future analysis orchestration separate from these stable facades:

```text
src/analysis/      timeline, pivotal-event detection, state diff, win score
src/pipeline/      demo -> replay -> report orchestration
src/tools/         policy-checked Pi adapters around bounded use cases
skills/            reviewed instructions for explaining reports
web/ or server/    HTTP/SSE transport; no simulator logic
```

Application code should call `ReplayModel`, `ReplayExtractor`, and
`TrainingPipeline` from their package roots. It should not reach into model
component files, extractor repositories, or training scripts directly. The
same facade-backed library can serve a CLI, Pi session, test runner, and future
webapp. A separate deployable service is unnecessary until scale or isolation
requires one.

## Recommended execution flow

1. `run_demo` creates a deterministic replay from `{seed, scenario, policy}` and stores or returns a `replay_id`.
2. `build_timeline` converts simulator events into chronological, user-facing events with state snapshots or references to snapshots.
3. `analyze_replay` indexes the first damage contact for each `(round, player)` pair. Each candidate carries a stable `decision_id`, the pre-contact decision window, opponent/team identity, observed action, and evidence. This avoids selecting only deaths and therefore preserves successful reset decisions.
4. The UI filters candidates by the original `player_id` (or shows all players), then can request the same report with `decision_id` to select one window.
5. At the Pi boundary, the bridge replaces player IDs/names with replay-local aliases and turns decision IDs into opaque references. A follow-up Pi tool call is translated back locally; original identifiers remain in the backend/UI only.
6. The shared release-backed model produces bounded team win-estimator points. Pi uses the outcome-blind report and the analysis skill to write a full-sentence explanation; the webapp keeps the complete replay and event markers for replay rendering.

The server-side handoff merges Pi's response back into the authoritative UI
result with `merge_pi_output`. It resolves the model-facing opaque decision
reference, restores the original `player_id` and `display_name` from the
backend candidate, and adds the result under `coach_analysis`. The source
replay JSON is read-only and is never rewritten.

For a webapp, pass a replay ID between stages rather than sending the entire event log through the model. Recompute from the seed or load the replay from server-side storage when a later stage needs more context.

## Target tool contracts

The demo-to-analysis contract below is registered in the harness. The older
`run_demo` contract remains a future server-side replay-store operation.

### `run_demo`

```json
{
  "seed": 7,
  "scenario": "example",
  "policy": "baseline"
}
```

Returns a `replay_id`, winner, duration, and bounded metadata. The full replay remains server-side.

### `analyze_replay` (implemented vertical slice)

```json
{
  "replay_path": "C:/replays/match.dem",
  "max_decisions": 100,
  "max_timeline_points": 120,
  "sample_every": 8,
  "decision_id": "r1:p7656119:t1200"
}
```

The pipeline emits progress envelopes while it runs. The final envelope has
`stage: "complete"`, `progress: 100`, `done: true`, and places the complete
authoritative result under `result`:

```json
{
  "schema_version": "pipeline_progress_v1",
  "stage": "complete",
  "progress": 100,
  "message": "Replay preparation is complete.",
  "done": true,
  "result": {}
}
```

The authoritative result sent to the UI has this shape. The IDs and names in
this object are the backend's original values; this is the object the player
selector and replay renderer consume:

```json
{
  "report_type": "replay_pipeline_analysis",
  "schema_version": "replay_pipeline_v1",
  "replay_id": "match-42",
  "players": [{
    "player_id": "steam:7656119",
    "display_name": "Player A",
    "side_by_round": {"1": "t"},
    "event_ids": ["evt:1:r1:t1200"],
    "key_event_ids": ["evt:1:r1:t1200"],
    "decision_ids": ["r1:psteam:7656119:t1200"]
  }],
  "key_events": [{
    "event_id": "evt:1:r1:t1200",
    "round_number": 1,
    "tick": 1200,
    "event_type": "damage",
    "participant_ids": ["steam:7656119"],
    "is_key_event": true,
    "key_event_type": "first_damage_contact",
    "is_coaching_anchor": true
  }],
  "decision_candidates": [{
    "decision_id": "r1:psteam:7656119:t1200",
    "round_number": 1,
    "player_id": "steam:7656119",
    "display_name": "Player A",
    "event_category": "damage",
    "decision_open_tick": 1200,
    "contact_tick": 1200,
    "action_close_tick": 1360,
    "observed_action": "peek"
  }],
  "selected_decision": {
    "decision_id": "r1:psteam:7656119:t1200",
    "player_id": "steam:7656119",
    "player_name": "Player A"
  },
  "win_estimator": {
    "scope": "global_team_probability",
    "filtered_by_player": false,
    "model_available": true,
    "timeline": [{"round_number": 1, "tick": 1200, "ct_probability": 0.52, "t_probability": 0.48, "uncertainty": 0.1}]
  },
  "summary": {"anchor": "first_damage_contact", "outcome_blind": true},
  "coach_analysis": {
    "source": "pi",
    "decision_id": "r1:psteam:7656119:t1200",
    "player_id": "steam:7656119",
    "player_name": "Player A",
    "observed_action": "peek",
    "evidence": ["displacement_above_threshold"],
    "what_could_be_done_better": "Hold the angle until support is available."
  }
}
```

`coach_analysis` is added only after the server receives Pi's response and
calls `merge_pi_output`. Before that merge, `selected_decision` may be `null`.
`merge_pi_output` accepts either a parsed JSON object or Pi text containing a
JSON object, resolves `decision_001` back to the candidate's original
`decision_id`, and restores `player_name` from the authoritative player list.
The source replay JSON is never rewritten.

The pipeline intentionally does not include `round_won`, `outcome`, or future kill/death labels in the selected window. The UI can retain the original replay and use its kill events as replay markers. The current release-backed estimator can report `model_available: false` when optional model dependencies are absent without blocking decision indexing.

## Frontend preparation functions

The transport-neutral backend surface lives in
`backend/app/replay/pipeline.py` and has three public functions:

```python
from backend.app.replay.pipeline import (
    extract_players_for_selector,
    merge_pi_output,
    stream_replay_pipeline,
)

selector = extract_players_for_selector("match.dem")
ui_result = None
for update in stream_replay_pipeline("match.dem"):
    send_to_frontend(update)
    if update.get("done"):
        ui_result = update["result"]

# pi_response is the parsed JSON returned by the redacted Pi adapter.
final_ui_result = merge_pi_output(ui_result, pi_response)
```

`extract_players_for_selector` and `stream_replay_pipeline` require only the
replay input. `merge_pi_output` requires the authoritative result plus the
Pi response. The stream emits monotonic stage percentages from `0` through
`100`; its final `complete` update contains the entire prepared result.
`players[].event_ids`, `key_event_ids`, and
`decision_ids` are the direct selector indexes. The frontend filters event
markers through `participant_ids`, while `win_estimator` remains a global CT/T
team probability and is never filtered by player.

Every event exposes `is_key_event`, `key_event_type`, and
`is_coaching_anchor`. First damage contacts are coaching anchors; kills and
bomb events remain easy-to-pull replay markers without becoming the coaching
selection rule.

### Model-facing JSON versus UI JSON

The model-facing projection deliberately has a different identity layer:

```json
{
  "privacy": {
    "player_identifiers_redacted": true,
    "player_names_redacted": true,
    "decision_references_opaque": true
  },
  "players": [{"player_id": "player_02", "display_name": "Player 02"}],
  "decision_candidates": [{
    "decision_id": "decision_001",
    "player_id": "player_02",
    "observed_action": "peek"
  }]
}
```

Pi never receives the original Steam ID, player name, or filesystem path. The
bridge maps the opaque decision reference back locally for a follow-up call,
then redacts the returned payload again. Only `merge_pi_output` restores the
authoritative identity for the final UI JSON.

## Tool versus skill responsibilities

Tools should do deterministic work:

- validate inputs and limits;
- run or load the replay;
- identify events and state transitions;
- calculate scores and deltas;
- return evidence references and uncertainty.

Skills should guide communication:

- explain the timeline in plain language;
- distinguish observed facts from inference;
- state what could be done differently;
- avoid claiming real professional CS2 advice from simulator behavior;
- cite the returned event IDs or timestamps when making a claim.

Do not put the pipeline algorithm in `SKILL.md`, and do not ask Pi to calculate the score from prose.

## FastAPI usage

The backend exposes a two-stage job. The replay is accepted once; selecting a
player references the prepared job and never reparses the source:

```text
POST /api/analysis/prepare       { replay: <processed replay JSON> }
  <- { analysis_id, status, players_url, events_url, result_url }

GET /api/analysis/{id}/players   selector-ready player names and IDs
GET /api/analysis/{id}/events    SSE log/progress stream

POST /api/analysis/{id}/run      { player_id }
GET /api/analysis/{id}/result    final player-filtered UI JSON
GET /api/analysis/{id}/logs      persisted JSONL log
```

The player view filters events and first-contact decision candidates by the
selected player. The `win_estimator` remains global to preserve the distinct
CT/T team context. The FastAPI adapter is in `backend/app/main.py`; its
transport-neutral job state and JSONL logging are in
`backend/app/orchestration.py`. Keep API keys, replay storage, and model calls
on the server. The default service constructs
`backend.app.coach.PiCoachAdapter`. For each Pi process it preserves
deployment environment variables and, when no explicit `HARNESS_ENV_FILE` is
configured, points the harness at the repository-root `.env`. The adapter
receives the selected anonymized decision packet; it does not give Pi a replay
path or a replay-analysis tool.

## Implementation order

1. Add explicit `player_death`, damage, and round-ending event records to the simulator.
2. Add immutable state snapshots or compact state references at event boundaries.
3. Add `src/analysis/` pure functions with fixture-based tests.
4. Add the replay store and bounded `run_demo` bridge operation if the webapp needs opaque replay IDs instead of local paths.
5. Extend the current composite `analyze_replay` tool with persisted replay IDs and richer state diffs after the UI contract is fixed.
6. Add `skills/analyze-cs2-round/` instructions for the structured report format.
7. Extend the existing HTTP/SSE transport without moving domain logic into the
   web layer.

Keep the first release narrow: one replay, one pivotal event, one team perspective, and a bounded evidence window. Expand to multiple events or counterfactual simulations only after the basic report is deterministic and reviewable.

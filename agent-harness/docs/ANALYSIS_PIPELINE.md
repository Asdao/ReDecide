# Round analysis pipeline

This guide describes the modular path from a simulated round to an explanation and recommendation:

```text
demo -> timeline -> pivotal death/loss event -> before/after analysis -> recommendation
                                      \-> deterministic win score
```

The simulator is the source of truth. Pi is the explanation layer. A model may summarize returned facts, but it must not invent events, state, scores, or causes.

## What exists today

The current harness exposes `simulate_round`. It returns a seeded winner, event count, bounded key events, and final state. The simulator internally creates a full event list, but the bridge deliberately returns only a bounded subset. Explicit player-death events, replay IDs, and win scores are planned extensions.

Run the current capability with:

```powershell
pnpm dev -- --prompt "Run seed 7 for the example scenario with the baseline policy"
```

Use the [tool protocol](TOOLS.md) for the current JSON contract. Do not call the planned tools below until their bridge operation and tests have been added.

## Target module boundaries

Keep the pipeline in the package, but separate it from Pi-specific adapters:

```text
src/cs2_sim/       deterministic rules, state, actions, events
src/analysis/      timeline, pivotal-event detection, state diff, win score
src/pipeline/      demo -> replay -> report orchestration
src/tools/         policy-checked Pi adapters around bounded use cases
skills/            reviewed instructions for explaining reports
web/ or server/    future HTTP/SSE wrapper; no simulator logic
```

The same pipeline library can serve a CLI, Pi session, test runner, and future webapp. A separate deployable service is unnecessary until scale or isolation requires one.

## Recommended execution flow

1. `run_demo` creates a deterministic replay from `{seed, scenario, policy}` and stores or returns a `replay_id`.
2. `build_timeline` converts simulator events into chronological, user-facing events with state snapshots or references to snapshots.
3. `find_pivotal_event` selects the first decisive death, failed action, bomb event, or round-ending transition. The selector returns evidence and a reason code.
4. `score_state` calculates a bounded score for the requested team before and after the event. The score belongs to the simulator/analysis layer, not the language model.
5. `analyze_replay` returns a structured report containing the event window, state diff, score change, uncertainty, and allowed recommendations.
6. Pi uses the report and the analysis skill to write the human explanation. The webapp streams each completed stage to the client.

For a webapp, pass a replay ID between stages rather than sending the entire event log through the model. Recompute from the seed or load the replay from server-side storage when a later stage needs more context.

## Target tool contracts

These are proposed contracts, not currently registered tools.

### `run_demo`

```json
{
  "seed": 7,
  "scenario": "example",
  "policy": "baseline"
}
```

Returns a `replay_id`, winner, duration, and bounded metadata. The full replay remains server-side.

### `analyze_replay`

```json
{
  "replay_id": "rpl_01J...",
  "team": "t",
  "max_events": 20,
  "window_seconds": 10
}
```

Returns a report like:

```json
{
  "replay_id": "rpl_01J...",
  "winner": "ct",
  "pivotal_event": {
    "event_id": "evt_42",
    "kind": "player_death",
    "time_seconds": 31.5,
    "reason_code": "isolated_peek"
  },
  "before": {
    "win_score": 61.0,
    "state_ref": "snap_41"
  },
  "after": {
    "win_score": 34.0,
    "state_ref": "snap_42"
  },
  "score_delta": -27.0,
  "evidence": ["evt_39", "evt_42"],
  "recommendations": [
    {"action": "hold_crossfire", "confidence": 0.72}
  ]
}
```

The score must be reproducible for the same replay and team. Start with a documented heuristic or calibrated model; later replace it without changing the Pi-facing report schema.

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

## Webapp usage

A backend endpoint can expose the pipeline as a streamed job:

```text
POST /api/rounds              { seed, scenario, policy }
  <- { replay_id, status: "started" }

GET /api/rounds/{id}/events   Server-Sent Events:
  stage: timeline
  stage: pivotal_event
  stage: analysis
  stage: recommendation

GET /api/rounds/{id}          final structured report
```

Keep API keys, replay storage, and simulator execution on the server. The browser receives structured results and rendered explanations, never provider credentials or unrestricted tool access.

## Implementation order

1. Add explicit `player_death`, damage, and round-ending event records to the simulator.
2. Add immutable state snapshots or compact state references at event boundaries.
3. Add `src/analysis/` pure functions with fixture-based tests.
4. Add the replay store and bounded `run_demo`/`analyze_replay` bridge operations.
5. Register one composite `analyze_replay` tool only after validation, output limits, cancellation, and audit tests pass.
6. Add `skills/analyze-cs2-round/` instructions for the structured report format.
7. Add the HTTP/SSE wrapper without moving domain logic into the web layer.

Keep the first release narrow: one replay, one pivotal event, one team perspective, and a bounded evidence window. Expand to multiple events or counterfactual simulations only after the basic report is deterministic and reviewable.

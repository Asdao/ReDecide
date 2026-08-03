# AI Coach and Reliability Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 3 - AI Coach, Rubric, and Reliability

## Status

**Noah analysis connector implemented; RE:DECIDE provider/card layer remains
separate.**

`backend/app/coach/noah_connector.py` accepts one normalized replay mapping and
forwards it to Noah's deployed `ReplayModel.analyse_replay` facade. The folder
still contains no provider adapter, versioned rubric, prompt assembly,
structured-output parser, deterministic validators, or fixture coach.

## Required input and output

- Input: frozen `DecisionPacket`, `IntentInput`, versioned rubric, and at most
  two reviewed examples
- Output: frozen version `1.0` `DecisionCard`
- Model: one pretrained provider model; no training or fine-tuning from scratch
- Checks: schema, evidence IDs, future language/timestamps, explicit
  contradictions, confidence cap, and abstention

### Model I/O format

The following is the logical provider boundary for the planned RE:DECIDE coach.
It is not the current Noah connector request shape and is not yet an executable
schema in `backend/app/coach/`.

Model input is one JSON prompt envelope/.demo file:

```json
{
  "decision_packet": {
    "schema_version": "1.0",
    "decision_id": "match-round-player-tick",
    "match_id": "string",
    "map": "de_mirage",
    "round_number": 7,
    "player": "PlayerName",
    "decision_type": "POST_CONTACT_RESET",
    "decision_open_tick": 12345,
    "decision_open_seconds": 96.45,
    "action_close_tick": 12665,
    "known_before_decision": [],
    "observed_action": {},
    "unknowns": [],
    "data_quality": {"score": 0.86, "warnings": []}
  },
  "intent": {
    "tag": "TAKE_DUEL",
    "text": "I thought the enemy was reloading"
  },
  "rubric": {
    "version": "0.1",
    "content": "versioned coaching rubric text or YAML"
  },
  "few_shot_examples": []
}
```

Input rules:

- `decision_packet` is the only game evidence. The raw `.dem`, full event log,
  round winner, and anything after `action_close_tick` are excluded.
- `intent` is the player's stated intent, not a fact asserted by the parser.
- `few_shot_examples` contains zero to two reviewed examples using the same
  schema.
- The provider must not generate or receive `checks`; validators compute those
  fields after parsing the response.

The model response must be JSON matching the frozen `DecisionCard` shape:

```json
{
  "report_type": "combined_replay_analysis",
  "schema_version": "replay_analysis_v1",
  "source": "fixture.dem",
  "map_name": "de_mirage",
  "summary": {
    "moment_count": 4,
    "kill_count": 4,
    "kill_analysis_count": 4,
    "least_risk_fallback_count": 4,
    "least_risk_candidate_count": 4,
    "least_risk_usable_count": 0,
    "decision_classes": {
      "insufficient_evidence": 4
    },
    "probability_decision_classes": {
      "insufficient_evidence": 4
    },
    "recommendations_are_counterfactual_estimates": true,
    "probability_labels_are_thresholded_estimates": true,
    "candidate_model_type": "full_lightgbm_blended_with_small_statistical"
  },
  "kill_analysis": [
    {
      "kill_number": 1,
      "round_num": 1,
      "tick": 64,
      "time_seconds": 1.0,
      "event_id": "event-000001",
      "attacker_id": "ct1",
      "victim_id": "t1",
      "weapon": "m4a1",
      "observed_action": "hold",
      "recommended_action": "hold",
      "recommendation_supported": false,
      "recommendation_sample_count": 104,
      "recommendation_support_level": "backoff",
      "recommendation_support_reason": "high_entropy",
      "least_death_risk_action": "hold",
      "least_death_probability": 0.145985401459854,
      "least_death_round_loss_probability_proxy": 0.145985401459854,
      "least_death_is_proxy": true,
      "least_death_risk_upper_bound": 0.19542941544969175,
      "least_death_risk_support": 135,
      "least_death_risk_supported": false,
      "least_death_risk_status": "unsupported_candidate_state",
      "least_death_risk_source": "round_loss_proxy_posterior",
      "round_win_probability": 0.14458186005395898,
      "round_loss_probability_proxy": 0.855418139946041,
      "probability_of_improvement": null,
      "expected_regret": null,
      "probability_decision_class": "insufficient_evidence",
      "estimate_type": "simulator_action_value_estimate"
    }
  ]
}
```

`checks` is shown here to document the final API output, but it is appended or
overwritten by deterministic backend validation. A response with invalid JSON,
unknown evidence IDs, forbidden future information, contradictions, or weak
evidence is rejected, repaired at most once when appropriate, or converted to
`INSUFFICIENT_EVIDENCE`.

### Current Noah connector I/O

The implemented boundary is different: `NoahCoachConnector.analyse_json()`
accepts a normalized replay object such as the checked-in
`backend/tests/fixtures/coach_replay.json` and returns a report with
`report_type: "combined_replay_analysis"`. The report contains `full_match`,
`moments`, `kill_analysis`, `summary`, model configuration, and probability /
abstention metadata. It is a replay-analysis report, not a `DecisionCard`, and
must not be sent to the frontend as the final coaching response.

## Existing work to review

Root `agent-harness/` contains useful process, configuration, timeout, audit,
and validation patterns. Its synthetic simulation and winner/final-state output
must not be connected directly to the RE:DECIDE coach.

`Noah/` contains the canonical existing replay-analysis implementation,
including both the model/runtime (`Noah/model/`) and the analysis harness and
training pipeline (`Noah/training/`). It is the correct implementation to
reuse for RE:DECIDE, but it has not yet been wired to the frozen
`DecisionPacket`/`DecisionCard` coach contract.

### Legacy model probability behavior

The existing `Noah/` implementation does not currently estimate a calibrated
player-death probability for an arbitrary action sequence such as `A -> B -> C`.
Its probability fields come from three distinct paths:

- The candidate-action path scores one legal first action from a reconstructed
  simulator state. The small model combines a Beta-smoothed observed-outcome
  estimate (75%) with an action-frequency prior (25%). The optional full model
  blends an 80% LightGBM score with the small-model score.
- Candidate-action training labels define `success` as the player's team
  winning the simulated round. The simulator forces the candidate first action
  and then lets the policy choose subsequent actions. Therefore the analysis
  field `death_probability = 1 - success_probability` is a proxy for simulated
  round loss, not literal probability that the player dies.
- The observed-engagement path estimates death from replay labels in a future
  time window using a Beta-smoothed state key based on map, side, role, contact
  type, weapon, and horizon. It does not receive an action sequence.

Consequently, `A -> B -> C` is not learned as one sequence-level event. A true
`P(death | A, B, C)` requires a sequence model or repeated fixed-action
rollouts that count deaths across the complete sequence. This legacy behavior
must not be presented as the frozen RE:DECIDE coaching contract.

### Internal data flow

The canonical implementation has three related inference paths:

1. **Replay-value snapshots.** Replay data is normalized into time-stamped
   snapshots. The feature builder converts each snapshot into a fixed vector
   containing map/time, alive-player counts, health, armor, positions, bomb
   state, kills, damage, shots, utility, and bomb time remaining. The deployable
   ensemble combines an optional LightGBM prediction with a hierarchical
   Bayesian snapshot prediction, then optionally applies Platt calibration.
   This returns `P(CT wins the round | snapshot)` plus Bayesian support and
   uncertainty. Each timeline point is scored independently; the harness can
   compare adjacent probabilities to report a swing.
2. **Observed engagement windows.** The engagement extractor chooses a contact
   anchor and builds a fixed future horizon such as one, two, or five seconds.
   Features before the cutoff form a compact state key: map, side, role, anchor
   type, weapon, and horizon. Future replay labels are used only to train the
   descriptive outcomes. The runtime uses Beta-smoothed local counts backed off
   toward global counts, and may blend an optional LightGBM engagement head.
   This path reports observed kill, death, trade, and post-kill survival rates;
   it does not infer whether an unobserved alternative action would have been
   better.
3. **Candidate-action analysis.** The harness selects important replay moments,
   reconstructs a simulator `GameState`, finds legal actions, and scores each
   candidate for the identified player. The small statistical model uses a
   state/action count prior plus observed binary outcomes. The full action model
   converts the state/action pair into simulator features and blends a
   LightGBM score with the small-model score. Candidate rows are then filtered
   by sample support and entropy and ranked by estimated round-value delta,
   with death probability used as a secondary ordering signal.

Candidate-action training evaluates each legal first action by running the
simulator from the same initial state. The first action is forced; subsequent
actions are selected by the configured policy. The label is whether the acting
player's team wins the round. This is why the candidate score is a simulated
round-value estimate rather than a per-event death hazard.

### Backend connector

The backend coach boundary can call the deployed analysis without importing
the harness internals:

```python
from backend.app.coach.noah_connector import NoahCoachConnector

connector = NoahCoachConnector()
report = connector.analyse(normalized_replay)
```

`analyse_json` is available for a JSON request body, and `analyze` is an
American-English alias. The connector validates that the returned object is a
`combined_replay_analysis` report and wraps load/runtime failures in the stable
`NoahCoachError`. It does not convert the report into a `DecisionCard` or make
provider calls.

The harness then compares the observed action with the best supported candidate.
Its estimated regret is:

```text
best_candidate_round_value - observed_action_round_value
```

Large positive regret is classified as bad, non-positive regret as good, and
intermediate or unsupported cases as neutral or insufficient evidence. These
legacy fields remain in the report for compatibility. The probability-based
fields use seeded Beta-posterior comparisons and require support, a meaningful
expected gap, and a probability-of-improvement threshold before emitting a
directional label. Unsupported cases abstain and must remain visible to the
coach layer. Candidate support can be exact or hierarchical backoff; reports
expose the level and raw support so a broad prior is not confused with an
exact-state observation.
High-entropy rankings, missing labelled outcome counts, and constant
within-state rollout outcomes also abstain; action-observation support alone
is not treated as a success/failure sample size.

## Important paths

```text
backend/app/coach/**
backend/tests/test_coach_*.py
data/eval/model/**
```

## Tests and validation

The connector tests are in `backend/tests/test_coach_noah_connector.py` and
cover forwarding, JSON input, invalid input, stable configuration errors, and
the real checked-in fixture flowing through the deployed runtime.
The RE:DECIDE coach contract itself still has no fixture tests in the new path.

The user-facing Noah smoke runner is:

```powershell
python Noah/training/test_harness.py data/private/processed/full_replays.jsonl
```

For a deterministic local smoke test, send the checked-in fixture through the
same runner. It lives under `backend/tests`, so it is separate from training
data:

```powershell
python Noah/training/test_harness.py backend/tests/fixtures/coach_full_replay.json --all-moments --sample-every 1 --output data/private/processed/coach_fixture.analysis.json
```

The backend boundary can use that same object directly, or decode a request
body with `NoahCoachConnector.analyse_json(payload)`. The fixture is tiny, so
sparse evidence may produce abstention/insufficient-evidence probability
labels; that is the expected safe result. `full_match.event_counts.kill` and
the kill events attached to `moments` should contain all four fixture kills.
Normal production calls remain capped at 25 key moments unless
`max_moments=None`/`--all-moments` is explicitly requested.
The command also prints a per-kill table; the JSON report exposes the same
rows under `kill_analysis`. `summary.kill_count` remains the total replay kill
count, while `summary.kill_analysis_count` reports how many received candidate
analysis under the selected cap.

Required coverage includes well-formed fixtures, nonexistent evidence IDs,
forbidden outcome information, malformed model JSON, low-quality packets,
contradictory evidence, confidence caps, and safe abstention.

## Known limitations and blockers

- No executable shared contracts or fixture packets are available yet.
- No provider/model/API key and spend limit are confirmed in this path.
- No versioned coaching rubric or reviewed evaluation labels are present.

## Contract/API impact

The Noah connector is an internal model-report adapter only. Consume frozen
RE:DECIDE contracts owned by Person 1 and coordinate labels with Person 5;
do not expose the combined report as a `DecisionCard` until that contract is
implemented.

## Next handoff

Once a frozen fixture packet is available, return one validated fixture card,
then prove one genuine structured-output provider call without exposing a key.

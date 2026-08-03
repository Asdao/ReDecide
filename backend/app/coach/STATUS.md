# AI Coach and Reliability Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 3 - AI Coach, Rubric, and Reliability

## Status

**Not implemented in the new RE:DECIDE path.**

`backend/app/coach/` currently contains no provider adapter, versioned rubric,
prompt assembly, structured-output parser, deterministic validators, or fixture
coach.

## Required input and output

- Input: frozen `DecisionPacket`, `IntentInput`, versioned rubric, and at most
  two reviewed examples
- Output: frozen version `1.0` `DecisionCard`
- Model: one pretrained provider model; no training or fine-tuning from scratch
- Checks: schema, evidence IDs, future language/timestamps, explicit
  contradictions, confidence cap, and abstention

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

The harness then compares the observed action with the best supported candidate.
Its estimated regret is:

```text
best_candidate_round_value - observed_action_round_value
```

Large positive regret is classified as bad, non-positive regret as good, and
intermediate or unsupported cases as neutral or insufficient evidence. These
classifications are legacy simulator-analysis behavior and still require a
cutoff-safe adapter before they can be used by RE:DECIDE.

## Important paths

```text
backend/app/coach/**
backend/tests/test_coach_*.py
data/eval/model/**
```

## Tests and validation

No RE:DECIDE coach tests exist in the new path yet.

Required coverage includes well-formed fixtures, nonexistent evidence IDs,
forbidden outcome information, malformed model JSON, low-quality packets,
contradictory evidence, confidence caps, and safe abstention.

## Known limitations and blockers

- No executable shared contracts or fixture packets are available yet.
- No provider/model/API key and spend limit are confirmed in this path.
- No versioned coaching rubric or reviewed evaluation labels are present.

## Contract/API impact

None implemented. Consume contracts owned by Person 1 and coordinate labels
with Person 5.

## Next handoff

Once a frozen fixture packet is available, return one validated fixture card,
then prove one genuine structured-output provider call without exposing a key.

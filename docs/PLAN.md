# CS2 Tactical Simulation Plan

## Goal

Build a small, deterministic CS2 round simulator in Python. Hard game rules are
implemented in code, while a replaceable policy chooses tactical actions. The
first policy is rule-based; a small Bayesian policy can be trained later from
compact match data.

The first version models one map with named zones. It does not attempt to
reproduce aiming, physics, or exact player movement.

## Design principles

- Keep game rules separate from learned behaviour.
- Give every module one clear responsibility.
- Use typed dataclasses, enums, and protocols at module boundaries.
- Keep the simulation deterministic when given the same random seed.
- Advance simulated time without calling `sleep`.
- Keep file and network I/O outside the simulation core.
- Start with the Python standard library; add a model dependency only when the
  baseline simulation works.

## Proposed structure

```text
GHackathon/
|-- main.py                         # Creates dependencies and runs an example
|-- pyproject.toml
|-- docs/
|   `-- PLAN.md                     # This document
|-- src/
|   `-- cs2_sim/
|       |-- __init__.py
|       |-- config.py               # Tick and decision interval configuration
|       |-- state.py                # GameState, PlayerState, Team, BombState
|       |-- actions.py              # Action types, durations, completion rules
|       |-- events.py               # Damage, death, sighting and bomb events
|       |-- rules.py                # Legal actions and round-ending rules
|       |-- policy.py               # ActionPolicy protocol
|       |-- baseline_policy.py      # Simple seeded rule-based policy
|       |-- bayesian_policy.py      # Optional learned action probabilities
|       `-- simulator.py            # Simulation loop and action interruption
|-- training/
|   |-- __init__.py
|   |-- download_dataset.py         # Stream small metadata or full demos with a byte cap
|   |-- extract_features.py         # Converts compact match data into examples
|   |-- train_policy.py             # Fits and saves Bayesian probability tables
|   `-- train_models.py             # Monitored simulator-bootstrap training
|-- data/                           # Downloaded data; ignored by Git
|   |-- small/metadata/
|   `-- full/
|-- models/                         # Generated model data; ignored by Git
`-- tests/
    |-- test_downloader.py
    |-- test_rules.py
    |-- test_actions.py
    |-- test_simulator.py
    `-- test_policy.py
```

Do not create all modules with placeholder code at once. Add them in the order
below, keeping the test suite passing after each step.

## State and action scope

Use discrete map zones rather than coordinates in version one. A state contains:

- Simulated round time
- Player team, health, alive status, inventory class, and current zone
- CT and T players alive
- Bomb carrier, bomb state, and bomb site
- Currently visible enemies
- The active action for each player
- A chronological event list

Initially support these actions:

- `HOLD`
- `PEEK`
- `MOVE_TO_ADJACENT_ZONE`
- `USE_UTILITY`
- `PLANT`
- `DEFUSE`
- `SAVE`

Do not make `ROTATE_A_TO_B` one long action. A rotation is a sequence of
`MOVE_TO_ADJACENT_ZONE` actions, allowing the policy to reconsider at each zone.

## Timing model

- Simulation tick: `0.25` seconds
- Normal policy decision interval: `1.0` second
- Ordinary action limit: `1` to `3` seconds depending on action type
- `HOLD` and `SAVE`: continue until interrupted, completed, or reconsidered
- `PLANT` and `DEFUSE`: use explicit rules-engine durations

An action is reconsidered immediately after an important event:

- An enemy becomes visible
- The player takes damage
- A player dies
- The bomb is planted, dropped, or picked up
- The destination zone is reached
- A route becomes invalid

Keep action duration in `actions.py`; do not scatter timing constants throughout
the simulator.

## Policy boundary

Define a small interface in `policy.py`:

```python
class ActionPolicy(Protocol):
    def choose_action(
        self,
        state: GameState,
        player_id: str,
        legal_actions: tuple[Action, ...],
    ) -> Action: ...
```

The simulator must only call this interface. It must not know whether the action
came from hand-written rules, Bayesian counts, or a future ML model.

The first `BaselinePolicy` should be understandable and seeded. For example, it
may prioritize defusing, planting, escaping an unwinnable situation, moving
toward the bomb, and otherwise holding or peeking with fixed probabilities.

## Bayesian policy

After the simulator works, train a compact conditional probability table:

```text
P(action | map zone, side, time bucket, alive difference, bomb state)
```

Use Dirichlet/Laplace smoothing so unseen and rare states still have sensible
probabilities. Save the result as versioned JSON rather than Python pickle. JSON
is portable, inspectable, and safer to load.

Keep training outside `src/cs2_sim`. Runtime code may load a completed model but
must never train one during a simulation.

The initial metadata dataset can train event and outcome probabilities. Tactical
actions such as holding, peeking, and rotating require position data extracted
from selected raw demos or manually defined simulator behaviour.

The detailed algorithm choices and evaluation criteria are documented in
`docs/STATISTICAL_MODELING_PLAN.md`.

## Implementation milestones

### 1. Domain model

Create the enums and immutable value objects in `state.py`, `actions.py`, and
`events.py`. Add validation for impossible values such as negative health.

Done when state objects can represent a simple five-versus-five round and their
tests pass.

### 2. Rules engine

Implement pure functions in `rules.py` for legal actions and round results.
Include elimination, timer expiry, bomb detonation, and defusal.

Done when tests cover both valid and invalid actions and every round-ending path.

### 3. Action timing

Implement action start, progress, completion, timeout, and interruption. Keep the
clock virtual and expose action outcomes as events.

Done when tests demonstrate that a normal action ends on time and is interrupted
immediately by contact or damage.

### 4. Baseline policy

Implement `ActionPolicy` and the seeded rule-based policy. Require policies to
choose only from actions supplied by the rules engine.

Done when the same seed and initial state produce the same sequence of actions.

### 5. Simulation loop

At each tick, update active actions, apply resulting events, check round-ending
rules, and ask the policy for decisions when required. Return a structured
`SimulationResult`; do not print from the core.

Done when a complete round can run quickly from `main.py` and returns a winner
plus an event timeline.

### 6. Data and Bayesian policy

Stream selected match records, convert them into coarse state/action examples,
and train the smoothed probability table. Keep processed Parquet/JSON data under
the storage budget and do not commit raw demos.

Done when `BayesianPolicy` can replace `BaselinePolicy` without changing the
simulator.

### 7. Evaluation

Evaluate policies by running many seeded simulations. Record round-win rate,
action distribution, invalid-action count, average round duration, and model
confidence. Compare against the baseline instead of relying on a single replay.

## Test requirements

- Pure rule tests contain no random behaviour.
- Randomized tests always specify a seed.
- Policies never receive hidden enemy information unless it is marked known.
- A dead player cannot act.
- Illegal plant and defuse attempts are rejected.
- Interruptions happen before the next scheduled one-second decision.
- Simulation stops at a configurable maximum duration to prevent infinite loops.
- Model loading rejects unknown schema versions or malformed probability tables.

## First deliverable

The first usable release should contain only the domain model, rules engine,
baseline policy, simulator, tests, and a short example in `main.py`. Do not add
demo parsing, a UI, an LLM, or LightGBM until this release behaves correctly.

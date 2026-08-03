# CS2 replay data and modelling plan

## Goal

Build a reliable CS2 analysis pipeline that:

1. preserves raw demos;
2. audits and cleans replay data reproducibly;
3. stores queryable training rows in SQLite;
4. trains calibrated round-value models quickly; and
5. later learns player actions without mixing action labels with round outcomes.

The current 23 native demos, 505 rounds, and 2,491 positional snapshots are the
initial full-replay dataset. The 500 lightweight sidecars remain useful for the
larger Bayesian prior.

## Design rules

- Raw `.dem` and parsed JSONL files are immutable inputs.
- Cleaning writes a new versioned dataset; it never edits raw data.
- SQLite becomes the canonical input for training.
- Data splits are grouped by match, not by snapshot.
- Labels never appear in model feature columns.
- Round-value and action-value models remain separate modules.
- Every model artifact includes its feature schema, cleaning version, split,
  metrics, and random seed.

## Intended module layout

```text
training/
|-- audit_replays.py          # Read-only data-quality report
|-- replay_cleaning.py        # Shared cleaning policy and pure functions
|-- build_replay_db.py        # JSONL -> versioned SQLite database
|-- replay_repository.py      # Typed SQLite queries for trainers
|-- full_features.py          # Round-value feature construction
|-- infer_actions.py          # Fixed-window player action labels
|-- train_baselines.py        # Bayesian, logistic, and optional GNB baselines
|-- train_full_replay.py      # SQLite-backed LightGBM training
|-- calibrate_model.py        # Platt or beta calibration
`-- evaluate_models.py        # Grouped comparison and reports

src/cs2_sim/core/model/
|-- replay_value.py           # Deployable Bayesian + LightGBM ensemble
|-- action_value.py           # Future action recommendation model
`-- transitions.py            # Future first-order Markov movement model
```

The existing `cs2_sim.models` package remains as a compatibility shim while
new model code is added under `cs2_sim.core.model`.

## Implementation status

The first implementation pass is complete through action inference:

- `training.audit_replays` and `training.replay_cleaning` provide deterministic,
  non-destructive reports and versioned cleaned copies;
- SQLite schema version 2 now stores matches, replay checksums, player ticks,
  events, snapshots, and inferred actions;
- `training.train_full_replay --database` reads SQLite directly and weights
  rows so each round contributes equal total training weight;
- Gaussian Naive Bayes, regularized logistic regression, Platt calibration,
  and grouped model comparison are available;
- `ReplayValueEnsemble` provides Bayesian fallback, blending, calibration, and
  uncertainty; and
- fixed-window movement labels plus Dirichlet action and zone-transition
  models are available.

The remaining work is deeper feature quality (utility/visibility/weapon state)
and larger-scale action-value validation once more native demos are available.

## Phase 1: Audit and cleaning

Create `training/audit_replays.py` and `training/replay_cleaning.py`.

Audit checks:

- duplicate replay, round, tick, and snapshot keys;
- missing winners, teams, health, positions, or tick rates;
- invalid alive counts outside `0..5`;
- non-monotonic ticks and impossible round boundaries;
- technical pauses and rounds longer than the configured maximum;
- unknown maps and coordinate outliers;
- terminal-state and post-outcome leakage;
- map, side, patch, team, and label distributions; and
- number of snapshots contributed by each round.

Initial cleaning policy:

- use first player damage as contact for native demos;
- fall back to first real kill when damage is unavailable;
- keep a configurable five-second decision window;
- reject snapshots after 180 seconds of round time;
- exclude terminal states;
- calculate positions using alive players only;
- retain team total health separately from alive-player average health; and
- attach `cleaning_version`, `contact_basis`, and exclusion reason counts.

Output:

```text
data/full/processed/audit_report.json
data/full/processed/cleaning_manifest.json
```

Done when the audit is deterministic, raw files remain unchanged, and every
excluded row has a counted reason.

## Phase 2: Canonical SQLite schema

Upgrade `training/build_replay_db.py` to schema version 2.

Tables:

- `dataset_metadata`: schema and cleaning versions;
- `matches`: match ID, date, event, patch, and teams;
- `replays`: source path, checksum, map, parser, match ID, and tick rate;
- `rounds`: timing, winner, reason, bomb result, and score;
- `players`: stable player and team identity;
- `player_ticks`: per-player health, armor, position, zone and state;
- `events`: kills, damage, fire, utility, bomb, and other event types;
- `snapshots`: one row per cleaned decision state with real feature columns and
  an optional JSON debugging payload; and
- `inferred_actions`: future fixed-window action labels.

Required constraints:

- unique `(replay_id, round_num, tick)` training snapshots;
- unique source path and checksum for replays;
- foreign keys enabled;
- indexes for match, replay, map, round, tick, player, and action; and
- migrations controlled by an explicit schema version.

Do not store primary training features only inside JSON. JSON may remain as an
optional debugging payload, but health, alive counts, positions, time, map,
bomb state and labels must be normal columns.

Done for the current dataset: rebuilding produces 23 unique replays, 505
rounds, 2,513 snapshots, and 1,168,262 player-tick rows with no duplicate
training keys.

## Phase 3: Connect SQLite to training

Create `training/replay_repository.py` and change
`training/train_full_replay.py` to accept:

```powershell
python -m training.train_full_replay `
  --database data/full/processed/cs2_replays.sqlite
```

Training behaviour:

- query cleaned feature columns directly;
- preserve JSONL only as an import format;
- group splits by match ID;
- prefer a chronological validation split when dates are available;
- weight snapshots so each round contributes equal total weight;
- optionally rebalance maps without changing outcome labels;
- save the exact train/validation match IDs; and
- cache the final numeric matrices when the database version is unchanged.

Performance targets:

- database feature loading below one second for the current dataset;
- model training below ten seconds for the current dataset;
- deterministic output for a fixed seed; and
- no full 381 MB JSONL read during normal training.

Done when SQLite and JSONL produce equivalent cleaned rows, and SQLite is the
trainer default. The current benchmark is roughly 17.9 seconds for JSONL plus
feature rebuilding versus 0.38 seconds for SQLite loading.

## Phase 4: Statistical baselines and calibration

Train every model on the same grouped split.

Models:

1. hierarchical Beta-binomial Bayesian baseline;
2. regularized logistic regression baseline;
3. optional Gaussian Naive Bayes speed benchmark; and
4. LightGBM nonlinear model.

LightGBM configuration remains intentionally small:

- `num_leaves=15`;
- `max_bin=63`;
- feature and row subsampling;
- at most 200 boosting rounds; and
- early stopping after 30 non-improving rounds.

Feature corrections:

- use LightGBM categorical features or stable one-hot columns for map and bomb
  site instead of hashed numeric values;
- add alive-only positions and normalized/map-zone positions;
- add recent damage, fire, utility, armor and bomb-time features; and
- remove redundant features only when mutual information and ablation tests
  show no useful signal.

Calibration:

- use Platt scaling or beta calibration on grouped out-of-fold predictions;
- use isotonic regression only after substantially more validation rounds; and
- report calibration before and after adjustment.

Selection metrics:

- log loss and Brier score are primary;
- expected calibration error and reliability bins are required;
- balanced accuracy is secondary;
- training time, inference time and artifact size are recorded; and
- the model must beat the training-prior baseline on held-out matches.

Done when `evaluate_models.py` produces one reproducible JSON report and names
the simplest model that satisfies the selection rules.

## Phase 5: Deployable replay-value ensemble

Create `src/cs2_sim/core/model/replay_value.py`.

The class must:

- load the Bayesian model, LightGBM booster, category mapping and calibrator;
- validate the feature and cleaning schema versions;
- expose `predict_ct_win(snapshot)`;
- blend the two models using a validated weight;
- return probability, sample count and uncertainty;
- fall back to the Bayesian model when the booster is unavailable; and
- load one manifest rather than several unrelated files.

This closes the current gap where validation blends the models but the saved
runtime artifact contains only the LightGBM booster.

Done when a round-trip test saves, loads and reproduces the same probability.

## Phase 6: Action inference and movement statistics

Do not train action recommendations directly from round-winner rows.

Create player-level fixed-window labels from native ticks:

- hold;
- move to adjacent zone;
- rotate;
- peek/engage;
- retreat;
- throw utility;
- plant;
- defuse; and
- save.

Start with a two-second action window and make it configurable. Each action row
must include the state before the action, the observed action, the legal action
set, the horizon, and outcome evidence.

Statistical models:

- Dirichlet-smoothed `P(action | state)` for imitation and fallback;
- normalized Shannon entropy for action uncertainty;
- first-order Markov `P(next zone | current zone, context)` for rotations;
- logistic regression and LightGBM for action outcome/value; and
- Gaussian mixtures only for position/setup heatmaps.

The deterministic simulator remains responsible for action legality. Observed
frequency is not automatically action quality; the analyser must distinguish
"commonly chosen" from "associated with a better outcome."

Done when inferred actions pass hand-checked replay examples and the model can
rank only legal actions while reporting uncertainty.

## Phase 7: Verification and delivery

Required tests:

- cleaning-rule unit tests for every exclusion reason;
- database migration, uniqueness and foreign-key tests;
- JSONL-versus-SQLite feature parity;
- match-grouped split leakage tests;
- per-round weighting tests;
- category encoding and unseen-category tests;
- model save/load parity;
- calibration tests;
- action-window inference fixtures; and
- end-to-end parse -> audit -> database -> train -> predict smoke test.

Release gates:

- zero known snapshot or match leakage;
- no unexplained missing required features;
- database is the default trainer source;
- round-level log loss remains below the baseline;
- calibrated probabilities do not regress materially;
- inference remains comfortably below one second; and
- all model limitations are stated in the generated metrics report.

## Recommended implementation order

1. Audit and cleaning modules.
2. SQLite schema version 2 and repository.
3. SQLite-backed trainer and weighted grouped split.
4. Logistic baseline and calibration.
5. Deployable replay-value ensemble.
6. Player/action tables and action inference.
7. Markov transitions and action-value training.

The first three items provide the largest immediate reliability and speed
improvement. Action modelling should begin only after those foundations pass
their tests.

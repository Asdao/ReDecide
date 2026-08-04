# Training the two replay-value models

Data is split into public and private roots. Public metadata and maps may be
uploaded after checking their source license; raw demos, parsed replay data,
SQLite databases, features, and user uploads stay under `data/private`. See
[`DATA_LAYOUT.md`](DATA_LAYOUT.md).

The lightweight pipeline uses parsed `.analysis.json` sidecars. It does not
download the very large `.dem` file for every match.

`download_dataset` streams each remote file in bounded chunks, enforces the
cumulative `--max-gb` budget, and atomically renames the completed `.part`
file. It therefore never loads the complete dataset into memory. The default
cached path keeps downloaded sidecars on disk until `extract_features` has
produced compact JSONL snapshots; the optional streaming path below pipes one
sidecar at a time through extraction.

For application code, use `backend.replay_engine.training.TrainingPipeline` as documented in
[`docs/MODULE_API.md`](MODULE_API.md). The commands below remain the supported
shell interface for individual pipeline stages.

## One complete run

Use the project Python and set `PYTHONPATH` first:

```powershell
$env:PYTHONPATH = "backend/replay_engine/model/src;backend/replay_engine/extractor/src;."

python -m backend.replay_engine.training.download_dataset sidecars --max-files 500 --max-gb 0.25

python -m backend.replay_engine.training.extract_features `
  --input data/private/sidecars `
  --output data/private/processed/analysis_snapshots.jsonl `
  --decision-window-seconds 5

python -m backend.replay_engine.training.train_snapshot_model

python -m backend.replay_engine.training.train_full_replay `
  --snapshot-input data/private/processed/analysis_snapshots.jsonl
```

For the storage-minimal alternative, replace the download and extraction
commands above with:

```powershell
python -m backend.replay_engine.training.stream_sidecars `
  --metadata data/public/metadata `
  --output data/private/processed/analysis_snapshots.jsonl `
  --max-files 500 `
  --max-gb 0.25
```

To stream and train both replay-value models in one command, use the
orchestrator instead:

```powershell
python -m backend.replay_engine.training.train_streamed_sidecars `
  --metadata data/public/metadata `
  --snapshot-output data/private/processed/analysis_snapshots.jsonl `
  --release-dir backend/replay_engine/model/artifacts/releases/v4 `
  --max-files 500 `
  --max-gb 0.25
```

This command trains the small snapshot model and the event-only full replay
model. The full trainer reuses the snapshot artifact without overwriting it;
its held-out metrics use a development-only in-memory prior to avoid test
leakage. It does not retrain movement or candidate-action models because
compact sidecars do not contain the positional/action data those models
require.

`stream_sidecars` is the storage-minimal alternative to the first two stages:
it uses the same metadata quality filters, downloads one sidecar at a time,
emits compact snapshots, and discards the raw sidecar. Add `--cache-dir` when
you want to retain a raw copy as well. The resulting snapshot JSONL can be
passed to `train_snapshot_model` and `train_full_replay --snapshot-input`.
This mode trains replay-value models; movement and candidate-action models
still require native positional replay data.

For a direct full replay run, `--small-model` is opt-in. When omitted, the
trainer fits the Bayesian component for that run and writes it only through
`--small-model-output`; an unrelated existing artifact is never reused by
accident.

## Sharing the exact same sidecar data

The repository includes `backend/replay_engine/training/sidecars_manifest.json`, a lock file for the
500 sidecars used by the lightweight pipeline. It records every dataset path,
byte count, and SHA-256 checksum. A new user can download that exact set with:

```powershell
$env:PYTHONPATH = "backend/replay_engine/model/src;backend/replay_engine/extractor/src;."
python -m backend.replay_engine.training.download_dataset locked `
  --manifest backend/replay_engine/training/sidecars_manifest.json `
  --output data/private/sidecars
```

The command reuses a file only when its checksum matches; otherwise it
re-downloads it and verifies the result. To check an existing directory without
downloading anything, run:

```powershell
python -m backend.replay_engine.training.download_dataset verify `
  --manifest backend/replay_engine/training/sidecars_manifest.json `
  --input data/private/sidecars
```

If the upstream selection changes later, regenerate a new manifest explicitly
with `download_dataset lock`; do not silently replace the checked-in one.

## SQLite replay database

JSONL remains the portable parser output, but the queryable training store is
SQLite. Build it after native parsing:

```powershell
python -m backend.replay_engine.training.build_replay_db `
  --input data/private/processed/full_replays.jsonl `
  --output data/private/databases/cs2_replays_v2.sqlite `
  --action-window-seconds 2 `
  --clean `
  --replace
```

The database contains `matches`, `replays`, `rounds`, `players`, `player_ticks`,
`events`, `inferred_actions`, and leakage-safe `snapshots` tables, with foreign
keys and indexes for replay/round/player/action queries. It uses Python's
built-in `sqlite3`, so no database server is required.

Run a read-only audit before rebuilding:

```powershell
python -m backend.replay_engine.training.audit_replays `
  --input data/private/processed/full_replays.jsonl `
  --report data/private/processed/replay_audit.json
```

For normal training, read SQLite directly instead of rebuilding features from
the full JSONL:

```powershell
python -m backend.replay_engine.training.train_full_replay `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --output model/artifacts/releases/v2/full_replay_value.txt `
  --small-model-output model/artifacts/releases/v2/small_snapshot_value.json `
  --calibrator model/artifacts/releases/v2/full_replay_calibrator.json `
  --manifest model/artifacts/releases/v2/full_replay_value.manifest.json
```

The trainer uses deterministic match/source-held-out groups: development rows
are split again for tuning and calibration, while the final test groups are
used only for the reported metrics. The manifest records the feature schema,
dataset fingerprint, split fingerprint, tick rate, and checksums for every
replay-value component.

The lightweight baselines can be compared with:

```powershell
python -m backend.replay_engine.training.train_baselines --database data/private/databases/cs2_replays_v2.sqlite
python -m backend.replay_engine.training.evaluate_models `
  model/artifacts/releases/v2/full_replay_metrics.json `
  model/artifacts/releases/v2/statistical_baseline_metrics.json `
  --output model/artifacts/releases/v2/model_comparison.json
```

LightGBM plus the Bayesian snapshot model is the deployed replay-value
ensemble. Gaussian/logistic reports are advisory baselines only; the
comparison command rejects reports built from a different dataset or split.

Train the movement-frequency and zone-transition tools from SQLite:

```powershell
python -m backend.replay_engine.training.train_action_models `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --action-output model/artifacts/releases/v2/action_frequency.json `
  --transition-output model/artifacts/releases/v2/zone_transitions.json
python -m backend.replay_engine.training.evaluate_actions `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --output model/artifacts/releases/v2/action_evaluation.json
```

Action labels are deterministic observations, not claims about a strategically
optimal or “best” CS2 move. The current action vocabulary is `hold`, `peek`,
`move_to_adjacent_zone`, `use_utility`, `plant`, `defuse`, and `unknown`.
Movement destinations and utility types are parameters, not separate classes.
The simulator may also expose `save`, but it is not learned until reliable
economy/round-context labels are available. The action coverage report records
match-separated support and identifies actions that must abstain when sparse.
Combat engagement windows are available as a separate, additive export. Schema
v3 places the decision cutoff one second before first damage and includes three
seconds of earlier movement, health, armor, damage, place, and team-distance
context. The identifying hit is not an input feature. `label_kill`,
`label_death`, `label_trade`, `label_survival`, `label_damage`, and
`label_round_win` only inspect events after the cutoff. The observed action is
measured after the cutoff and includes family, parameters, confidence, and
evidence fields:

```powershell
python -m backend.replay_engine.training.engagement_windows `
  --input data/private/processed/full_replays.jsonl `
  --output data/private/processed/engagement_windows_v3_5s.jsonl `
  --horizon-seconds 5 `
  --lookback-seconds 3 `
  --decision-lead-seconds 1 `
  --action-window-seconds 1
```

Supplying several horizons writes one suffixed JSONL per horizon. Existing
SQLite events can be read with `--database`, but positional history requires
player ticks; event-only rows explicitly report `history_available=false`.

Train the dependency-free engagement prior with a whole-match held-out split:

```powershell
python -m backend.replay_engine.training.train_engagement_model `
  --input data/private/processed/engagement_windows_v3_5s.jsonl `
  --output model/artifacts/releases/v4/engagement_model.json `
  --metrics model/artifacts/releases/v4/engagement_metrics.json
```

The trainer reports kill/death/trade/survival/damage/round-win log loss, Brier
score, calibration, and improvement over the training prior. Sparse targets use a
stronger empirical-Bayes prior; this avoids treating one observed duel as a
reliable tactical rule. If the full dependencies are installed, optional
shallow LightGBM heads use the same grouped split:

```powershell
python -m backend.replay_engine.training.train_engagement_lightgbm `
  --input data/private/processed/engagement_windows_v3_5s.jsonl `
  --output model/artifacts/releases/v4/engagement_lightgbm.json `
  --metrics model/artifacts/releases/v4/engagement_lightgbm_metrics.json
```

The LightGBM action features are generated from the shared vocabulary as
nominal one-hot columns; adding a learned action therefore requires new labels
and retraining, but not a second model. To add one, update
`backend/replay_engine/model/src/cs2_sim/action_vocabulary.py`, add its deterministic detector
to `backend/replay_engine/training/action_labeler.py`, add a fixture test, regenerate windows,
and retrain the release. Do not create a separate class for a target zone or
utility type. Review coverage before activation:

```powershell
python -m backend.replay_engine.training.evaluate_action_vocabulary `
  --input data/private/processed/engagement_windows_v3_5s.jsonl `
  --output model/artifacts/releases/v4/action_vocabulary_coverage.json `
  --model-metrics model/artifacts/releases/v4/engagement_lightgbm_metrics.json
```

Refresh the checksummed release manifest after changing an artifact:

```powershell
python -m backend.replay_engine.training.build_release_manifest `
  --release model/artifacts/releases/v4 --version v4
```

## Compact Parquet exports and dataset registry

SQLite remains the canonical training store. When a portable, typed projection
is useful, stream it into a new directory without loading the whole database:

```powershell
python -m backend.replay_engine.training.export_parquet `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --output data/private/features/replay-v1 `
  --dataset-id replay-v1 `
  --role training `
  --visibility private `
  --registry data/private/dataset_registry.json
```

The export writes `snapshots.parquet`, `actions.parquet`, and `metadata.json`.
Rows retain `match_id` and replay/round/tick identity; model inputs are typed
`feature_*` columns. Public exports omit raw source paths while retaining a
stable source hash. The registry records checksums, row counts, feature/schema
versions, source metadata, rejection reasons, and match groups. Its roles are
`training`, `validation`, `benchmark`, and `rejected`; it rejects a match group
appearing in more than one role:

```powershell
python -m backend.replay_engine.training.dataset_registry validate `
  --registry data/private/dataset_registry.json
python -m backend.replay_engine.training.dataset_registry list `
  --registry data/private/dataset_registry.json
```

At runtime, load the single manifest and use the Bayesian fallback if the
optional LightGBM native library is unavailable:

```python
from cs2_sim import ModelConfig, ReplayModel

model = ReplayModel.load(ModelConfig(version="v4"))
prediction = model.predict_probability(snapshot)
match_report = model.analyse_match(replay)
engagement_report = model.analyse_engagement(replay, tick=1234, player_id="steam-id")
```

`analyse_engagement` returns future-only multi-head probabilities.
`analyse_replay` scores legal simulator actions plus the shared action
vocabulary with a coaching utility: 35% round win, 25% survival, 15% kill,
10% trade, 10% damage, and 5% simulator value. These are observational
estimates, not causal proof. A "should have" label is emitted only after
support and uncertainty checks pass. The engagement report marks
statistical-only and LightGBM-blended results;
it does not claim an observational replay proves a counterfactual “best move”.

To install and activate a verified local release bundle:

```powershell
python -m backend.replay_engine.training.download_models `
  --source path/to/cs2-model-bundle-v2 `
  --releases model/artifacts/releases `
  --version v2 `
  --activate `
  --require-checksums
```

Run the end-to-end tester against SQLite, parsed JSONL, or a native demo:

```powershell
python -m backend.replay_engine.training.test_replay_models `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --manifest model/artifacts/releases/v2/full_replay_value.manifest.json `
  --action-model model/artifacts/releases/v2/action_frequency.json `
  --limit 500

python -m backend.replay_engine.training.test_replay_models `
  --input data/private/processed/full_replays.jsonl `
  --limit 500

python -m backend.replay_engine.training.test_replay_models --demo path/to/match.dem --limit 500
```

The replacement extractor can be used at the tester boundary as well. This
normalizes its JSONL in memory and reuses the existing model artifacts; it does
not rebuild SQLite or retrain either model:

```powershell
python -m backend.replay_engine.training.test_replay_models `
  --extractor-input path/to/replacement-extractor.jsonl `
  --limit 500 `
  --output model/artifacts/replay_model_test_extractor.json

python -m backend.replay_engine.training.test_replay_models `
  --extractor-demo path/to/match.dem `
  --limit 500
```

Install the sibling extractor only if needed:
`python -m pip install -e extractor` (use its optional `full` extra for
native Awpy parsing).

The adapter preserves the model's existing `record_to_rows` contract, including
round labels, tick aliases, event stream separation, and parser-native armor
field names. A regression test compares the resulting feature vectors before
and after adaptation so extractor changes cannot silently shift the model
input distribution.

The default tester mode is a bounded smoke check. It reports model predictions
and observed action counts, but its rows are not a held-out accuracy claim.
Use the trainer and `evaluate_actions` reports for held-out metrics. The
tester accepts replacement-extractor JSONL without rebuilding SQLite or
retraining.

With no `--database`, `--manifest`, or `--action-model` flags, the tester
follows `model/artifacts/releases/current.json` and uses the active release bundle.

## Sealed unseen-demo benchmark

Native demos are large, so benchmark selection uses the compact metadata first,
excludes every replay identity in the training database, and enforces a
cumulative byte budget before downloading:

```powershell
python -m backend.replay_engine.training.benchmark_dataset `
  --training-database data/private/databases/cs2_replays_v2.sqlite `
  --output data/private/benchmark_cache `
  --manifest data/public/benchmark_manifest.json `
  --max-files 1 `
  --max-gb 0.6
```

The manifest records the repository path, match/map metadata, local file,
size, and SHA-256 checksum. It is marked training-excluded and the evaluator
checks for overlap again before parsing any demo:

```powershell
python -m backend.replay_engine.training.evaluate_benchmark `
  --benchmark-manifest data/public/benchmark_manifest.json `
  --model-manifest model/artifacts/releases/v2/full_replay_value.manifest.json `
  --action-model model/artifacts/releases/v2/action_frequency.json `
  --output data/public/benchmark_evaluation.json
```

The benchmark report is a macro-average across unseen demos. It is a true
generalisation check for round-value prediction, but it is not yet a
counterfactual “best move” score.

The downloader reads the compact metadata already stored under
`data/public/metadata`. It rejects incomplete maps by requiring at least 16
rounds and 80 kills, ranks higher-star/recent matches first, and selects maps
round-robin to avoid a Mirage/Dust2-heavy subset. Change `--min-rounds`,
`--min-kills`, `--min-stars`, or `--max-files` when needed.

## What is leakage-safe here

The extractor keeps only the five seconds beginning with the first real kill.
It excludes `round_end`, states after either team reaches zero alive players,
and setup/world kills. The first kill is used because lightweight sidecars do
not contain damage ticks. Native demos can later use the first damage event as
a better contact marker.

Training, calibration, and test evaluation are separated by entire demo/match,
not random snapshots. Metrics include log loss, Brier score, balanced accuracy,
expected calibration error, and comparison with the training-set CT win-rate
baseline.

## Outputs

- `model/artifacts/small_snapshot_value.json`: hierarchical Bayesian model. It backs
  off through exact state, broader state, map, and global evidence.
- `model/artifacts/full_replay_value.txt`: LightGBM model blended with a split-safe 20%
  Bayesian prior during evaluation.
- `model/artifacts/small_snapshot_metrics.json` and
  `model/artifacts/full_replay_metrics.json`: demo-separated validation results.
- `model/artifacts/releases/v2/full_replay_value.manifest.json`: deployable
  Bayesian/LightGBM component manifest with checksums and dataset fingerprints.
- `model/artifacts/releases/v2/action_frequency.json` and `zone_transitions.json`:
  map-aware movement-tendency tools.
- `model/artifacts/releases/v2/engagement_model.json`: grouped, calibrated
  Beta-smoothed kill/death/trade prior with support and entropy.
- `model/artifacts/releases/v2/engagement_lightgbm.json`: optional compact
  engagement heads blended only when statistical support is sufficient.
- `model/artifacts/releases/v2/release_manifest.json`: checksums for all
  deployable components.

The event-only full model estimates round win probability. It is not yet a
movement/action model because sidecars contain no player positions, health,
utility inventory, visibility, or velocity. For that model, parse native demos
successfully and run `backend.replay_engine.training.train_full_replay` without `--snapshot-input`.

## Combined replay analysis

### One-command test

For the normal path, send a native `.dem`, extracted replay JSON, or JSONL file
to the small runner. Native demos and canonical replacement-extractor records
are normalized in memory; the harness does not build a database or retrain a
model. It selects the active release (`v5` in the current bundle), applies the conservative defaults, and writes
an adjacent `.analysis.json` report:

```powershell
python backend/replay_engine/training/test_harness.py data/private/processed/full_replays.jsonl
python backend/replay_engine/training/test_harness.py path/to/match.dem --all-moments
```

Use `--record-index 3` for another JSONL record or `--output path/to/report.json`
to choose the report location. It permits the documented Bayesian/statistical
fallback when optional native LightGBM dependencies are unavailable. The
runner is only an input/output wrapper; application code accesses the complete
harness through the package-root `backend.replay_engine.analyze_replay` function.

The implementation is split into a small orchestration facade in
`backend/replay_engine/training/analysis_harness.py`, replay-state reconstruction in
`replay_state.py`, candidate and engagement scoring in
`candidate_analysis.py`, and report/moment projection in `analysis_report.py`.

The same function accepts a native `.dem`, JSON/JSONL path, canonical extractor
mapping, or normalized replay mapping. It performs any required normalization,
loads the active model release, and returns the same report dictionary:

```python
from backend.replay_engine import analyze_replay

report = analyze_replay("match.dem", max_moments=None)
```

Analysis is read-only with respect to the training database and model artifacts.

### Clean-clone demo reproduction

The repository includes a sanitized replay fixture, the complete checksummed
`v5` release, and a portable expected-result specification. No private database
or raw `.dem` is needed for this regression. From a fresh clone of the `Replay Engine`
branch, install the optional native model runtime and run the focused check:

```powershell
uv sync --extra full
uv run --extra full python -m unittest `
  backend.replay_engine.training.tests.test_test_harness.TestHarnessInputTests.test_portable_demo_spec_reproduces_v5_summary `
  -v
```

To produce the complete human-inspectable report with the same inputs and
settings:

```powershell
uv run --extra full python backend/replay_engine/training/test_harness.py `
  backend/tests/fixtures/coach_full_replay.json `
  --release-dir backend/replay_engine/model/artifacts/releases `
  --version v5 `
  --output portable_demo.analysis.json
```

The expected summary and relative paths live in
`backend/replay_engine/model/artifacts/releases/v5/replay_model_demo_test.json`. The regression
fails if the fixture is absent, paths become machine-specific, the selected
model behavior changes, or the report schema/summary differs. This reproduces
deployed inference against a sanitized fixture; it does not reproduce training
from the intentionally ignored private dataset.

The harness uses two model components. Its main round-value model comes from
the selected release manifest and `full_replay_value.txt`; the action-analysis
component comes from `candidate_action_value.txt`. The wrapper follows the
active pointer, currently `backend/replay_engine/model/artifacts/releases/v5`. Pass
`--candidate-model` to override only
the action model. If the candidate LightGBM artifact cannot load, the loader
falls back to that release's `small_statistical.json`; if no candidate model is
available, the harness reports no action alternative instead of inventing one.
After training a new release, select it explicitly with `--release-dir` and
`--version` (or update the release pointer) before testing it:

```powershell
python backend/replay_engine/training/test_harness.py match.json `
  --release-dir backend/replay_engine/model/artifacts/releases `
  --version v4
```

### Advanced configuration

The deployable runtime can produce one report that combines factual replay
evidence with estimated alternatives:

```powershell
python backend/replay_engine/training/test_harness.py data/private/processed/full_replays.jsonl `
  --record-index 0 `
  --release-dir model/artifacts/releases `
  --version v4 `
  --max-moments 25 `
  --output data/private/processed/replay_analysis.json
```

Use `--all-moments` for a complete event audit. This removes the default
25-moment coaching cap; the embedded `full_match` report already retains all
deduplicated kill/death/bomb evidence in every mode:

```powershell
python backend/replay_engine/training/test_harness.py backend/tests/fixtures/coach_full_replay.json `
  --all-moments --sample-every 1 `
  --output data/private/processed/coach_fixture.analysis.json
```

Each kill line and JSON row contains both estimates when legal candidate
actions are available. Release v3 coaches the victim from `decision_tick`, one
second before first contact, and exposes all utility components on the selected
action. `least_death_risk_action` uses the literal engagement death head when
available; older releases use a round-loss proxy. Both include support,
outcome-variance, interval-level/method, and `risk_source` metadata. If the model
has no candidate state, the fallback is `null`; low-support fallbacks should
be treated as suggestions for review rather than proven best moves. The JSON
also reports `least_risk_fallback_count` (selected while the primary label
abstained), `least_risk_candidate_count`, and `least_risk_usable_count`.

To test a newly trained candidate model before promoting it into a release,
pass its standalone artifact explicitly:

```powershell
python backend/replay_engine/training/test_harness.py `
  backend/tests/fixtures/coach_full_replay.json `
  --candidate-model data/private/artifacts/candidate_v3/candidate_action_value.txt `
  --all-moments --sample-every 1
```

To check whether a replay is covered by the candidate-action model without
running training, inspect the canonical replay or the combined report with the
read-only coverage diagnostic:

```powershell
python backend/replay_engine/training/candidate_coverage.py `
  data/private/processed/coach_fixture.analysis.json `
  --min-support 5
```

The JSON summary reports total/analyzed kills, supported and unsupported
candidate rows, and missing support grouped by map, side, zone, bomb state,
alive-count difference, and round-time bucket. High-entropy states are
reported separately from low sample support, and a kill is counted as fully
supported only when every candidate row is supported. Passing a JSONL file
aggregates the counts across records; no input file is modified.

The same diagnostic accepts the extractor output. In that mode it reports
strict pre-event rows emitted and skip reasons (for example, missing snapshots)
before any model-support threshold is applied:

```powershell
python backend/replay_engine/training/candidate_coverage.py `
  data/private/processed/candidate_states.json
```

To build a directional candidate-action dataset, first extract strictly
pre-event states and generate the leakage-safe rubric label sidecar. The
sidecar stores only one compact row per state/action and excludes later round
outcomes:

```powershell
python backend/replay_engine/training/candidate_states.py `
  data/private/processed/full_replays.jsonl `
  data/private/processed/candidate_states.json

python backend/replay_engine/training/candidate_labels.py `
  data/private/processed/candidate_states.json `
  data/private/processed/candidate_labels.jsonl `
  --format jsonl

python backend/replay_engine/training/split_candidate_dataset.py `
  data/private/processed/candidate_states.json `
  data/private/processed/candidate_split `
  --labels data/private/processed/candidate_labels.jsonl

python backend/replay_engine/training/train_candidate_value.py `
  data/private/processed/candidate_split/train_candidate_states.json `
  data/private/artifacts/candidate_v5 `
  --labels data/private/processed/candidate_split/train_candidate_labels.jsonl

python backend/replay_engine/training/evaluate_candidate_value.py `
  data/private/processed/candidate_split/heldout_candidate_states.json `
  data/private/artifacts/candidate_v5 `
  data/private/processed/candidate_v5_evaluation.json `
  --labels data/private/processed/candidate_split/heldout_candidate_labels.jsonl
```

The candidate trainer treats `preferred` and `risky` rubric labels as binary
suitability targets and excludes `unknown` rows. It records the rubric version
and target in `candidate_training_metrics.json` and the candidate model
metadata. It requires action-label variation within a state and a whole-match
held-out split before producing a promotable directional model.

The simulator rollout path remains useful as a diagnostic for the compact
simulator, but its labels are not a directional training target when every
legal action receives the same round winner:

```powershell
python backend/replay_engine/training/candidate_rollouts.py `
  data/private/processed/candidate_states.json `
  data/private/processed/candidate_rollouts.jsonl `
  --rollouts 8

python backend/replay_engine/training/split_candidate_dataset.py `
  data/private/processed/candidate_states.json `
  data/private/processed/candidate_rollouts.jsonl `
  data/private/processed/candidate_split

python backend/replay_engine/training/train_candidate_value.py `
  data/private/processed/candidate_split/train_candidate_states.json `
  data/private/processed/candidate_split/train_candidate_rollouts.jsonl `
  data/private/artifacts/candidate_v3

python backend/replay_engine/training/evaluate_candidate_value.py `
  data/private/processed/candidate_split/heldout_candidate_states.json `
  data/private/processed/candidate_split/heldout_candidate_rollouts.jsonl `
  data/private/artifacts/candidate_v3 `
  data/private/processed/candidate_v3_evaluation.json
```

The state extractor excludes same-tick and future outcomes. Rollout files keep
aggregate wins/losses per legal action rather than storing simulation traces.
The trainer always writes the compact Bayesian model and writes the LightGBM
candidate model when the optional full dependencies are available.
The held-out evaluator reports Brier score, log loss, top-action agreement and
support coverage; held-out demos must remain separate from training inputs.
The trainer splits by complete `record_index` groups. With only one replay it
writes a prior for inspection but refuses to produce a promotable full model;
add a second complete training demo before measuring generalisation.
The training metrics also report whether rollout outcomes vary across actions.
If the compact simulator has no action-outcome variance, the resulting model
is useful for plumbing and priors but is not evidence that one tactical action
is causally better. Its current survival field is explicitly marked as a
no-combat simulator diagnostic; use real damage/death horizons before treating
it as death-risk probability.

The command prints one line per kill with its round/tick, observed action,
best estimated action, lowest-risk fallback, proxy probabilities, support,
fallback status, and probability label. Use `--show-moments` when keeping the normal 25-moment cap
but still wanting the detailed table. `summary.kill_count` is the total kill
count in the replay; `summary.kill_analysis_count` is the number scored by the
current moment cap.

### Analysis JSON shape

The saved `.analysis.json` report is a JSON object. Probabilities are stored as
decimal values from `0.0` to `1.0`; the CLI display converts them to
percentages. The following is a valid representative output containing the
summary and one enriched kill row (the real report also includes the complete
`full_match` timeline and detailed `moments` array):

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

`least_death_probability` is explicitly a round-loss proxy until real
engagement/death labels are available. `least_death_risk_status` and
`least_death_risk_usable` must be checked before presenting that action as
coaching advice. A `null` improvement probability means the probability layer
abstained; it is not a zero-percent estimate.

The report first selects key moments from round-value swings and kill/death/
bomb events. It then reconstructs the nearest legal simulator state, scores
only actions accepted by `cs2_sim.rules.legal_actions`, and stores the complete
ranked `candidate_actions` list. `best_estimated_alternative` is therefore a
simulator action-value estimate, not a proven counterfactual. A moment is
classified as `good`, `bad`, or `neutral` only when both the observed action
and the best candidate have at least `--min-support` observations; otherwise
the harness emits `insufficient_evidence` or `no_observed_action`.

The current reconstructed state uses the simulator's default topology. Replay
nav-area labels are retained, but a map-specific navigation adapter is still
needed before movement alternatives can be treated as authoritative CS2-legal
routes; the report records this scope in `candidate_legality`.

### Probability-based decision labels

The combined report keeps the original `decision_class` for compatibility and
adds a conservative uncertainty-aware label. For each supported observed and
candidate action it reports:

- `probability_of_improvement`: estimated probability that the best candidate's
  success probability exceeds the observed action;
- `expected_regret`: posterior expected positive probability gap;
- `posterior_comparison`: seeded Beta-posterior Monte Carlo comparison,
  including the probability of beating the observed action by the configured
  margin;
- `credible_intervals`: approximate 90% intervals for the observed and best
  candidate estimates;
- `probability_abstention`: threshold values and a reason when evidence is too
  weak or intervals are too wide.

The default label thresholds are `min_support=5`,
`probability_of_improvement=0.80`, `expected_regret=0.05`, credible level
`0.90`, and maximum interval width `0.80`. These labels are estimates from
observational/simulator support, not proof of a counterfactual. The interval
method is explicitly marked as a support-proxy normal approximation unless
posterior success/failure counts are available. `insufficient_evidence` and
all abstention reasons must remain visible to API and UI clients.

The CLI emits the same additive probability fields. Its Beta comparison uses
5,000 seeded posterior draws by default; tune this with
`--posterior-samples` and `--posterior-seed` when trading accuracy for speed.

This keeps the two evaluation questions separate: full-match metrics measure
round-value prediction, while candidate quality is evaluated later against a
held-out tactical benchmark or human-reviewed labels. The harness does not
claim that an estimated alternative was objectively better when the replay
does not contain enough state or outcome support.

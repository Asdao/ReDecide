# Training the two replay-value models

Data is split into public and private roots. Public metadata and maps may be
uploaded after checking their source license; raw demos, parsed replay data,
SQLite databases, features, and user uploads stay under `data/private`. See
[`DATA_LAYOUT.md`](DATA_LAYOUT.md).

The lightweight pipeline uses parsed `.analysis.json` sidecars. It does not
download the very large `.dem` file for every match.

For application code, use `training.TrainingPipeline` as documented in
[`docs/MODULE_API.md`](MODULE_API.md). The commands below remain the supported
shell interface for individual pipeline stages.

## One complete run

Use the project Python and set `PYTHONPATH` first:

```powershell
$env:PYTHONPATH = "model/src"

python -m training.download_dataset sidecars --max-files 500 --max-gb 0.25

python -m training.extract_features `
  --input data/private/sidecars `
  --output data/public/processed/analysis_snapshots.jsonl `
  --decision-window-seconds 5

python -m training.train_snapshot_model

python -m training.train_full_replay `
  --snapshot-input data/public/processed/analysis_snapshots.jsonl
```

## Sharing the exact same sidecar data

The repository includes `training/sidecars_manifest.json`, a lock file for the
500 sidecars used by the lightweight pipeline. It records every dataset path,
byte count, and SHA-256 checksum. A new user can download that exact set with:

```powershell
$env:PYTHONPATH = "model/src"
python -m training.download_dataset locked `
  --manifest training/sidecars_manifest.json `
  --output data/private/sidecars
```

The command reuses a file only when its checksum matches; otherwise it
re-downloads it and verifies the result. To check an existing directory without
downloading anything, run:

```powershell
python -m training.download_dataset verify `
  --manifest training/sidecars_manifest.json `
  --input data/private/sidecars
```

If the upstream selection changes later, regenerate a new manifest explicitly
with `download_dataset lock`; do not silently replace the checked-in one.

## SQLite replay database

JSONL remains the portable parser output, but the queryable training store is
SQLite. Build it after native parsing:

```powershell
python -m training.build_replay_db `
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
python -m training.audit_replays `
  --input data/private/processed/full_replays.jsonl `
  --report data/private/processed/replay_audit.json
```

For normal training, read SQLite directly instead of rebuilding features from
the full JSONL:

```powershell
python -m training.train_full_replay `
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
python -m training.train_baselines --database data/private/databases/cs2_replays_v2.sqlite
python -m training.evaluate_models `
  model/artifacts/releases/v2/full_replay_metrics.json `
  model/artifacts/releases/v2/statistical_baseline_metrics.json `
  --output model/artifacts/releases/v2/model_comparison.json
```

LightGBM plus the Bayesian snapshot model is the deployed replay-value
ensemble. Gaussian/logistic reports are advisory baselines only; the
comparison command rejects reports built from a different dataset or split.

Train the movement-frequency and zone-transition tools from SQLite:

```powershell
python -m training.train_action_models `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --action-output model/artifacts/releases/v2/action_frequency.json `
  --transition-output model/artifacts/releases/v2/zone_transitions.json
python -m training.evaluate_actions `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --output model/artifacts/releases/v2/action_evaluation.json
```

Action labels are deterministic observed movement tendencies (`hold`/`move`)
over a fixed two-second window. They are not claims about a strategically
optimal or “best” CS2 move; the held-out action report makes that distinction
explicit.

Combat engagement windows are available as a separate, additive export. They
anchor on damage events (or kills when no damage table exists) and emit one row
per participant. Features stop at the anchor tick; `label_kill`,
`label_death`, `label_trade`, `survived_after_kill`, and `round_won` inspect
only later events inside the configured horizon. The output describes observed
outcomes, not a tactical recommendation:

```powershell
python -m training.engagement_windows `
  --input data/private/processed/full_replays.jsonl `
  --output data/private/processed/engagement_windows.jsonl `
  --horizon-seconds 1 2 5
```

This writes `engagement_windows_1s.jsonl`, `engagement_windows_2s.jsonl`, and
`engagement_windows_5s.jsonl`. Existing SQLite events can be read directly
with `--database`; no database rebuild or model retraining is performed.

Train the dependency-free engagement prior with a whole-match held-out split:

```powershell
python -m training.train_engagement_model `
  --input data/private/processed/engagement_windows_2s.jsonl `
  --output model/artifacts/releases/v2/engagement_model.json `
  --metrics model/artifacts/releases/v2/engagement_metrics.json
```

The trainer reports kill/death/trade log loss, Brier score, calibration, and
improvement over the training prior. Sparse trade/survival targets use a
stronger empirical-Bayes prior; this avoids treating one observed duel as a
reliable tactical rule. If the full dependencies are installed, optional
shallow LightGBM heads use the same grouped split:

```powershell
python -m training.train_engagement_lightgbm `
  --input data/private/processed/engagement_windows_2s.jsonl `
  --output model/artifacts/releases/v2/engagement_lightgbm.json `
  --metrics model/artifacts/releases/v2/engagement_lightgbm_metrics.json
```

Refresh the checksummed release manifest after changing an artifact:

```powershell
python -m training.build_release_manifest `
  --release model/artifacts/releases/v2
```

## Compact Parquet exports and dataset registry

SQLite remains the canonical training store. When a portable, typed projection
is useful, stream it into a new directory without loading the whole database:

```powershell
python -m training.export_parquet `
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
python -m training.dataset_registry validate `
  --registry data/private/dataset_registry.json
python -m training.dataset_registry list `
  --registry data/private/dataset_registry.json
```

At runtime, load the single manifest and use the Bayesian fallback if the
optional LightGBM native library is unavailable:

```python
from cs2_sim import ModelConfig, ReplayModel

model = ReplayModel.load(ModelConfig(version="v2"))
prediction = model.predict_probability(snapshot)
match_report = model.analyse_match(replay)
engagement_report = model.analyse_engagement(replay, tick=1234, player_id="steam-id")
```

`analyse_engagement` returns observed kill/death/trade probabilities for
future-only windows. It marks statistical-only and LightGBM-blended results;
it does not claim an observational replay proves a counterfactual “best move”.

To install and activate a verified local release bundle:

```powershell
python -m training.download_models `
  --source path/to/cs2-model-bundle-v2 `
  --releases model/artifacts/releases `
  --version v2 `
  --activate `
  --require-checksums
```

Run the end-to-end tester against SQLite, parsed JSONL, or a native demo:

```powershell
python -m training.test_replay_models `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --manifest model/artifacts/releases/v2/full_replay_value.manifest.json `
  --action-model model/artifacts/releases/v2/action_frequency.json `
  --limit 500

python -m training.test_replay_models `
  --input data/private/processed/full_replays.jsonl `
  --limit 500

python -m training.test_replay_models --demo path/to/match.dem --limit 500
```

The replacement extractor can be used at the tester boundary as well. This
normalizes its JSONL in memory and reuses the existing model artifacts; it does
not rebuild SQLite or retrain either model:

```powershell
python -m training.test_replay_models `
  --extractor-input path/to/replacement-extractor.jsonl `
  --limit 500 `
  --output model/artifacts/replay_model_test_extractor.json

python -m training.test_replay_models `
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
python -m training.benchmark_dataset `
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
python -m training.evaluate_benchmark `
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
successfully and run `training.train_full_replay` without `--snapshot-input`.

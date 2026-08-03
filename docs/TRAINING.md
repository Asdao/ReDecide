# Training the two replay-value models

The lightweight pipeline uses parsed `.analysis.json` sidecars. It does not
download the very large `.dem` file for every match.

## One complete run

Use the project Python and set `PYTHONPATH` first:

```powershell
$env:PYTHONPATH = "src"

python -m training.download_dataset sidecars --max-files 500 --max-gb 0.25

python -m training.extract_features `
  --input data/small/sidecars `
  --output data/small/processed/analysis_snapshots.jsonl `
  --decision-window-seconds 5

python -m training.train_snapshot_model

python -m training.train_full_replay `
  --snapshot-input data/small/processed/analysis_snapshots.jsonl
```

## SQLite replay database

JSONL remains the portable parser output, but the queryable training store is
SQLite. Build it after native parsing:

```powershell
python -m training.build_replay_db `
  --input data/full/processed/full_replays.jsonl `
  --output data/full/processed/cs2_replays.sqlite `
  --action-window-seconds 2 `
  --replace
```

The database contains `matches`, `replays`, `rounds`, `players`, `player_ticks`,
`events`, `inferred_actions`, and leakage-safe `snapshots` tables, with foreign
keys and indexes for replay/round/player/action queries. It uses Python's
built-in `sqlite3`, so no database server is required.

Run a read-only audit before rebuilding:

```powershell
python -m training.audit_replays `
  --input data/full/processed/full_replays.jsonl `
  --report data/full/processed/replay_audit.json
```

For normal training, read SQLite directly instead of rebuilding features from
the full JSONL:

```powershell
python -m training.train_full_replay `
  --database data/full/processed/cs2_replays.sqlite `
  --calibrator models/full_replay_calibrator.json `
  --manifest models/full_replay_value.manifest.json
```

The lightweight baselines can be compared with:

```powershell
python -m training.train_baselines --database data/full/processed/cs2_replays.sqlite
python -m training.evaluate_models `
  models/full_replay_metrics.json `
  models/statistical_baseline_metrics.json
```

Train the movement-frequency and zone-transition tools from SQLite:

```powershell
python -m training.train_action_models `
  --database data/full/processed/cs2_replays.sqlite
```

At runtime, load the single manifest and use the Bayesian fallback if the
optional LightGBM native library is unavailable:

```python
from cs2_sim.core.model import ReplayValueEnsemble

model = ReplayValueEnsemble.load("models/full_replay_value.manifest.json")
prediction = model.predict_ct_win(snapshot)
```

Run the end-to-end tester against SQLite, parsed JSONL, or a native demo:

```powershell
python -m training.test_replay_models `
  --database data/full/processed/cs2_replays.sqlite `
  --limit 500

python -m training.test_replay_models `
  --input data/full/processed/full_replays.jsonl `
  --limit 500

python -m training.test_replay_models --demo path/to/match.dem --limit 500
```

The test report includes held-out replay-value metrics, action counts, and
nav-region transitions. `training.map_regions` uses the downloaded nav mesh
area IDs and the Awpy radar transform for overlays.

The downloader reads the compact metadata already stored under
`data/small/metadata`. It rejects incomplete maps by requiring at least 16
rounds and 80 kills, ranks higher-star/recent matches first, and selects maps
round-robin to avoid a Mirage/Dust2-heavy subset. Change `--min-rounds`,
`--min-kills`, `--min-stars`, or `--max-files` when needed.

## What is leakage-safe here

The extractor keeps only the five seconds beginning with the first real kill.
It excludes `round_end`, states after either team reaches zero alive players,
and setup/world kills. The first kill is used because lightweight sidecars do
not contain damage ticks. Native demos can later use the first damage event as
a better contact marker.

Training and validation are separated by entire demo, not random snapshot.
The saved deployment artifacts are retrained on all rows only after validation
metrics have been computed. Metrics include log loss, Brier score, balanced
accuracy, expected calibration error, and comparison with the training-set CT
win-rate baseline.

## Outputs

- `models/small_snapshot_value.json`: hierarchical Bayesian model. It backs
  off through exact state, broader state, map, and global evidence.
- `models/full_replay_value.txt`: LightGBM model blended with a split-safe 20%
  Bayesian prior during evaluation.
- `models/small_snapshot_metrics.json` and
  `models/full_replay_metrics.json`: demo-separated validation results.
- `models/full_replay_value.manifest.json`: deployable Bayesian/LightGBM
  component manifest.

The event-only full model estimates round win probability. It is not yet a
movement/action model because sidecars contain no player positions, health,
utility inventory, visibility, or velocity. For that model, parse native demos
successfully and run `training.train_full_replay` without `--snapshot-input`.

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

The event-only full model estimates round win probability. It is not yet a
movement/action model because sidecars contain no player positions, health,
utility inventory, visibility, or velocity. For that model, parse native demos
successfully and run `training.train_full_replay` without `--snapshot-input`.

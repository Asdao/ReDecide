# Model profiles

The analyser has two interchangeable profiles. Both expose the existing
`ActionPolicy` interface, so the simulator and future API do not need to know
which model is selected.

The matching data layout is:

```text
data/
├── small/metadata/     # compact Parquet metadata
└── full/               # selected raw demos and processed replay rows
```

## Small profile

`SmallStatisticalModel` is dependency-free and is the default for the current
small metadata and simulator-generated examples. It combines:

- Dirichlet-smoothed action counts;
- Beta-smoothed action outcomes; and
- normalized Shannon entropy for uncertainty.

The replay-value variant (`SnapshotValueModel`) adds hierarchical Bayesian
backoff from exact states to broader state, map, and global evidence. This is
important because an exact CS2 state may never have appeared in training.

It is saved as one small JSON file and works even when LightGBM cannot be
installed.

## Full profile

`FullLightGBMModel` uses the same features and blends a LightGBM action-value
prediction with the small statistical model. It is intended for parsed replay
snapshots and larger labelled datasets. LightGBM is an optional dependency:

```powershell
pip install -e ".[full]"
```

The model is trained on one row per `(state, candidate_action)` and a binary
success label. Training examples are represented by
`cs2_sim.core.model.TrainingExample`. The native LightGBM dependency is imported
only when `fit()` or `load()` is called. Pass a separately trained
`SmallStatisticalModel` into the constructor so the two dataset tiers remain
independent; the full model then combines both predictions at inference time.

## Selecting a profile

```python
from cs2_sim.core.model import create_model

model = create_model("small")  # current compact data
model = create_model("full")   # larger replay dataset after parsing
```

Both models return only a legal action when passed the simulator's legal-action
list. The full profile falls back to the small profile before training, which
makes incremental development possible.

## Bootstrap training

Until raw replay parsing supplies action labels, train a monitored bootstrap
pair from simulator outcomes:

```powershell
$env:PYTHONPATH = "src"
python -m training.train_models --states 500
```

This writes `models/small_statistical.json`, `models/full_lightgbm.txt`, and
`models/bootstrap_metrics.json`. These artifacts are useful for testing the
tool interface, but should be retrained after full replay-derived examples are
available.

The replay extractor writes event snapshots with the future outcome stored as
`label_round_winner`. Treat that field as a label only; do not include it in
the model input features.

Train the small snapshot model with:

```powershell
$env:PYTHONPATH = "src"
python -m training.train_snapshot_model
```

The default input is now
`data/small/processed/analysis_snapshots.jsonl`. See `docs/TRAINING.md` for the
quality-filtered download, leakage-safe extraction, and both training commands.

The full parser is launched with:

```powershell
python -m training.parse_demos
```

It uses Awpy/demoparser2 when PyArrow is available. If native PyArrow loading
is blocked, it records the existing analysis sidecar as a fallback and marks
the record with `parser: "analysis_sidecar"`; those fallback records do not
contain positional ticks.

When positional ticks are present, train the full replay-value model with:

```powershell
python -m training.train_full_replay
```

The trainer requires at least two parsed demos so validation can be separated
by whole demo. It blends the LightGBM prediction with the small snapshot model
when `models/small_snapshot_value.json` exists.

While native positional parsing is unavailable, a provisional event-only
LightGBM model can use the same leakage-safe snapshot dataset:

```powershell
python -m training.train_full_replay `
  --snapshot-input data/small/processed/analysis_snapshots.jsonl
```

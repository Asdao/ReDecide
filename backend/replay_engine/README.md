# CS2 Match Analysis Prototype

This repository contains an early Counter-Strike 2 replay-analysis prototype.
Its current focus is **replay-value prediction**: given a structured snapshot of
a round, estimate the chance that the CT side wins. A separate agent harness can
explain bounded simulator results in natural language.

The project is not yet a complete “upload a match and receive a full coaching
report” application.

## Current pipeline

```text
CS2 .dem or analysis sidecar
        -> parse and normalize replay data
        -> extract leakage-safe round snapshots
        -> predict CT round-win probability
        -> optionally inspect movement/action frequencies
        -> explain bounded results through the agent harness
```

The model only receives information available at the snapshot time. The later
round winner is used as a training label, but is not included as an input
feature.

## What the replay model predicts

The deployable replay-value model is an ensemble:

- **LightGBM (80%)**: trained on replay snapshot features.
- **Hierarchical Bayesian model (20%)**: backs off from exact states to broader
  state, map, and global evidence when a state is rare or unseen.
- **Calibration**: the saved manifest can apply a Platt probability calibrator.
- **Uncertainty**: estimated from the amount of matching Bayesian training data.

Features include map, elapsed time, CT/T alive counts, health, armor, player
positions, bomb state/site, kills, damage, shots, utility events, and bomb time
remaining. The model returns a probability, not a guaranteed outcome.

The current full artifact was trained from 2,513 rows in the SQLite replay
database, with validation separated by complete demos. Its held-out,
one-snapshot-per-round accuracy is about 66.3%. This measures round-outcome
prediction; it is **not** a measure of player-decision quality or coaching
accuracy.

## Current data boundaries

The lightweight sidecar path focuses on the five seconds beginning at the first
real kill. It excludes terminal states and future events from the model input.
Native demo parsing can provide richer positional and event data through Awpy,
but it is optional.

The sibling [`extractor`](extractor/README.md) package provides a
separate path for parsing, normalizing, segmenting, and storing replay data in
SQLite.

## Install

The core simulator and Bayesian models use Python 3.12+ and have no required
runtime dependencies:

```powershell
python -m pip install -e .
```

For native `.dem` parsing and the full LightGBM model:

```powershell
python -m pip install -e ".[full]"
```

For the standalone extractor:

```powershell
python -m pip install -e backend/replay_engine/extractor
```

## Run the simulator

From the repository root:

```powershell
$env:PYTHONPATH = "backend/replay_engine/model/src;backend/replay_engine/extractor/src;."
python main.py
```

This runs a deterministic example round and prints its winner, duration, and
events. The TypeScript agent harness exposes the same simulator through the
bounded `simulate_round` tool:

```powershell
cd agent-harness
pnpm install
pnpm build
pnpm test
pnpm dev -- --prompt "Run seed 7 for the example scenario with the baseline policy"
```

The harness currently supports the `example` and `planted` scenarios and the
`baseline` and `bayesian` policies. It deliberately exposes only bounded,
read-only simulator output to the language model.

## Train or test the replay models

The documented training workflow is in [`docs/TRAINING.md`](docs/TRAINING.md).
The main commands are:

```powershell
$env:PYTHONPATH = "backend/replay_engine/model/src;backend/replay_engine/extractor/src;."
python -m backend.replay_engine.training.train_snapshot_model
python -m backend.replay_engine.training.train_full_replay `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --output model/artifacts/releases/v2/full_replay_value.txt `
  --small-model-output model/artifacts/releases/v2/small_snapshot_value.json `
  --calibrator model/artifacts/releases/v2/full_replay_calibrator.json `
  --manifest model/artifacts/releases/v2/full_replay_value.manifest.json
```

To test the saved artifacts against a database, parsed JSONL file, or native
demo:

```powershell
python -m backend.replay_engine.training.test_replay_models `
  --database data/private/databases/cs2_replays_v2.sqlite `
  --manifest model/artifacts/releases/v2/full_replay_value.manifest.json `
  --limit 500
```

For the combined key-moment and candidate-action harness, pass only the
extracted replay data:

```powershell
python backend/replay_engine/training/test_harness.py data/private/processed/full_replays.jsonl
```

The runner writes an adjacent `.analysis.json` report. Use
`--record-index` for JSONL files containing multiple replays. It falls back to
the bundled statistical components when native LightGBM is not installed.

Application code accesses the complete harness through one function. It accepts
a native demo, JSON/JSONL path, canonical extractor mapping, or normalized
replay mapping:

```python
from backend.replay_engine import analyze_replay

report = analyze_replay("match.dem")
print(report["summary"])
```

Load the deployable ensemble in Python:

```python
from cs2_sim import ModelConfig, ReplayModel

model = ReplayModel.load(ModelConfig(version="v2"))
prediction = model.predict(snapshot)
print(prediction.probability, prediction.uncertainty)
```

The loader is strict by default: missing or checksum-mismatched components fail
fast. Use `allow_fallback=True` only for an explicit degraded Bayesian-only
smoke check.

## Repository layout

- `backend/replay_engine/model/src/cs2_sim/` — deterministic CS2 state, rules, simulator, and model code.
- `training/` — feature extraction, replay storage, training, calibration, and
  evaluation scripts.
- `extractor/` — standalone replay parsing and normalization package.
- `agent-harness/` — TypeScript/Pi boundary with the bounded simulator tool.
- `backend/replay_engine/model/artifacts/` — generated model artifacts and metrics.
- `docs/` — detailed plans, training notes, reliability guidance, and target
  analysis architecture.
- `training/tests/`, `model/tests/`, and `extractor/tests/` — tests grouped by ownership.

## Programmatic API

Application code should use the public facades exported by each package:

- `backend.replay_engine.analyze_replay` for the complete replay-analysis harness.
- `replay_extractor.ReplayExtractor` for parsing and normalization.
- `backend.replay_engine.training.TrainingPipeline` for database preparation and training.
- `cs2_sim.ReplayModel` for runtime inference.

The supported imports, lifecycle, error types, and examples are documented in
[`docs/MODULE_API.md`](docs/MODULE_API.md). Lower-level files remain available to
the facades and CLI commands but are not the stable application interface.

## What is not implemented yet

The following are planned rather than complete:

- a production web UI for uploading and analyzing a full match;
- an `analyze_replay` endpoint/tool;
- automatic pivotal-decision detection;
- before/after win-score comparison for a player decision;
- a complete evidence-backed Decision Card;
- reliable player-specific counterfactual coaching across a whole match.

The target design is described in
[`agent-harness/docs/ANALYSIS_PIPELINE.md`](../agent-harness/docs/ANALYSIS_PIPELINE.md).
The reliability rules for any future LLM coaching layer are in
[`03_AI_COACH_RELIABILITY.md`](../03_AI_COACH_RELIABILITY.md).

## Important limitation

The system currently predicts **round state value**, not whether a player made a
good or bad decision. A round win or loss is not enough to judge a decision:
the eventual outcome must remain separate from the evidence available when the
decision was made.

# Public module API standard

Application code should use the three package-level facade classes described
here. Files below each package are implementation details and may change without
requiring callers to change.

## Shared rules

1. Import public classes from the package root only.
2. Construct one frozen configuration object, then pass it to one facade object.
3. Pass paths as `str` or `Path`; public methods normalize them internally.
4. Use returned dataclasses instead of inferring output filenames.
5. Catch the module's public error type at application boundaries.
6. Do not import underscored functions, CLI `main()` functions, repositories, or
   individual training scripts from application code.

The dependency direction is:

```text
extractor output -> training pipeline -> model artifacts -> runtime model
```

The runtime model does not import the extractor or training implementation.

## Extractor module

Stable imports:

```python
from replay_extractor import ExtractorConfig, ExtractorError, ReplayExtractor
```

Use `ReplayExtractor` for parsing, normalization, segmentation, JSONL batch
parsing, and extractor-vault ingestion:

```python
from replay_extractor import ExtractorConfig, ReplayExtractor

extractor = ReplayExtractor(
    ExtractorConfig(tick_interval=32, heatmap_cell_size=256)
)

replay = extractor.parse("match.dem")
segments = extractor.segment(replay)

batch = extractor.parse_batch("data/demos", "data/processed/replays.jsonl")
vault = extractor.ingest(batch.output_path, "data/processed/extractor.sqlite")
print(batch.parsed, vault.stats)
```

`ReplayRecord`, `SegmentedReplay`, `ParseBatchResult`, and `IngestionResult` are
stable return types. Catch `ExtractorError` when extraction failure should be
reported at an application boundary.

## Training module

Stable imports:

```python
from Noah.training import TrainingConfig, TrainingError, TrainingPipeline
```

Use `TrainingPipeline` for database preparation and artifact generation:

```python
from Noah.training import TrainingConfig, TrainingPipeline

pipeline = TrainingPipeline(
   TrainingConfig(
      artifact_dir="model/artifacts/releases/v3",
      seed=7,
      clean_records=True,
   )
)

result = pipeline.run(
   "data/processed/replays.jsonl",
   "data/processed/replays.sqlite",
   replace_database=True,
)
print(result.replay.manifest)
```

For explicit orchestration, call `prepare_database()`, `train_replay_model()`,
and `train_action_models()` separately. Training methods return typed artifact
paths; callers should not reconstruct those filenames. Catch `TrainingError` at
job-runner or API boundaries.

## Model module

Stable imports:

```python
from cs2_sim import ModelConfig, ModelError, ReplayModel
```

Use `ReplayModel` to load the active release and perform all runtime inference:

```python
from cs2_sim import ModelConfig, ReplayModel

model = ReplayModel.load(
    ModelConfig(releases_dir="model/artifacts/releases", allow_fallback=True)
)

prediction = model.predict(snapshot)
action_scores = model.action_probabilities(
    map_name="de_mirage",
    side="ct",
    zone="A_SITE",
    legal_actions=["hold", "move"],
)
next_zone = model.predict_next_zone("A_SITE", map_name="de_mirage", side="ct")
match_report = model.analyse_match(replay)
replay_analysis = model.analyse_replay(
    replay,
    max_moments=25,
    min_support=5,
    probability_of_improvement_threshold=0.80,
    expected_regret_threshold=0.05,
    credible_level=0.90,
    posterior_samples=5000,
    posterior_seed=7,
)
engagement_report = model.analyse_engagement(replay, tick=1234, player_id="steam-id")
one_window_score = model.score_engagement(leakage_safe_engagement_window)
ranked = model.rank_candidate_actions([
    {"action": "hold", "death_probability": 0.31, "round_value_delta": 0.03, "sample_count": 20, "entropy": 0.4},
])
print(prediction.probability, action_scores, next_zone)
```

`analyse_replay` combines a deterministic key-moment report with support-aware
candidate ranking. For kills, release v3 coaches the victim from a decision
cutoff one second before contact using three seconds of prior history. Abstract
`hold` and `move` candidates are scored by round-win, survival, kill, trade,
damage, and simulator-value heads. It labels `good`/`bad` only when observed
and candidate actions have enough support; otherwise it abstains. Detailed
simulator actions still record their default-topology legality scope.
`analyse_engagement`, `score_engagement`, and `rank_candidate_actions` remain
observational: a ranked alternative is not proof that a player should have
made that move.

For application code that already has one normalized extracted replay, the
complete analysis call is simply:

```python
from cs2_sim import ModelConfig, ReplayModel

model = ReplayModel.load(ModelConfig(allow_fallback=True))
analysis = model.analyse_replay(replay_record, max_moments=None)
print(analysis["kill_analysis"])
```

For a file-based entry point that also parses a native `.dem` or normalizes
canonical replacement-extractor JSON/JSONL, use the user-facing wrapper:

```python
from Noah.training.test_harness import run_replay_test

analysis = run_replay_test("match.dem", max_moments=None, sample_every=1)
analysis_from_json = run_replay_test(
    "data/private/processed/extractor_record.json",
    max_moments=None,
)
```

Both calls return the same combined report shape. The `kill_analysis` array
contains one enriched row per kill, including `decision_tick`, coached player,
the selected action's probability heads, and coaching utility; `moments` contains the detailed candidate
state and `full_match` retains the deterministic timeline. No database rebuild
or retraining occurs during either analysis call.

The small statistical candidate model uses hierarchical support: it first
looks for an exact state, then backs off to zone/bomb, side/bomb, side, and
global priors. Candidate rows expose `support_level` and `raw_support`; the
effective `sample_count` is discounted for broader backoff levels.

Pass `max_moments=None` when auditing a complete replay and every detected
kill/death/bomb moment should receive a candidate-analysis entry. The default
cap of 25 is intended for bounded coaching responses. The nested
`full_match.events` list and `event_counts` retain all deduplicated event
evidence in either mode.

The response also contains additive probability-based fields under each
moment. `probability_of_improvement` estimates the probability that the best
supported candidate exceeds the observed action, and `expected_regret` is the
posterior expected positive probability gap. `posterior_comparison` contains a
seeded Beta-posterior Monte Carlo comparison, including the probability that
the candidate beats the observed action by the configured margin. Each action
has a `credible_interval` and each moment has `credible_intervals`; these are
support-proxy, normal-approximation intervals unless posterior success/failure
counts are supplied. They are uncertainty indicators, not guarantees.

`probability_decision_class` is the thresholded label (`good`, `bad`,
`neutral`, or `insufficient_evidence`). The legacy `decision_class` remains
unchanged for compatibility. `probability_abstention` records whether the
probability label abstained, the reason, and the exact thresholds used. The
default thresholds are minimum support 5, probability of improvement 0.80,
expected regret 0.05, 90% intervals, and maximum interval width 0.80. Clients
must display abstention and uncertainty rather than converting them into a
binary good/bad verdict.

The Monte Carlo comparison defaults to 5,000 seeded posterior draws; callers
can override `posterior_samples` and `posterior_seed` on `analyse_replay`.

Callers provide structured fields and never construct internal action-state keys
or load component files independently. `model.status` reports which optional
components were loaded. Catch `ModelError` at service boundaries.

## Compatibility policy

The facade classes, configuration fields, result dataclasses, and package-root
imports are the supported API. Existing CLI commands remain supported wrappers
for shell use. Internal modules can be refactored as long as facade behavior and
tests remain compatible. Removing or renaming a public facade member requires a
documented deprecation period or a major package version change.

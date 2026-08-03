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
engagement_report = model.analyse_engagement(replay, tick=1234, player_id="steam-id")
ranked = model.rank_candidate_actions([
    {"action": "hold", "death_probability": 0.31, "round_value_delta": 0.03, "sample_count": 20, "entropy": 0.4},
])
print(prediction.probability, action_scores, next_zone)
```

`analyse_engagement` and `rank_candidate_actions` are explicitly
observational: legal candidate actions must come from the simulator/map rules,
and a ranked alternative is an estimated outcome rather than proof that a
player should have made that move.

Callers provide structured fields and never construct internal action-state keys
or load component files independently. `model.status` reports which optional
components were loaded. Catch `ModelError` at service boundaries.

## Compatibility policy

The facade classes, configuration fields, result dataclasses, and package-root
imports are the supported API. Existing CLI commands remain supported wrappers
for shell use. Internal modules can be refactored as long as facade behavior and
tests remain compatible. Removing or renaming a public facade member requires a
documented deprecation period or a major package version change.

# Noah Component Status

Last verified: 2026-08-04 (Asia/Singapore)

## Current status

The Noah training package remains an offline replay-value/model-artifact
component and is not the frozen RE:DECIDE runtime contract. Its public training
facade is `Noah.training.TrainingPipeline`.

Replay training now records one coherent release version and inferred or
explicit tick rate. Streamed sidecar training reuses the snapshot Bayesian
artifact without overwriting it; held-out metrics use a development-only
in-memory prior when the deployable artifact was trained over all streamed
rows.

Release bundles can be staged and validated through the complete
`release_manifest.json`, including replay components, feature schema, optional
metrics/dataset paths, checksums, and release-directory version identity.

## Important paths

- `Noah/training/api.py` — public `TrainingPipeline` and configuration.
- `Noah/training/train_full_replay.py` — replay-value training and metadata.
- `Noah/training/train_streamed_sidecars.py` — sidecar orchestration.
- `Noah/training/model_bundle.py` — release staging and validation.
- `Noah/training/build_release_manifest.py` — complete release manifest.
- `Noah/model/artifacts/releases/` — generated release artifacts.

## Verification

From the repository root:

```powershell
uv run pytest Noah/training/tests -q -p no:cacheprovider -o "pythonpath=Noah/model/src Noah/extractor/src ."
```

Latest result: 104 passed. Focused release validation also passes through
`Noah/model/tests/test_model_bundle.py` and
`Noah/training/tests/test_contracts.py`.

Training smoke run against
`data/private/databases/cs2_replays_v2.sqlite` completed into the isolated
temporary release `C:\tmp\smoke-20260804`: 1,168 rows, 894 development rows,
274 held-out rows, 0.5565 held-out log loss, and 0.1907 Brier score. Strict
checksum validation and stage/activate validation both passed. The checked-in
release directories were not modified.

## Limitations and handoff

- LightGBM remains an optional full-training/runtime dependency; strict release
  loading requires the `[full]` extra.
- Existing outcome-based replay models must not be connected directly to the
  frozen RE:DECIDE coaching contract without replay-packet and leakage review.
- The root integration owner should review the package-layout change in
  `pyproject.toml` before treating Noah as integrated into the new backend.

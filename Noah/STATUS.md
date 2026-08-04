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

The candidate-action component now supports a compact `candidate_label_v1`
sidecar. Its deterministic pre-event rubric produces `preferred`, `risky`, or
`unknown` suitability labels from the serialized decision state only. The
candidate trainer/evaluator can consume those labels, and the split utility
keeps the label sidecar match-separated. The existing simulator-rollout path
remains available for diagnostics but is not directional training evidence
when all actions share the same simulator outcome.

The local `Noah/model/artifacts/releases/v5` bundle contains the
suitability-trained candidate artifact, has a checksummed `release_manifest.json`,
and is active through `current.json` (previous release `v4`). The public harness
now follows that active pointer by default; callers can still pass an explicit
release version.

## Important paths

- `Noah/training/api.py` — public `TrainingPipeline` and configuration.
- `Noah/training/train_full_replay.py` — replay-value training and metadata.
- `Noah/training/train_streamed_sidecars.py` — sidecar orchestration.
- `Noah/training/model_bundle.py` — release staging and validation.
- `Noah/training/build_release_manifest.py` — complete release manifest.
- `Noah/model/artifacts/releases/` — generated release artifacts.

The candidate label sidecar and trainer are implemented in
`Noah/training/candidate_labels.py`, `Noah/training/train_candidate_value.py`,
and `Noah/training/evaluate_candidate_value.py`.

## Verification

From the repository root:

```powershell
uv run pytest Noah/training/tests -q -p no:cacheprovider -o "pythonpath=Noah/model/src Noah/extractor/src ."
```

Latest result: 110 passed. Focused release validation also passes through
`Noah/model/tests/test_model_bundle.py` and
`Noah/training/tests/test_contracts.py`.

The v5 release manifest passed strict validation for 19 components. The focused
release/candidate suite passed 23 tests; the harness/release suite passed 19
tests with the optional LightGBM dependency enabled. An active-pointer
end-to-end smoke against the first real replay record loaded v5 and emitted
`full_lightgbm_blended_with_small_statistical_rubric_suitability`.

Candidate-label smoke training on the existing compact candidate states
produced 3,351 states and 4,616 trainable rubric rows, with 2,308 comparable
state groups. A match-held-out evaluation completed in an isolated temporary
directory; no checked-in release or active pointer was changed. These metrics
measure reproduction of the deterministic rubric, not real-world strategic
correctness.

Training smoke run against
`data/private/databases/cs2_replays_v2.sqlite` completed into the isolated
temporary release `C:\tmp\smoke-20260804`: 1,168 rows, 894 development rows,
274 held-out rows, 0.5565 held-out log loss, and 0.1907 Brier score. Strict
checksum validation and stage/activate validation both passed. The checked-in
release directories were not modified.

## Limitations and handoff

- LightGBM remains an optional full-training/runtime dependency; strict release
  loading requires the `[full]` extra.
- Candidate rubric labels are weak labels and must be reviewed against a
  representative human set before being treated as coaching truth.
- Existing outcome-based replay models must not be connected directly to the
  frozen RE:DECIDE coaching contract without replay-packet and leakage review.
- The root integration owner should review the package-layout change in
  `pyproject.toml` before treating Noah as integrated into the new backend.

# Replay Pipeline Status

Last verified: 2026-08-04 (Asia/Singapore)

Owner: Person 2 - CS2 Replay Data and Decision Detection

## Status

**Replay selector/progress pipeline and UI coaching merge are implemented.**

`backend/app/replay/replay_engine_extractor.py` now wraps the replay engine's public
`ReplayExtractor` facade. It parses or normalizes a replay, segments it, and
returns the replay engine's canonical `ReplayRecord` plus `SegmentedReplay` through a stable
backend error boundary. `pipeline.py` now indexes first-damage decisions for
all players, streams progress, keeps the global win estimator unfiltered, and
provides `merge_pi_output` for attaching redacted Pi coaching to the original
UI result without mutating the replay file.

## Required input and output

- Input: legal CS2 `.dem` sample plus selected player
- Output: frozen version `1.0` `DecisionPacket`
- Decision family: `POST_CONTACT_RESET` only
- Knowledge boundary: facts at or before `decision_open_tick`
- Observed-action boundary: no evidence after `action_close_tick`

## Existing work to review

`backend/replay_engine/extractor/` is the canonical parsing, normalization, and segmentation
implementation used by the connector. `backend/replay_engine/training/` contains potentially
reusable replay-processing and feature-extraction work. Person 2 must review
capability, licensing, evidence semantics, and future-information leakage
before using either path to build a packet.

Changes under `backend/replay_engine/**` should preserve the public replay
engine facade and its model-release contracts; coordinate ownership changes
with the replay-engine maintainer.

## Important paths

```text
backend/app/replay/**
backend/tests/test_replay_*.py
data/samples/**
```

## Tests and validation

Focused connector tests:

```powershell
uv run pytest backend/tests/test_replay_engine_extractor.py
```

The source paths are configured directly in `pyproject.toml` for the renamed
`backend.replay_engine` package:

```powershell
$env:PYTHONPATH = "backend/replay_engine/extractor/src;backend/replay_engine/model/src;."
uv run pytest backend/tests/test_replay_engine_extractor.py -q
```

Result: 3 tests passed. The current tests
verify canonical normalization/segmentation, stable errors for missing files,
and wrapping of extractor failures. No native `.dem` sample is checked in, so
native parsing and sidecar fallback are not yet verified at this boundary.

The current selector/merge tests are run with:

```powershell
uv run --with pytest python -m pytest backend/tests/test_replay_pipeline.py -q
```

Result: 5 tests passed on 2026-08-04. This covers processed replay JSONL input,
player selection, player-scoped event references, monotonic progress, the
global win estimator, and merging an opaque Pi decision reference back to the
authoritative player name.

The standalone Replay FastAPI and coaching handoff are also verified with:

```powershell
uv run --no-project --with pytest --with fastapi --with httpx --with pydantic --with python-multipart pytest backend/tests/test_replay_api.py backend/tests/test_analysis_api.py -q
```

Result: 13 tests passed on 2026-08-04. This covers one-time `.dem` parsing,
the shared `visualization.json`/`coaching.json` artifacts, player-first
preparation, and unlocking full visualization JSON only after coaching.

Required coverage includes deterministic output, unique evidence IDs, cutoff
ticks, forbidden outcome keys, stable player/round selection, missing-field
warnings, and typed invalid-demo errors.

## Known limitations and blockers

- The native `.dem` parser still depends on the workstation's optional parser
  environment; processed JSONL is the deterministic local integration input.
- `backend/app/main.py` now exposes the two-stage FastAPI job transport:
  `/api/analysis/prepare` creates a replay job and selector, `/run` accepts the
  selected player, `/events` streams progress, and `/logs` persists JSONL
  records. The default service is constructed with `PiCoachAdapter`; injected
  adapters remain available for deterministic tests. The frozen
  `DecisionPacket`/`DecisionCard` coach contract is still separate from this
  replay-job result.
- The frozen `DecisionPacket`/`DecisionCard` API contracts remain a separate
  integration surface and are not yet emitted by this replay-job result.

## Contract/API impact

The existing pipeline result is unchanged. When a Pi response is merged, the
returned UI mapping gains `selected_decision.player_name` and a
`coach_analysis` object containing the original decision/player identity and
the model's full-sentence coaching fields. The source replay is read-only.

## Next work

Align the replay-job result with the frozen product contract only after the
contract boundary is explicitly agreed; keep the current replay result stable
while that adapter is implemented.

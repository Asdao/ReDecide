# Replay Pipeline Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 2 - CS2 Replay Data and Decision Detection

## Status

**Extractor connector implemented; RE:DECIDE packet export is not yet
implemented.**

`backend/app/replay/noah_extractor.py` now wraps Noah's public
`ReplayExtractor` facade. It parses or normalizes a replay, segments it, and
returns Noah's canonical `ReplayRecord` plus `SegmentedReplay` through a stable
backend error boundary. It does not yet select a player/decision window or
export a `DecisionPacket`.

## Required input and output

- Input: legal CS2 `.dem` sample plus selected player
- Output: frozen version `1.0` `DecisionPacket`
- Decision family: `POST_CONTACT_RESET` only
- Knowledge boundary: facts at or before `decision_open_tick`
- Observed-action boundary: no evidence after `action_close_tick`

## Existing work to review

`Noah/extractor/` is the canonical parsing, normalization, and segmentation
implementation used by the connector. `Noah/training/` contains potentially
reusable replay-processing and feature-extraction work. Person 2 must review
capability, licensing, evidence semantics, and future-information leakage
before using either path to build a packet.

Do not modify or relocate `Noah/**` without coordinating with Noah.

## Important paths

```text
backend/app/replay/**
backend/tests/test_replay_*.py
data/samples/**
```

## Tests and validation

Focused connector tests:

```powershell
uv run pytest backend/tests/test_replay_noah_connector.py
```

In this checkout, the same three tests were verified with Noah's source paths
explicitly available:

```powershell
$env:PYTHONPATH = "Noah/extractor/src;Noah/model/src;."
python -m unittest discover -s backend/tests -p "test_replay_noah_connector.py" -v
```

Result: 3 tests passed. The direct `uv run pytest` invocation currently cannot
import `replay_extractor` because the root test configuration still points at
legacy `extractor/src` rather than `Noah/extractor/src`. The current tests
verify canonical normalization/segmentation, stable errors for missing files,
and wrapping of extractor failures. No native `.dem` sample is checked in, so
native parsing and sidecar fallback are not yet verified at this boundary.

Required coverage includes deterministic output, unique evidence IDs, cutoff
ticks, forbidden outcome keys, stable player/round selection, missing-field
warnings, and typed invalid-demo errors.

## Known limitations and blockers

- No executable `DecisionPacket` contract is available to import yet.
- The connector does not apply `decision_open_tick` or `action_close_tick`
  filtering; it returns the complete canonical replay for the next detector
  layer.
- No selected-player/round decision detector or evidence-ID exporter exists in
  this path yet.
- No legal bundled sample is present under `data/samples/`.

## Contract/API impact

None implemented. Import the contract owned by Person 1; do not redefine it.

## Next handoff

After Person 1 freezes the executable contract, add the decision-window
detector and `DecisionPacket` exporter on top of this connector, then produce
one hand-inspected JSON packet and the parser capability matrix so Persons 3
and 4 can proceed.

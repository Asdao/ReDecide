# Replay Pipeline Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 2 - CS2 Replay Data and Decision Detection

## Status

**Not implemented in the new RE:DECIDE path.**

`backend/app/replay/` currently contains no parser adapter, contact detector,
action classifier, or `DecisionPacket` exporter.

## Required input and output

- Input: legal CS2 `.dem` sample plus selected player
- Output: frozen version `1.0` `DecisionPacket`
- Decision family: `POST_CONTACT_RESET` only
- Knowledge boundary: facts at or before `decision_open_tick`
- Observed-action boundary: no evidence after `action_close_tick`

## Existing work to review

`Noah/extractor/` and `Noah/training/` contain potentially reusable extraction
and replay-processing work. Person 2 must review capability, licensing, evidence
semantics, and future-information leakage before integrating any portion.

Do not modify or relocate `Noah/**` without coordinating with Noah.

## Important paths

```text
backend/app/replay/**
backend/tests/test_replay_*.py
data/samples/**
```

## Tests and validation

No RE:DECIDE replay tests exist in the new path yet.

Required coverage includes deterministic output, unique evidence IDs, cutoff
ticks, forbidden outcome keys, stable player/round selection, missing-field
warnings, and typed invalid-demo errors.

## Known limitations and blockers

- No parser adapter has been selected and verified for the bundled sample in
  this path.
- No legal bundled sample is present under `data/samples/`.
- No executable `DecisionPacket` contract is available to import yet.

## Contract/API impact

None implemented. Import the contract owned by Person 1; do not redefine it.

## Next handoff

After Person 1 freezes the executable contract, produce one hand-inspected JSON
packet and the parser capability matrix so Persons 3 and 4 can proceed.

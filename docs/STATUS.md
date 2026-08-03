# Evidence, QA, Pitch, and Demo Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 5 - User Evidence, QA, Pitch Deck, and Demo

## Status

**Not implemented in the new RE:DECIDE documentation path.**

`docs/` currently contains no RE:DECIDE interview evidence, human evaluation
set, QA matrix results, deck draft, demo script, disclosure inventory, or
submission checklist beyond this status file.

## Required outputs

- Anonymized interview notes with consented quotes only
- Masked human review protocol and 20+ credible cases when possible
- Development/validation/untouched-holdout split
- Three-condition comparison with raw counts and denominators
- QA issues with decision ID, reproduction, severity, expected, and actual result
- Maximum 15-slide PDF content and maximum five-minute demo script
- Third-party API, parser, model, dataset, and licence disclosure inventory
- Final submission checklist

## Important paths

```text
docs/**
data/eval/human/**
```

## Dependencies

Coordinate packet cases with Person 2, rubric/model evaluation with Person 3,
usability testing with Person 4, and final README/integration claims with Person
1.

## Tests and validation

No RE:DECIDE human evaluation or QA results are recorded yet. Do not add
placeholder percentages, invented interviews, testimonials, or legal claims.

## Known limitations and blockers

- No recorded interview set or reviewer assignments.
- No masked decision cases in `data/eval/human/`.
- No integrated product path available for the QA matrix or usability tests.

## Contract/API impact

None. Person 5 provides evidence and labels but does not modify shared runtime
contracts.

## Next handoff

Freeze interview questions and the evaluation sheet, then review the first
parser packets without exposing later outcomes.

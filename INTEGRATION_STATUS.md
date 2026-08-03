# RE:DECIDE Integration Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 1 - Team Lead, Platform, and Integration

## Overall status

**The executable version 1.0 contract and fixture foundation is integrated;
the RE:DECIDE API and end-to-end vertical slice are not yet integrated.**

Merge commit `3f5645c` on `main` contains the shared Pydantic contracts,
checked-in JSON fixtures, dependency declaration, lockfile update, and focused
contract tests. Persons 2, 3, and 4 can now build independently against this
shared boundary while Person 1 implements the API walking skeleton.

## Integrated capabilities

- Five role briefs define the agreed scope and seven-day plan.
- `AGENTS.md` defines repository-wide working rules and required context reads.
- `Project_Context.md` defines scope, architecture, ownership, and frozen
  boundaries.
- Empty ownership paths exist for replay, coach, frontend, samples, evaluation,
  and documentation work.
- `backend/app/contracts.py` provides executable version `1.0`
  `DecisionPacket`, `IntentInput`, and `DecisionCard` Pydantic contracts plus
  their nested types, frozen enums, and the `AnalyzeJsonRequest` transport
  envelope.
- Contract validation rejects facts after `decision_open_tick`, action windows
  that close before they open, duplicate evidence references, unsupported enum
  values, unexpected fields, invalid schema versions, and confidence outside
  the `0.0` to `1.0` range.
- Checked-in fixtures provide one valid packet, intent, card, and
  `/api/analyze-json` request under `backend/tests/fixtures/`.
- Pydantic `>=2.7,<3` is declared in `pyproject.toml`; `uv.lock` currently
  resolves Pydantic `2.13.4`.

## Not integrated yet

- TypeScript versions of `DecisionPacket`, `IntentInput`, and `DecisionCard`
- FastAPI application, orchestration, typed errors, and the approved two-stage
  prepare-then-analyze transport
- `GET /api/health`, `GET /api/samples`, `POST /api/prepare`,
  `POST /api/analyze-json`, and `POST /api/analyze`
- Fixture card response through the API
- Outcome-blind first-contact detector and `DecisionPacket` exporter
- Real pretrained-model call through the frozen coach boundary
- Deterministic evidence, future-information, contradiction, confidence, and
  abstention validators
- Four-screen frontend and knowledge-boundary visualization
- Bundled legal sample demo and representative evaluation set
- Clean-machine RE:DECIDE setup and end-to-end test

## Existing work awaiting component review

- `Noah/` contains extractor, model, training, API, benchmark, documentation,
  tests, and model artifacts.
- Root `agent-harness/` contains the existing Pi-to-Python simulator harness.
- Root `main.py`, `pyproject.toml`, and `uv.lock` remain shared integration and
  dependency surfaces. Pydantic is now integrated, but the legacy setuptools
  package paths and pytest paths still reference root `model/`, `training/`,
  and `extractor/` locations that no longer exist and require coordination
  before cleanup.

Existing code must not be described as integrated merely because it is present.
The relevant owner must map it to the frozen contract, remove future/outcome
leakage from the RE:DECIDE path, and run focused tests.

## Current integration risks

- Contributor names have not yet been mapped to all five numbered roles in this
  document.
- `observed_action.evidence_ids` are version `1.0` traceability references; the
  current packet supplies their human-readable meaning through
  `observed_action.description` rather than separate expandable evidence
  records.
- The root `.gitignore` has overlapping `data/*` rules that can block new
  sanitized public, sample, and evaluation files until corrected.
- No model-provider key and spend limit are recorded as confirmed.
- No bundled `.dem` sample is recorded as legally cleared and reproducible.
- Existing simulator/model flows may include winner or later-outcome information
  and cannot be connected directly to the coach.

## Next integration gate

Person 1 should implement the FastAPI walking skeleton and approved two-stage
transport: prepare a validated fixture packet before intent, then accept packet
plus intent through `POST /api/analyze-json` and return the packet with a
validated fixture card. Person 4 can render the checked-in fixtures while this
transport is being implemented.

## Component handoffs

- [Replay pipeline](backend/app/replay/STATUS.md)
- [AI coach and reliability](backend/app/coach/STATUS.md)
- [Frontend](frontend/STATUS.md)
- [Evidence, QA, pitch, and demo](docs/STATUS.md)

## Latest verification

- Verified merged `main` at commit `3f5645c` on 2026-08-03.
- Runtime used Pydantic `2.13.4`.
- Command:

  ```powershell
  python -m unittest discover -s backend/tests -p "test_contracts.py" -v
  ```

- Result: 9 tests passed.
- No API, replay, coach, frontend, or end-to-end tests are claimed yet.

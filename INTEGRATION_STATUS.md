# RE:DECIDE Integration Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 1 - Team Lead, Platform, and Integration

## Overall status

**Repository scaffold created; the new RE:DECIDE vertical slice is not yet
integrated.**

The shared ownership directories and context documents now exist. The current
root and `Noah/` implementations predate or sit beside the frozen RE:DECIDE
contracts and must be reviewed through the appropriate component boundary before
reuse.

## Integrated capabilities

- Five role briefs define the agreed scope and seven-day plan.
- `AGENTS.md` defines repository-wide working rules and required context reads.
- `Project_Context.md` defines scope, architecture, ownership, and frozen
  boundaries.
- Empty ownership paths exist for replay, coach, frontend, samples, evaluation,
  and documentation work.
- Git ignores large data while allowing the empty ownership skeleton to remain
  trackable.

## Not integrated yet

- Pydantic and TypeScript versions of `DecisionPacket`, `IntentInput`, and
  `DecisionCard`
- FastAPI application and the four minimal endpoints
- Checked-in request/response fixtures
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
  dependency surfaces.

Existing code must not be described as integrated merely because it is present.
The relevant owner must map it to the frozen contract, remove future/outcome
leakage from the RE:DECIDE path, and run focused tests.

## Current integration risks

- Contributor names have not yet been mapped to all five numbered roles in this
  document.
- The shared contracts exist only in the role brief, not executable schemas.
- No model-provider key and spend limit are recorded as confirmed.
- No bundled `.dem` sample is recorded as legally cleared and reproducible.
- Existing simulator/model flows may include winner or later-outcome information
  and cannot be connected directly to the coach.

## Next integration gate

Person 1 should freeze executable contracts and fixtures, then expose a fixture
card through `POST /api/analyze-json`. Persons 2, 3, and 4 can build independently
against that fixture before the real parser/model path is ready.

## Component handoffs

- [Replay pipeline](backend/app/replay/STATUS.md)
- [AI coach and reliability](backend/app/coach/STATUS.md)
- [Frontend](frontend/STATUS.md)
- [Evidence, QA, pitch, and demo](docs/STATUS.md)

## Latest verification

- Documentation and repository-structure validation only.
- No application tests were required or run for the context/status-file change.
- Do not add test claims here until the corresponding merged component has been
  run from its documented path.

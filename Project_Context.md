# RE:DECIDE Shared Project Context

Last reviewed: 2026-08-03 (Asia/Singapore)

This is the team's stable shared context. Read it together with `AGENTS.md`,
`INTEGRATION_STATUS.md`, the applicable component `STATUS.md`, and the relevant
numbered role brief before changing the repository.

The numbered briefs are the authoritative source for product scope, contracts,
acceptance criteria, and role-specific details. This file summarizes stable
shared rules; current implementation state belongs in the status files.

## Product

- Name: **RE:DECIDE**
- Promise: **"Don't replay the match. Replay the decision."**
- Game: Counter-Strike 2
- Input: parsed `.dem` telemetry, not full-match video
- AI: one pretrained GPT/Claude-style model behind an adapter, bounded by CS2
  evidence, a coaching rubric, deterministic validators, and abstention
- MVP decision family: reset versus re-engage after first damage contact
- Deadline strategy: working vertical slice by Day 3; feature freeze on Day 5

The product evaluates one immediate post-contact choice: re-engage,
reset/reposition, reload, or wait for support. It asks for the player's intent
before returning one evidence-linked Decision Card and one cue-based practice
quest.

## Non-negotiable boundaries

1. Do not expand beyond CS2 post-contact reset decisions for the MVP.
2. Do not train or fine-tune a model from scratch for RE:DECIDE.
3. The LLM never parses a raw `.dem` file.
4. The parser establishes facts; experts establish rules; the LLM applies and
   explains those rules.
5. `known_before_decision` contains only facts available at or before
   `decision_open_tick`.
6. The observed action may use only the short window ending at
   `action_close_tick`.
7. Nothing after `action_close_tick` may reach the coaching model or influence
   candidate selection.
8. Do not judge a choice by whether the player later died, survived, won, or
   lost the round.
9. Missing or contradictory evidence must produce an unknown, an unclassified
   action, or `INSUFFICIENT_EVIDENCE`; never invent a fact.
10. Humans validate a representative evaluation set, not every future output.

## Frozen interfaces

The semantics of these version `1.0` interfaces are frozen in
`01_TEAM_LEAD_PLATFORM_INTEGRATION.md`:

- `DecisionPacket`: deterministic, evidence-linked parser output
- `IntentInput`: player intent tag plus optional one-sentence explanation
- `DecisionCard`: evidence-linked verdict, options, trade-offs, limitations,
  computed checks, and one next-match quest

Do not silently change field names, enum values, cutoff semantics, or evidence
rules. Contract changes require Person 1 to propose the smallest migration and
notify Persons 2, 3, and 4 before implementation.

## Intended runtime flow

```text
CS2 .dem
  -> replay parser and decision detector
  -> validated DecisionPacket
  -> player IntentInput
  -> coaching rubric and pretrained LLM
  -> deterministic evidence/future/contradiction/confidence checks
  -> validated DecisionCard
  -> frontend evidence view and practice quest
```

Minimal API owned by Person 1:

- `GET /api/health`
- `GET /api/samples`
- `POST /api/analyze`
- `POST /api/analyze-json`

`/api/analyze-json` and checked-in fixtures are the integration fallback while
the real parser and model path are being completed.

## Current repository state

At the time of this update:

- The five role briefs and `AGENTS.md` exist at the repository root.
- The RE:DECIDE ownership skeleton exists, but the new `backend/` and
  `frontend/` application code has not been implemented yet.
- `backend/app/coach/` and `backend/app/replay/` contain placeholders only.
- `data/samples/`, `data/eval/model/`, and `data/eval/human/` contain
  placeholders only. Actual large datasets remain ignored by Git.
- `docs/` and `frontend/` contain placeholders only.
- `Noah/` contains Noah's existing extractor, model, training, API, benchmark,
  documentation, tests, and model-artifact work. It is potentially reusable,
  but it is not automatically the frozen RE:DECIDE runtime contract.
- Root `agent-harness/`, `agent-harness-plan/`, `main.py`, `pyproject.toml`, and
  `uv.lock` are existing shared/experimental surfaces. Coordinate with the lead
  and their original owner before reorganizing or modifying them.
- The current agent harness is a bounded Pi-to-Python simulator harness. Its
  safety patterns may be reusable, but its synthetic round/winner flow is not
  the outcome-blind RE:DECIDE product flow.
- `DecisionPacket`, `IntentInput`, and `DecisionCard` have not yet been encoded
  as production Pydantic/TypeScript contracts in the new skeleton.

Do not move another person's current folder into the skeleton for them. Each
owner should integrate or copy only the parts they have reviewed and can test.

## Ownership map

Ownership means the named person may implement inside the listed paths. It does
not grant permission to change frozen interfaces or overwrite another owner's
work.

### Person 1 - Team Lead, Platform, and Integration

Primary responsibilities:

- Freeze and maintain shared contracts.
- Build the FastAPI skeleton, orchestration, shared errors, and API integration.
- Connect replay, coach, and frontend work.
- Keep `main` runnable and own final setup, README, and demo fallback paths.

Owned paths and files:

```text
backend/app/main.py
backend/app/contracts.py
backend/app/orchestration.py
backend/tests/test_contracts.py
backend/tests/test_api.py
backend/tests/fixtures/**
README.md
.env.example
AGENTS.md
Project_Context.md governance sections
INTEGRATION_STATUS.md
```

Person 1 may resolve integration conflicts but should not rewrite teammate-owned
implementation files without coordinating with that owner.

### Person 2 - CS2 Replay Data and Decision Detection

Primary responsibilities:

- Parse legal CS2 `.dem` samples into normalized telemetry.
- Detect outcome-blind first-contact decision windows.
- Classify the immediate observed action deterministically.
- Emit evidence IDs, unknowns, quality warnings, and leakage-safe packets.

Owned paths:

```text
backend/app/replay/**
backend/tests/test_replay_*.py
data/samples/**
```

Person 2 imports `DecisionPacket` from Person 1 and must not edit the shared
contract directly.

### Person 3 - AI Coach, Rubric, and Reliability

Primary responsibilities:

- Implement the provider adapter and versioned coaching rubric.
- Produce structured `DecisionCard` output from packet plus intent.
- Implement evidence, future-information, contradiction, confidence, and
  abstention gates in deterministic code.
- Coordinate model evaluation labels and metrics with Person 5.

Owned paths:

```text
backend/app/coach/**
backend/tests/test_coach_*.py
data/eval/model/**
```

Person 3 must not train a new model from scratch or ask the LLM to compensate
for missing telemetry.

### Person 4 - Frontend Product Experience

Primary responsibilities:

- Build the four-screen sample/upload, progress, intent, and Decision Card flow.
- Implement the knowledge-boundary timeline and evidence expansion.
- Support live, sample, fixture, timeout, error, no-decision, and abstention
  states.

Owned path:

```text
frontend/**
```

Person 4 consumes the shared API and may not invent missing facts or expose
provider secrets in browser code.

### Person 5 - User Evidence, QA, Pitch, and Demo

Primary responsibilities:

- Conduct and document user interviews without fabricating quotes or metrics.
- Maintain masked human review cases, QA results, and honest denominators.
- Own deck content, demo script, disclosures, and submission checklists.

Owned paths:

```text
docs/**
data/eval/human/**
```

Person 5 suggests root README content, while Person 1 owns the final README.

### Existing contributor-owned and shared surfaces

```text
Noah/**                 Noah; coordinate before editing or relocating
agent-harness/**        original owner plus Person 1 for agreed integration
agent-harness-plan/**   original owner plus Person 1 for agreed integration
main.py                 shared legacy/experimental entry point; ask first
pyproject.toml          shared dependency surface; Person 1 coordinates changes
uv.lock                 shared lockfile; update only with an intentional dependency change
01_*.md through 05_*.md frozen team briefs; Person 1 coordinates edits
```

If a contributor's name-to-person-number mapping differs from this document,
the team lead should update the mapping before parallel implementation begins.
Path ownership remains the merge-safety boundary in the meantime.

## Collaboration and Git rules

1. Start work from the latest `main`.
2. Work on the role branch named in the briefs:
   - `lead/integration`
   - `data/replay-pipeline`
   - `ai/coach-reliability`
   - `ux/decision-card`
   - `story/evidence-demo`
3. Keep commits small and merge reviewed work daily; do not isolate branches
   until Day 6.
4. Before editing, run `git status`, inspect the relevant paths, and read the
   applicable role brief.
5. Do not overwrite or reorganize another owner's files.
6. Contract or shared dependency changes require explicit coordination.
7. Pull or fetch before preparing a PR and resolve conflicts in the branch, not
   by discarding another person's work.
8. Run focused tests for the changed component and report anything not run.
9. Never commit API keys, raw private player information, uncontrolled large
   datasets, generated caches, or unlicensed samples.

## Seven-day coordination target

- Day 1: frozen contracts, fixtures, API walking skeleton, frontend fixture card
- Day 2: first real parser packet reaches first real model call
- Day 3: complete bundled-sample vertical slice
- Day 4: reliability/evidence review and representative evaluation cases
- Day 5: feature freeze, clean setup, demo candidate
- Day 6: rehearsals, final video, deck, and submission candidate
- Day 7: blocker fixes and final submission QA only

## Status and handoff documents

Use status files for current operational truth instead of appending daily logs
to this document:

```text
INTEGRATION_STATUS.md             Person 1; verified end-to-end state
backend/app/replay/STATUS.md      Person 2; replay pipeline handoff
backend/app/coach/STATUS.md       Person 3; coach and reliability handoff
frontend/STATUS.md                Person 4; frontend handoff
docs/STATUS.md                    Person 5; evidence, QA, pitch, and demo handoff
```

Each owner updates only their status file. Replace stale information instead of
keeping a chronological diary. Git history already records what changed over
time.

A useful component status must state:

- last verified date and branch/commit when known;
- current status and implemented behavior;
- inputs, outputs, and dependencies;
- important paths;
- exact test or validation commands and their latest verified results;
- known limitations and blockers;
- contract/API impact; and
- the next integration handoff.

Person 1 updates `INTEGRATION_STATUS.md` only after merged behavior has been
inspected and verified. Branch-local claims remain in the component status until
integration.

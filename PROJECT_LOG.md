# RE:DECIDE Overall Project Log

Last reviewed: 2026-08-04 (Asia/Singapore)

This file is a current-state snapshot of the repository. It is intentionally
additive: the role briefs and component status files remain unchanged and
continue to hold their own ownership and handoff details.

## Product in one sentence

RE:DECIDE is an outcome-blind Counter-Strike 2 decision coach: it reconstructs
what was knowable around a post-contact choice, asks for player intent, and
returns evidence-linked coaching rather than judging the later round outcome.

## Current implementation snapshot

### Integrated and executable

- `backend/app/contracts.py` defines strict version `1.0` Pydantic contracts:
  `DecisionPacket`, `IntentInput`, `DecisionCard`, and the JSON request envelope.
- `backend/app/main.py` exposes the FastAPI transport:
  `GET /api/health`, preparation, job metadata, player discovery, player
  selection/run, progress events, logs, and result retrieval.
- `backend/app/orchestration.py` owns the in-memory analysis jobs, background
  preparation, player selection, coach adapter invocation, JSONL logs, and
  stable HTTP-facing error states.
- `backend/app/replay/pipeline.py` indexes replay players and first-contact
  decision candidates, streams progress, filters a selected player, and merges
  redacted coaching output into the UI result.
- `backend/app/replay/noah_extractor.py` wraps Noah's public extractor facade
  behind a backend error boundary.
- `backend/app/coach/noah_connector.py` adapts Noah analysis output for the
  backend pipeline; the adapter is injectable for deterministic tests.
- `frontend/src/domain/contracts.ts` mirrors the executable version `1.0`
  contracts with strict Zod schemas, including cutoff and cross-reference
  validation.
- `frontend/src/app/page.tsx` provides the current static, outcome-blind
  landing experience. Upload and sample controls are deliberately disabled
  until the live preparation contract is finalized in the product flow.
- Noah's extractor, training package, release manifests, and active model
  pointer are present and independently tested, but are not by themselves the
  frozen RE:DECIDE coaching contract.

### Present but not yet a complete product path

- The frontend is fixture-first and does not yet expose the complete upload ->
  progress -> player intent -> Decision Card journey.
- The backend job API and the frozen `DecisionPacket`/`DecisionCard` contracts
  are separate integration surfaces; the job result is not automatically a
  `DecisionCard`.
- A native `.dem` parser depends on optional workstation dependencies. Processed
  JSONL and checked-in fixtures are the deterministic local integration path.
- The live Pi/LLM coaching transport and provider configuration are not
  confirmed as a production service boundary.
- Human evidence, masked review cases, QA results, pitch materials, and demo
  submission records are not currently present under `docs/` or
  `data/eval/human/`.
- The existing `agent-harness/` and `agent-harness-plan/` are experimental
  simulator/harness surfaces. Their synthetic round and winner-oriented flow
  must not be treated as the outcome-blind RE:DECIDE product path.

## Repository map

| Area | Current responsibility |
| --- | --- |
| `backend/app/` | FastAPI transport, contracts, orchestration, replay integration, coach adapter |
| `backend/tests/` | API, contract, replay, coach, and fixture tests |
| `frontend/` | Standalone Next.js/Zod fixture-first UI |
| `Noah/extractor/` | Replay parsing, normalization, segmentation, and extractor storage |
| `Noah/training/` | Offline database preparation, feature extraction, training, evaluation, and release staging |
| `Noah/model/` | CS2 simulation/model code and generated model artifacts |
| `agent-harness/` | Separate Pi-to-Python simulator harness and tools |
| `agent-harness-plan/` | Planning documents for that harness |
| `data/` | Checked-in directory placeholders plus ignored/private runtime and evaluation data |
| `docs/` | Evidence/status documentation; this snapshot and architecture overview are additive |

## Verification recorded in the repository

The latest component status files record these checks:

- Backend contracts: 9 tests passed on 2026-08-03.
- Replay connector: 3 tests passed with Noah source paths explicitly enabled.
- Replay pipeline: 5 tests passed on 2026-08-04.
- Coach connector and Noah harness: 16 tests passed on 2026-08-04.
- Frontend verification: 5 Vitest tests, TypeScript, ESLint, and production
  build passed on 2026-08-03.
- Noah training suite: 110 tests passed on 2026-08-04.

These are component-level results, not evidence of a fully integrated,
production-ready end-to-end flow.

## Safe interpretation rules

1. Treat `Project_Context.md` as the stable scope and ownership reference.
2. Treat `INTEGRATION_STATUS.md` as the Person 1 integration handoff.
3. Treat each component `STATUS.md` as that component's operational truth.
4. Treat this file as a cross-repository snapshot, not a replacement for those
   owner documents.
5. Do not describe code as integrated solely because it exists; use the
   contract mapping and focused test evidence.
6. Preserve the knowledge boundary: no facts after `decision_open_tick` may
   influence the packet or coaching decision, and later round outcomes must not
   be used to judge the choice.

## Next useful integration work

- Connect the backend job transport to the frozen packet/card response path.
- Define the frontend reducer and typed adapter for sample/upload, progress,
  intent, success, no-decision, abstention, timeout, and error states.
- Resolve native parser/runtime dependency setup and legally cleared sample
  handling.
- Add representative human review cases and QA evidence before making quality
  claims.

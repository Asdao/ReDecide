# RE:DECIDE Repository Architecture

Last reviewed: 2026-08-04 (Asia/Singapore)

## System boundary

```text
CS2 .dem or processed replay JSON
        |
        v
Noah extractor: parse -> normalize -> segment
        |
        v
backend replay pipeline: index players and first-contact candidates
        |
        v
FastAPI analysis job: prepare -> select player -> coach adapter
        |                                  |
        |                                  v
         |                           PiCoachAdapter / injected test adapter
        v
player-scoped UI result + progress/events/logs
        |
        v
post-match replay outcome (website/CLI only; never sent to Pi)

Separate product-contract path:
DecisionPacket + IntentInput -> validated DecisionCard -> frontend contract schemas
```

The upper flow is the currently implemented replay-job path. The lower path is
the frozen RE:DECIDE product contract boundary. They are related but are not yet
a single fully integrated end-to-end transport.

## Backend layers

### Transport: `backend/app/main.py`

`create_app()` builds the FastAPI application. It exposes health, preparation,
job metadata, player discovery, player selection, result retrieval, JSONL logs,
and server-sent progress events. HTTP exceptions translate the orchestration
layer's not-found, not-ready, selection, and runtime failures into stable
responses. The runnable reference client is
`Noah/backend demo/cli.py`; it calls these same public routes and is documented
in `backend/app/API.md`.

### Orchestration: `backend/app/orchestration.py`

`AnalysisService` stores jobs in memory and writes durable per-job JSONL logs.
Preparation runs in a thread pool over the replay pipeline. Once preparation is
complete, the caller selects a player. The service filters the cached replay,
invokes an injected `CoachAdapter`, merges the response, and marks the job
complete. `create_app()` uses `PiCoachAdapter` by default; tests can inject a
deterministic adapter. The adapter remains outside the HTTP layer so provider
calls, fixtures, and error handling can be tested independently.

### Contracts: `backend/app/contracts.py`

The strict version `1.0` models are the shared product boundary:

- `DecisionPacket`: outcome-blind replay facts, decision/action cutoffs,
  observed action, unknowns, and data quality.
- `IntentInput`: the player's intent tag and optional text.
- `DecisionCard`: verdict, confidence, facts used, alternatives, recommendation,
  limitations, deterministic checks, and a next-match quest.

Pydantic forbids extra fields, trims boundary strings, constrains enums and
numeric ranges, rejects future evidence in `known_before_decision`, and checks
unique evidence references.

### Replay: `backend/app/replay/`

`noah_extractor.py` wraps `Noah.extractor`'s public `ReplayExtractor` API.
`pipeline.py` consumes normalized replay-shaped mappings, tracks players and
events, produces player-scoped decision candidates, reports monotonic progress,
and merges coaching output without mutating the source replay.

### Coach: `backend/app/coach/`

`noah_connector.py` is an internal adapter for Noah analysis reports. It is not
the same object as a version `1.0` `DecisionCard`; conversion requires the
integration owner and coach owner to map the output to the frozen contract.
`pi_connector.py` is the server-side Pi bridge used by the default FastAPI
service. It receives only the selected, anonymized, outcome-blind decision
payload, validates the structured Pi response, and passes it to
`merge_pi_output`. Tests inject a deterministic adapter instead of making
provider calls.

## Frontend layers

`frontend/` is a standalone Next.js application. The current page is a static
landing/knowledge-boundary preview. `src/domain/contracts.ts` provides strict
Zod mirrors of the backend product contracts and local fixtures under
`src/fixtures/` support rehearsal and drift tests. The live controls are
disabled until the preparation and intent flow is wired, so the browser does
not invent an endpoint or show fixture output as live analysis.

## Noah offline subsystem

Noah is a reusable but separately governed subsystem:

```text
Noah/extractor -> canonical replay records -> Noah/training -> release artifacts
                                                   |
                                                   v
                                             Noah/model runtime
```

`Noah/extractor` handles native demos, sidecar fallback, normalization,
segmentation, and replay storage. `Noah/training` builds databases, trains
replay/action/candidate artifacts, evaluates them, and stages checksummed
releases. `Noah/model` contains simulation/model runtime code and generated
artifacts, with `releases/current.json` selecting the active release.

Noah's outcome-based model and simulator outputs must undergo packet mapping and
future-information/leakage review before being used by the RE:DECIDE coach.

## Data and runtime boundaries

- `backend/tests/fixtures/` contains small checked-in contract and replay
  fixtures for deterministic tests.
- `data/samples/` and `data/eval/*` are repository-owned locations, currently
  mostly placeholders; private/large data is ignored rather than bundled.
- `data/runtime/analysis-logs/` is the default location for per-job JSONL logs
  created by `AnalysisService`.
- `pyproject.toml` declares FastAPI/Pydantic runtime dependencies and optional
  full/data/test extras; `uv.lock` pins the environment.
- `frontend/package.json` and `frontend/pnpm-lock.yaml` pin the standalone web
  toolchain.

## Main architectural risks

- The in-memory job store is process-local; durable logs do not make job state
  horizontally shared.
- Native demo parsing depends on optional environment setup.
- The live provider endpoint and spend limits still require deployment-level
  verification. Local FastAPI calls inherit deployment variables; otherwise
  the Pi adapter passes the repository-root `.env` as `HARNESS_ENV_FILE`.
- The backend replay-job result and the frozen packet/card contract are not yet
  one response schema.
- There is no representative human evaluation set or end-to-end production
  validation recorded in the repository.

## Change ownership

Use `Project_Context.md` and `AGENTS.md` for ownership and required context.
In brief: Person 1 owns shared contracts/API/integration; Person 2 owns replay;
Person 3 owns coaching/reliability; Person 4 owns frontend; Person 5 owns
evidence/QA/pitch/demo; Noah and the harness remain separately owned surfaces.

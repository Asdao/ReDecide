# Frontend agent instructions

These instructions apply to all work under `frontend/`. The frontend branch is
currently maintained by one person, but existing work must still be inspected
and preserved before edits.

## Required context

Before changing frontend behavior:

1. Read `../backend/app/API.md`; it is the source of truth for the public API.
2. Read `../backend/replay_api/API.md` when implementing upload, replay status,
   or visualization download behavior.
3. Read `STATUS.md` for the current frontend implementation and limitations.
4. Inspect the relevant frontend files, tests, working-tree status, and diff.
5. Inspect the current backend route and fixture implementation when an API
   detail is unclear. Do not invent an endpoint or response shape.

## Scope

Build and maintain the browser UI under `frontend/**`. Do not edit backend code
unless the user explicitly asks for a coordinated backend change. Keep secrets,
provider configuration, replay contents, and server-only paths out of browser
code, logs, URLs, analytics, and persistent storage.

Use the existing Next.js, React, TypeScript, Zod, Tailwind, Vitest, and pnpm
setup. Reuse the current components, adapters, domain types, fixtures, and
visual conventions before creating replacements.

## Current user flow

The active uploaded-replay flow is:

```text
upload .dem
  -> receive replay manifest and replay_id
  -> prepare analysis with replay_id
  -> wait until players are available
  -> choose player_id
  -> run coaching (may take up to 30 seconds)
  -> validate and display the completed analysis
  -> retrieve the unlocked visualization JSON when needed
```

Rules:

- Upload the `.dem` once. The backend creates separate coaching and
  visualization artifacts; the browser must not parse or re-upload it after
  player selection.
- Display a player's `display_name`, but submit the stable `player_id`.
- Keep `replay_id`, `analysis_id`, and `player_id` distinct.
- Player intent and follow-up questions are not supported. Do not build or send
  intent data.
- Do not display player-specific coaching before a player is selected.
- The coaching call can take up to 30 seconds. Show truthful progress and allow
  reasonable network overhead before declaring a timeout.
- Validate every successful response before rendering it. Treat network data as
  `unknown`; do not use `any` at the API boundary.
- Do not reveal later round outcomes before the backend unlocks the full
  visualization JSON.

## Public API endpoints

Run the public gateway from the repository root with:

```powershell
uv run uvicorn backend.app.main:app --reload --port 8000
```

The following list mirrors `../backend/app/API.md`.

### Active APIs

| Method and path | Frontend use |
| --- | --- |
| `GET /api/health` | Check backend availability. Returns `{"status":"ok"}`. |
| `POST /api/replay/upload` | Upload one `.dem` as `multipart/form-data` in the `file` field. Returns `202` with a safe replay manifest containing `replay_id`, map, rounds, players, and processing status. |
| `POST /api/replay/import-url` | Optional public Vercel Blob import. Disabled by default and absent from OpenAPI unless `REDECIDE_BLOB_IMPORT_ENABLED=true`. |
| `GET /api/replay/{replay_id}/status` | Read the latest replay, coaching, visualization, and unlock status. |
| `GET /api/replay/{replay_id}/json` | Download the full minimap, timeline, positions, rounds, and events JSON after visualization generation is ready and coaching has unlocked it. |
| `POST /api/analysis/prepare` | Send `{"replay_id":"<replay_id>"}`. Returns `202` with `analysis_id`, status, and progress URLs. |
| `GET /api/analysis/{analysis_id}` | Poll job status, including `players_available` and `result_available`. |
| `GET /api/analysis/{analysis_id}/players` | Get selectable players and stable `player_id` values. A `202` means preparation is not ready yet. |
| `POST /api/analysis/{analysis_id}/run` | Send `{"player_id":"<player_id>"}`. Runs live coaching and returns the completed player analysis. This request may take up to 30 seconds. |
| `GET /api/analysis/{analysis_id}/result` | Retrieve the completed result without running coaching again. A `202` means it is not ready yet. |
| `GET /api/analysis/{analysis_id}/events` | Consume `text/event-stream` progress events while preparation or coaching runs. |
| `GET /api/analysis/{analysis_id}/logs` | Read saved plain-text JSONL progress logs for debugging or status display. Do not expose sensitive log details to users. |

Upload-specific behavior:

- Reject a non-`.dem` filename cleanly; the backend returns `415`.
- Treat parser failure as an upload error; the backend returns `422`.
- The backend currently imposes no explicit demo-size limit, although hosting
  infrastructure may impose one.
- The upload response already contains safe player metadata. The analysis
  player endpoint remains authoritative for coaching selection.
- `visualization_status: "ready"` is not sufficient for download;
  `visualization_unlocked` must also be `true`.
- `/api/replay/{replay_id}/json` can return `202` while processing, `403` while
  locked, `404` for an unknown replay, or `422` after visualization failure.

### Compatibility APIs

These endpoints exist but are not the primary uploaded-replay flow:

| Method and path | Status and use |
| --- | --- |
| `POST /api/replay/convert` | Older alias for `/api/replay/upload`. New frontend code must use `/api/replay/upload`. |
| `GET /api/samples` | Returns the old built-in sample list used by the frozen-contract demonstration. |
| `POST /api/analyze` | Prepares the old fixture sample from `sample_id` and an optional player name. It is not the uploaded-replay analysis flow. |

The current API does not provide a general database-backed sample-match flow
that enters the same `replay_id` pipeline as an upload. If the product requires
that behavior, surface it as a backend contract gap instead of pretending the
compatibility sample is equivalent.

`POST /api/analyze-json` is intentionally unavailable on the public gateway and
returns `404`. Never call it from the frontend.

## Frontend state and request handling

Represent the main flow with explicit states rather than unrelated booleans:

```text
choose source
  -> uploading
  -> preparing analysis
  -> choosing player
  -> running coaching
  -> result
```

Each request may also transition to a typed error, retry, or reset state. Keep
the source file, IDs, selected player, request ownership, and retryability
explicit. Use `AbortController`, ignore late responses after reset or a newer
request, and prevent duplicate uploads or coaching calls.

Use SSE progress when practical. Otherwise poll the documented status endpoint
without fabricating completed stages. A long request is not automatically a
failure. Preserve the result from `POST /run`; use `GET /result` for retrieval
or recovery without causing another model call.

Never silently replace a failed live upload with fixture or sample data. Any
fallback must be a user-selected action with persistent provenance explaining
that it is an example.

## UI and accessibility

- Keep the existing restrained dark visual language and responsive layout.
- Label the `.dem` file input, player selector, retry actions, and errors.
- Use semantic controls, visible focus, readable contrast, and reduced-motion
  support.
- Announce meaningful progress changes through one polite live region. Do not
  announce decorative animation or complete stages on a timer.
- Use blocking alerts only for errors that prevent the user from continuing.
- At common desktop and laptop widths, verify loading, player selection, the
  30-second wait, errors, and the final result without clipping or horizontal
  overflow.

## Required error handling

Handle at least:

- invalid file type and `.dem` parser failure;
- network loss, CORS failure, non-JSON responses, and malformed success data;
- unknown `replay_id` or `analysis_id`;
- replay or player list still processing;
- empty player list and invalid player selection;
- coaching/model failure and analysis timeout;
- visualization processing, locked, missing, and failed states; and
- reset, abort, stale response, duplicate submission, and retry behavior.

Show safe, non-technical messages and do not expose stack traces, provider
errors, local paths, raw prompts, or private replay details.

## Validation and handoff

After frontend changes, run the focused tests for the changed behavior and then,
when feasible, run from `frontend/`:

```powershell
pnpm run verify
```

Add or update tests for API validation, state transitions, the upload-to-player
flow, the 30-second coaching wait, error recovery, cancellation, stale-response
rejection, accessibility, and the complete sample or fixture path actually
supported by the backend.

After material work, update `STATUS.md` with current implemented behavior,
important paths, exact validation results, limitations, API impact, and the
next handoff. Replace stale claims rather than appending a diary.

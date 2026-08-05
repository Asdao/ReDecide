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
- Player intent and follow-up questions are not supported by the current public
  API. Do not send intent data to an invented endpoint. The future intent flow
  below may be designed behind a typed interface, but it must remain disabled or
  clearly mocked until the backend contract exists.
- Do not display player-specific coaching before a player is selected.
- The coaching call can take up to 30 seconds. Show truthful progress and allow
  reasonable network overhead before declaring a timeout.
- Validate every successful response before rendering it. Treat network data as
  `unknown`; do not use `any` at the API boundary.
- Do not reveal later round outcomes before the backend unlocks the full
  visualization JSON.

## Future replay and coaching workspace

This section defines the intended replay experience. It extends the current
upload-to-analysis flow but does not claim that all required backend contracts
exist yet.

### Layout and playback

- Use the game radar as the main visual surface in the center of the screen.
- Put a replay timeline across the full width at the bottom of the viewport.
- Provide play, pause, rewind, fast-forward, and direct scrubbing. Controls must
  remain usable by keyboard and must expose their state and current replay time
  to assistive technology.
- Drive playback from replay ticks and the backend-provided map tick rate. Keep
  one authoritative playback clock; do not let the timeline, player positions,
  and analysis panel maintain separate clocks.
- Mark backend-identified learning points on the timeline, including first
  damage, deaths, and other supported key events. Use stable `event_id` or
  `decision_id` values instead of array indexes.
- When playback reaches a learning point, select that marker, pause by default,
  and show the analysis associated with that exact point. The user may resume,
  rewind, fast-forward, scrub to another time, or select another marker.
- Seeking must update the map immediately and deterministically. Reaching the
  same point again must not repeat a model call when a cached analysis already
  exists.
- Keep the full-width timeline anchored at the bottom when the analysis panel
  opens. Avoid horizontal page scrolling or controls that move unpredictably.

### Key-point coaching panel and future intent

- In ordinary playback, the map occupies the central focus area.
- At a learning point, shrink the map slightly and shift it left. Reveal a
  right-side panel containing the backend analysis for that point and an intent
  textbox.
- The panel must identify the selected round, replay time/tick, event type, and
  player so analysis from different points cannot be confused.
- The first analysis shown is the backend's existing analysis for that point.
- In the future flow, the user may enter what they intended to do at that
  moment. Submitting intent sends the selected `replay_id`, `analysis_id`,
  `player_id`, stable key-point ID, and intent text to a future backend endpoint.
- The contextual response replaces the analysis currently displayed for that
  key point only. It must not overwrite analysis for other points or change the
  underlying replay facts.
- Store analysis state by stable key-point ID and request version. Ignore a
  late intent response if the user changed point, changed intent, reset the
  replay, or started a newer request.
- Show a local loading state in the analysis panel while keeping playback
  controls available. Preserve the previous analysis until the contextual
  response validates successfully; on failure, keep it and offer retry.
- Do not infer, simulate, or persist contextual intent analysis until the
  backend owner documents an endpoint, request/response schema, length limit,
  retry behavior, and privacy/retention rules. Never send intent text through
  query parameters, logs, analytics, or persistent browser storage.

### Radar map and player rendering

- Radar images and overview metadata are available from
  [MurkyYT/cs2-map-icons](https://github.com/MurkyYT/cs2-map-icons). Its radar
  information includes map origin, scale, rotation, zoom, and vertical-section
  metadata. Multi-level maps may have separate lower-radar images.
- Use a reviewed, pinned map asset and its matching overview metadata. Do not
  guess the world-to-radar transform or stretch a radar image until positions
  appear plausible.
- The repository redistributes assets extracted from the CS2 depot and states
  that map icons, radars, thumbnails, and overview data are Valve property.
  Confirm acceptable hackathon usage and attribution before bundling assets.
  Prefer a reviewed local subset over runtime hotlinking or bulk-copying every
  map.
- Render player snapshots from the unlocked visualization JSON. The backend
  currently documents `X`, `Y`, `Z`, health, side, and alive state when
  available. Handle missing samples explicitly and interpolate only between
  valid snapshots for the same player and round.
- Render each player as a clear dot relative to the selected player at the
  current tick:
  - selected player: blue;
  - selected player's allies: green; and
  - enemies: red.
- Do not use color alone. Give the selected player a distinct ring or glyph,
  distinguish teams by shape or outline, and provide an accessible legend.
- Use the side/team values at the current round rather than assuming a player's
  team remains constant for the whole match. Hide, fade, or mark dead players
  according to the backend `alive` state.
- Use `Z` and the radar's vertical-section metadata to choose the appropriate
  floor on multi-level maps. When the correct floor is uncertain, indicate that
  uncertainty rather than silently placing the player on an arbitrary layer.
- The selected blue player's current `Z` determines the active floor at every
  playback position. When the selected player moves between floors, update the
  active radar layer without resetting playback, the selected learning point,
  or the open coaching panel.
- In the flat 2D view, render the active floor at full opacity in the foreground.
  Keep the other available floor images aligned underneath it at lower opacity
  so the user retains multi-level context without confusing an inactive floor
  for the selected player's current floor.
- Render players on the active floor at full opacity. Render players on other
  floors at reduced opacity while preserving their team color and identity
  shape. The selected blue player must always remain fully visible on the active
  floor.
- Apply the same floor classification to player dots, field-of-view wedges,
  event markers, and any paths or trails. Do not show an off-floor player at
  full opacity merely because their `X` and `Y` overlap the active floor.
- Avoid rapid layer flicker when a `Z` value sits close to a vertical-section
  boundary. Use the backend's explicit vertical sections where available and a
  deterministic boundary rule. If the selected player's `Z` is temporarily
  missing, retain the last valid floor within the same round and visibly fall
  back to an uncertain single-layer state when no valid floor is known.
- Add a field-of-view wedge only when the backend returns a documented,
  normalized view direction such as yaw, including its units, zero direction,
  rotation convention, and coordinate space. The current public visualization
  contract does not guarantee this data. Never substitute movement direction
  as player aim.

### Flat 2D and planned 2.5D stacked-layer presentation

The required implementation is a flat 2D radar. It is practical with the
current position snapshots and the overview metadata, and it provides the best
base for reliable playback, seeking, key-point synchronization, and responsive
layout.

Add a decorative 2.5D "stacked pancakes" mode after the flat viewer is stable
for maps with separate radar layers:

- Render every radar floor as an aligned textured plane with vertical spacing
  derived from floor order, not as true game geometry.
- Keep the selected blue player's active plane at full opacity and stronger
  visual emphasis. Keep other planes visible below or above it at reduced
  opacity.
- Anchor every player marker to its classified floor plane. Players on the
  active plane remain fully opaque; players on other planes use the same reduced
  opacity rule as the flat view.
- When the selected player changes floor, transition emphasis to the new plane
  while retaining camera position, playback time, and analysis state.
- Allow a restrained tilt and slow spin only when it does not interfere with
  playback or reading analysis. Pause decorative rotation during scrubbing,
  active playback when motion becomes distracting, and while the coaching panel
  is being read.
- Provide a visible toggle between flat and stacked modes. Flat 2D remains the
  canonical tactical view and fallback for unsupported maps, small screens,
  reduced-motion users, poor performance, and uncertain layer metadata.
- Keep timeline markers and playback controls in screen space; they must not
  tilt or rotate with the map planes.

Do not attempt true 3D map geometry from the radar PNGs. They are flat images,
not meshes, so true geometry would require another licensed geometry source,
world-height mapping, a WebGL/Three.js renderer, camera and interaction work,
performance tuning, and substantially more QA. The decorative stacked-layer
version is medium effort after the 2D viewer is stable; true 3D is high effort
and out of scope for the first implementation.

Recommended order:

1. Flat 2D radar with correct coordinate transforms and player dots.
2. Timeline playback, seeking, controls, and key-point markers.
3. Responsive map-to-left and analysis-panel transition.
4. Contextual intent flow after the backend contract is available.
5. Conditional field-of-view wedges after view direction is available.
6. The planned 2.5D stacked radar mode only after the complete 2D flow passes
   functional, responsive, accessibility, and performance checks.

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
| `GET /api/samples` | Returns the sample matches available for selection. Treat the response as an opaque backend result. |
| `POST /api/analyze` | Starts the supported sample analysis flow using the selected `sample_id` and optional player name. |

Sample-picker behavior:

- When the user chooses `Use a sample match`, call `GET /api/samples` and render
  the returned `samples` array as a selectable list.
- The backend currently returns one match, so show a normal list containing one
  match. Do not auto-select it or replace the list with a special hard-coded
  sample button.
- Treat the backend as a black box. The frontend must not depend on, reveal, or
  describe whether samples come from fixtures, files, a database, or any other
  backend implementation detail.
- Use only the returned sample fields and stable `sample_id`. Do not branch on a
  known fixture ID or assume the list will always contain exactly one item.
- Handle zero, one, and many samples with the same list component. Show an empty
  state when none are returned and disable or label entries whose returned
  availability field says they cannot be selected.
- Submit the chosen `sample_id` through `POST /api/analyze` and validate its
  response before continuing the sample flow.

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
rejection, accessibility, zero/one/many sample-list responses, unavailable
sample entries, and the complete sample path supported by the backend. For
replay-workspace changes, also test tick-to-time
conversion, world-to-radar transforms, round/team changes, missing player
snapshots, selected-player floor changes, active/inactive layer and player
opacity, boundary flicker prevention, flat/2.5D parity, reduced-motion fallback,
timeline seeking, marker activation, pause/rewind/fast-forward behavior, panel
layout, cached point analysis, and stale contextual-intent responses. Verify
acceptable performance with a realistically large tick stream rather than a
tiny fixture alone.

After material work, update `STATUS.md` with current implemented behavior,
important paths, exact validation results, limitations, API impact, and the
next handoff. Replace stale claims rather than appending a diary.

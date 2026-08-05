# Frontend Status

Last verified: 2026-08-05 (Asia/Singapore)

## Status

**Backend sample selection, uploaded `.dem` coaching, processed-showcase player selection, and the first 2D replay workspace are implemented.**

The landing page's `Use a sample match` action calls `GET /api/samples` and
renders the backend-returned list through the compatibility sample selector.
Selecting an available entry submits its stable `sample_id` to
`POST /api/analyze`. A separate `Open processed showcase` action loads the
bundled, already-processed `mirage-showcase.replay.json`; the user chooses one
of its 10 stable player IDs and continues to `/analysis` without upload, demo
parsing, analysis preparation, or coaching calls. The native `.dem` action
continues to use the complete backend flow.

The `.dem` upload is the primary orange landing action; backend samples and the
processed showcase use the steel-blue secondary treatment. Their concise help
text shares one line below the action row and is revealed only for the hovered
or keyboard-focused action, with tan help text for upload and steel-blue help
text for the secondary actions. The secondary hover fill now uses a single
diagonal wipe without the earlier arrow-like edge. The product logo is a normal
link to `/`, so activating it performs a fresh page navigation and clears all
in-memory sample, upload, or showcase state.

Backend samples and the processed showcase now use query-backed browser history
entries (`?view=samples` and `?view=showcase`). Browser Back returns to the
landing screen, Forward restores and reloads the selected view, the visible
back controls consume owned child entries safely, and direct view links receive
a local landing entry so their first Back remains inside the app. Unrelated
query parameters are preserved. Returning from `/analysis` also restores the
showcase player selector rather than losing its source context.
Selecting a local `.dem` also pushes an owned, same-URL upload history entry,
so browser Back returns to the landing state and truncates any stale Forward
entry that could otherwise reopen the processed showcase. The upload itself is
not restored on Forward because browsers do not allow local `File` objects to
be reconstructed safely.

Every loading surface now uses the same rotating orange perimeter around its
content box, including sample retrieval, processed-showcase loading, browser
replay preparation, and all uploaded-replay progress states. The former
floating square markers and pulse animations were removed. The moving border is
a solid, hard-edged orange segment without a translucent gradient ramp, and the
global reduced-motion treatment still collapses it to a static border state.

The new analysis route renders the reviewed local Mirage radar with the
selected player in blue, same-side players in green, and opponents in red.
Team shapes, a selected-player ring, eliminated-player treatment, an accessible
horizontal legend layered above the radar at the bottom center, and tooltips
keep the view understandable without relying on color alone. The radar has no
card border or opaque backing, so its transparent map asset floats in the
workspace. Positions are derived from the processed snapshots with the reviewed
Mirage overview origin and scale. Position samples for the same player and
round are linearly interpolated against the authoritative playback tick, so
movement remains continuous between the replay's half-second snapshots.

A single playback clock synchronizes the radar, round selector, full-match
timeline, scrubber, elapsed time, and event inspector. The viewer supports
play/pause, five-second rewind/fast-forward, 0.5x through 8x playback, direct
scrubbing, round jumps, and stable kill/objective event markers. Selecting a
marker seeks to its exact tick and exposes the known event facts without
starting another model call. Timeline markers are perspective-specific: they
show only damage received and deaths where the selected player is the victim,
and refresh immediately when the perspective changes. Playback detects the
first selected-player event crossed by the authoritative clock, seeks to its
exact tick, opens the event inspector, and pauses automatically. Event and round
tracks use the range thumb's usable inset so markers align with the playback
thumb. The layout keeps the timeline full-width at the bottom on desktop and
sticky on narrow screens.
All event markers use one consistent hit target and a six-pixel visual line,
with no persistent focus or selected outline after clicking or automatic
pausing. The wider right-side inspector uses an orange border on all four sides;
its knowledge-boundary note uses background color without an edge border.
The inspector's clear action keeps the homepage button's 22-degree diagonal
edge, using a clipped sweep that extends beyond every corner and guarantees full
coverage at the end of the transition. Player
and round selectors suppress the browser's native white focus ring while
retaining the product-colored container state.
Full-match round segments are labeled buttons: hovering or keyboard focus shows
a round tooltip, and activation jumps to that round's start tick.
The analysis shell, toolbar, and workspace are transparent over the shared page
background, so the homepage's diagonal stripe treatment continues with its
original opacity, colors, and 22-degree angle.
The moment inspector is absent during ordinary playback. Selecting an event
slides a wider inspector in from the right and shifts the centered radar
slightly left; clearing the event or resuming playback restores the centered
map.

The backend-driven compatibility sample selector, schemas, adapter, reducer
states, and tests power the sample-match landing action. The processed
visualization showcase remains a distinct, explicitly labelled option.

`AnalysisProgressScreen.tsx` and the old saved-fixture loading path are no
longer part of the rendered flow. The landing page now exposes a labelled,
keyboard-focusable `.dem` picker alongside the existing sample-match action.

The frontend now also has a typed, UI-independent adapter for the complete
uploaded-replay API sequence. It uploads one `.dem` through
`POST /api/replay/upload`, prepares analysis by stable `replay_id`, reads job
and player status, submits the selected stable `player_id` for coaching,
recovers completed results without rerunning coaching, and distinguishes
visualization processing, locked, failed, and ready responses. Every successful
JSON response is validated before the adapter returns it. Abort errors remain
distinguishable from normalized network, HTTP, content-type, JSON, and schema
errors, and backend error details are not exposed through adapter messages.

The main reducer now models the complete supported upload lifecycle without UI
coupling: uploading, preparing analysis, waiting for players, choosing a stable
player ID, running coaching, recovering an ambiguously completed request, and
displaying a validated result. Each asynchronous state owns an explicit request
ID, so reset, retry, mismatched IDs, and late responses cannot advance the wrong
flow. Retry paths preserve only the context they need. An uncertain coaching
request can only check `GET /result`; it cannot accidentally start a duplicate
model call. Structurally valid results are also checked against the active
`replay_id` and selected `player_id` before entering the result state.

Replay contracts now enforce cross-field invariants in addition to field
shapes, including unique stable player IDs, valid round boundaries, selected
decision ownership, and agreement between the selected decision and coaching
analysis. Manifest validation also keeps visualization failures, coaching
completion, and visualization unlock state internally consistent.

The replay state machine is now connected to the adapter and rendered screens.
Choosing a `.dem` uploads it once, prepares analysis by `replay_id`, polls the
documented player endpoint until ready, displays player names while submitting
stable `player_id` values, allows only players with a coaching decision, and
runs the coach with a 45-second client allowance for the documented 30-second
request. A lost or timed-out coaching response checks `GET /result` after a
grace period. A merely `ready` analysis never authorizes another model call;
only an explicit backend `failed` state can enable a coaching retry. Other
ambiguous states can only re-check the result. Reset aborts browser requests
and stale request IDs prevent late completions from replacing the active flow.

Responsive replay screens cover upload, preparation, player discovery,
selection, coaching, ambiguous-result recovery, scoped errors/retries, and the
validated coaching result. Progress uses one polite live region, blocking
errors use alerts, headings receive focus on state changes, and later replay
outcomes are not rendered in the coaching result.

## Important paths

- `src/components/DecisionFlow.tsx` - backend sample-list entry, showcase loading
  and routing, plus uploaded replay polling, timeouts, cancellation, and request
  ownership
- `src/components/ShowcasePlayerScreen.tsx` - processed-showcase loading,
  errors, replay summary, and stable player selection
- `src/components/ReplayAnalysisScreen.tsx` - Mirage radar, playback clock,
  controls, event inspector, player perspective, and full-match timeline
- `src/app/analysis/page.tsx` - player-aware analysis route and metadata
- `src/adapters/showcase-replay.ts` - local showcase retrieval and safe boundary
  failure handling
- `src/domain/replay-viewer.ts` - strict showcase contract, frame indexing,
  deterministic seeking, clock formatting, and reviewed Mirage transform
- `public/replays/mirage-showcase.replay.json` - browser-served copy of the
  canonical processed showcase
- `src/components/ReplayFlowScreen.tsx` - upload/preparation progress, player
  selection, coaching/recovery, safe errors, and final coaching result
- `src/components/SampleSelectorScreen.tsx` - loading, error, empty, list, map
  thumbnail, unavailable, selecting, selected, and retry UI
- `src/components/LandingScreen.tsx` - source selection entry point
- `src/adapters/samples-api.ts` - `GET /api/samples` and `POST /api/analyze`
  transport with JSON/content/status checks
- `src/adapters/replay-api.ts` - typed transport for upload, preparation,
  status, player selection, coaching, recovery, and visualization retrieval
- `src/domain/replay.ts` - strict replay manifest, analysis, result, and
  visualization boundary schemas
- `src/domain/maps.ts` - shared official and fallback display names for CS2 map
  identifiers
- `src/domain/samples.ts` - strict API schemas, types, and safe map-asset naming
- `src/domain/analysis-flow.ts` - explicit sample and uploaded-replay state
  machine, request ownership, scoped retries, and coaching recovery
- `src/domain/landing-navigation.ts` - query-backed landing views, history URLs,
  and owned-entry markers for Back and Forward navigation
- `public/maps/de_mirage.png` - pinned current-sample thumbnail
- `src/app/globals.css` - sample and replay screens, responsive layout, focus,
  progress, error, selector, and result styling
- `tests/unit/analysis-flow.test.ts` - zero/one/many, unavailable, selection,
  error/retry/reset, and map-name coverage
- `tests/unit/replay-api.test.ts` - multipart upload, endpoint payloads,
  processing states, coaching recovery, visualization gating, validation,
  safe failures, and cancellation
- `tests/unit/replay-contracts.test.ts` - replay schema strictness and
  cross-field ownership invariants
- `tests/unit/replay-flow.test.ts` - complete state transitions, stable IDs,
  stale-response rejection, scoped retries, invalid selection, reset, and
  result recovery
- `tests/unit/replay-ui.test.ts` - enabled upload input, player availability,
  truthful coaching wait, live-region semantics, and outcome-safe result UI

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. Local development
defaults to `http://127.0.0.1:8000` when the variable is absent. The backend
must allow the frontend origin through `REDECIDE_API_ALLOWED_ORIGINS`.

The Next.js image allowlist permits only the referenced repository's thumbnail
folder on `raw.githubusercontent.com` for non-bundled future maps.

## Verification

From `frontend/`, `pnpm run verify` passes:

- Vitest: 7 files, 76 tests passed
- TypeScript: passed
- ESLint: passed with no warnings
- Next.js production build: passed; `/` and `/_not-found` prerendered

Browser verification against the documented sample responses confirmed:

- landing action opens the selector;
- browser Back returns from samples or showcase to the landing screen;
- browser Forward restores the selected samples or showcase view;
- direct `?view=` links and Back from `/analysis` retain their expected source
  context without console warnings or errors;
- the returned Mirage sample renders as a horizontal selectable bar;
- the local Mirage thumbnail is requested through Next.js image handling;
- selection reaches the selected state after `POST /api/analyze`;
- the preparation result reports one available player;
- no console warnings or errors; and
- no horizontal overflow at a 390-by-844 narrow-screen override.

Browser verification of the uploaded-replay UI also confirmed:

- the `.dem` picker is enabled, labelled, and restricted with `accept=".dem"`;
- desktop player selection distinguishes selectable and unavailable players;
- the coaching screen truthfully communicates the approximately 30-second wait;
- the coaching error screen exposes an enabled, scoped retry;
- the completed result shows the validated player, round, decision, and advice;
- desktop and 390-by-844 layouts have no horizontal overflow; and
- the final landing page reports no hydration errors.

## Known limitations and next handoff

- Only the thumbnail for the backend's current Mirage fixture is pinned
  locally. Add reviewed local assets to `public/maps/` and the bundled allowlist
  as new backend samples are introduced; otherwise the remote/fallback path is
  used.
- The compatibility sample flow currently stops after the backend preparation
  response reports the available players; its next player-selection screen is
  not yet implemented.
- A real native `.dem` has not yet completed the full backend flow, matching the
  backend's documented current limitation. Browser QA used validated replay
  fixtures for post-upload states and did not send user replay data.
- Visualization JSON retrieval for uploaded replays is implemented in the
  adapter but is not yet connected from a completed live coaching result into
  the radar/timeline workspace. The current workspace intentionally uses the
  bundled Mirage showcase. Player intent remains disabled because no public
  backend contract exists.

## Contract/API impact

No backend contract changes. In addition to the compatibility sample APIs, the
frontend adapter now implements the documented `/api/replay/*` and
`/api/analysis/*` contracts and the rendered UI consumes the supported upload,
preparation, player-selection, coaching, and result endpoints.

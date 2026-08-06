# Frontend Status

Last verified: 2026-08-06 (Asia/Singapore)

## Status

**Backend sample selection, complete uploaded `.dem` coaching-to-replay playback, a two-save processed replay catalog, and a map-aware 2D replay workspace are implemented.**

The landing page's `Use a sample match` action calls `GET /api/samples` and
renders the backend-returned list through the compatibility sample selector.
Selecting an available entry submits its stable `sample_id` to
`POST /api/analyze`. A separate `Open processed replays` action opens a local
list containing the bundled Mirage showcase and backend-generated Inferno
visualization. Selecting a save loads its player roster; selecting a stable
player ID then opens `/analysis` with that perspective already active. Player
perspective remains switchable inside the viewer. The Inferno save includes
saved coaching for flameZ, while Mirage has no analysis artifact; the replay and
player lists label those states explicitly. The processed-replay radar credit
links directly to the redistributed radar-image directory. The native `.dem` action continues
to use the complete backend flow.

The `.dem` upload is the primary orange landing action; backend samples and the
processed replay catalog use the steel-blue secondary treatment. Their concise help
text shares one line below the action row and is revealed only for the hovered
or keyboard-focused action, with tan help text for upload and steel-blue help
text for the secondary actions. The secondary hover fill now uses a single
diagonal wipe without the earlier arrow-like edge. The product logo is a normal
link to `/`, so activating it performs a fresh page navigation and clears all
in-memory sample, upload, or processed-replay state. The document title is
always `RE:DECIDE`; nested screens do not replace the browser-tab title with
route-specific text.

Backend samples and the processed replay catalog use query-backed browser history
entries (`?view=samples` and `?view=showcase`). Browser Back returns to the
landing screen, Forward restores and reloads the selected view, the visible
back controls consume owned child entries safely, and direct view links receive
a local landing entry so their first Back remains inside the app. Unrelated
query parameters are preserved. Browser Back from `/analysis` also restores the
processed replay list rather than losing its source context.
Selecting a local `.dem` also pushes an owned, same-URL upload history entry,
so browser Back returns to the landing state and truncates any stale Forward
entry that could otherwise reopen the processed replay catalog. The upload itself is
not restored on Forward because browsers do not allow local `File` objects to
be reconstructed safely.

Every loading surface now uses the same rotating orange perimeter around its
content box, including sample retrieval, browser replay loading and preparation,
and all uploaded-replay progress states. The former
floating square markers and pulse animations were removed. The moving border is
a solid, hard-edged orange segment without a translucent gradient ramp, and the
global reduced-motion treatment still collapses it to a static border state.

The analysis route renders the reviewed local radar for the selected replay with the
selected player in blue, same-side players in green, and opponents in red.
Team shapes, a selected-player ring, eliminated-player treatment, an accessible
horizontal legend layered above the radar at the bottom center, and tooltips
keep the view understandable without relying on color alone. The radar has no
card border or opaque backing, so its transparent map asset floats in the
workspace. Positions are derived from normalized backend snapshots with the
reviewed map-specific overview origin and scale. Position samples for the same player and
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
pausing. The marker track now uses a roving keyboard tab stop, so it contributes
one stop instead of every replay event to the page tab order; Left/Right and
Home/End move between markers and keyboard focus remains visibly outlined. The
wider right-side inspector matches its border to the selected marker: tan for
damage, red for death, and blue for an analysis-backed moment. A 100-damage
event is classified as death, and a same-tick duplicate kill marker is folded
into that stable damage event. The analysis legend swatch has the same visual
thickness as the damage and death swatches.
Saved coaching uses a borderless blue background. The inspector has no separate
saved-analysis note or clear button. Player
and round selectors suppress the browser's native white focus ring while
retaining the product-colored container state.
Full-match round segments are labeled buttons: hovering or keyboard focus shows
a round tooltip, and activation jumps to that round's start tick.
Between recorded rounds, the live-position heading reads `Waiting for next
round`. The bottom timeline caption contains only the event legend and current
tick; it no longer repeats the active round number.
The analysis shell, toolbar, and workspace are transparent over the shared page
background, so the homepage's diagonal stripe treatment continues with its
original opacity, colors, and 22-degree angle.
The moment inspector is absent during ordinary playback. Selecting an event
slides a wider inspector in from the right and shifts the centered radar
slightly left; resuming playback restores the centered
map. Inferno's saved coaching is attached to the matching flameZ damage event at
tick 2579, shown as a distinct blue timeline marker, and rendered in the moment
inspector. Analysis-backed moments now also render the intent follow-up composer
pinned to the bottom of the inspector. The textbox keeps its base height and
scrolls internally instead of resizing. Its typed, per-moment request lifecycle
keeps a one-time submitted intent attached to the stable event ID, disables editing,
preserves the old coaching behind the rotating loading border, ignores stale
responses, and replaces only that moment's coaching after a successful response.
The composer remains visibly disabled in the running app until the backend
provides a documented endpoint and a submission function is connected; the
viewer does not invent or call an unsupported API.
The radar workspace always renders a compact win-rate strip directly under the
live radar status and above the moment inspector. The strip is capped at half
the inspector's maximum width. The selected player's current team is flushed
left in the legend's green, `Win rate` is centered, and the opposing team is
flushed right in the legend's red with its team name after the percentage. The
split bar uses the same perspective-aware colors, matches the round indicator's
thickness, and sits close beneath the values. Playback carries forward the
latest backend estimate at or before the current tick in the same round. Before
a fresh round receives its first estimate,
or when analysis data is unavailable, the strip shows a muted 50/50 baseline
instead of borrowing from another round or a future tick.

The processed replay adapter accepts the documented backend
`replay_visualization_v1` output without requiring the sanitized Mirage shape.
It associates backend snapshots with stable top-level players by their unique
display names, normalizes sides and event participants, derives `alive` from
health only when absent, removes duplicate parser event aliases from the viewer,
and generates deterministic event IDs when the backend did not return one.

The backend-driven compatibility sample selector, schemas, adapter, reducer
states, and tests power the sample-match landing action. The processed replay
catalog remains a distinct, explicitly labelled option.

`AnalysisProgressScreen.tsx` and the old saved-fixture loading path are no
longer part of the rendered flow. The landing page now exposes a labelled,
keyboard-focusable `.dem` picker alongside the existing sample-match action.

The frontend now also has a typed, UI-independent adapter for the complete
uploaded-replay API sequence. Its configurable upload transport defaults to a
direct multipart `POST /api/replay/upload` for local development. Vercel can
instead upload the `.dem` directly from the browser to a public Blob store,
then submit only its URL and original filename to `POST /api/replay/import-url`.
Blob uploads use multipart transfer above 100 MB and reject files above the
backend-aligned 1 GB limit before transfer. The adapter prepares analysis by
stable `replay_id`, reads job and player status, submits the selected stable
`player_id` for coaching, recovers completed results without rerunning coaching,
and distinguishes visualization processing, locked, failed, and ready
responses. Every successful JSON response is validated before the adapter
returns it. Abort errors remain distinguishable from normalized network, HTTP,
content-type, JSON, and schema errors, and provider details are not exposed
through adapter messages.

The uploaded-replay boundary now matches the backend's repeatable per-player
run contract. Analysis metadata accepts the `coaching` state, nullable
`selected_player_id`, and keyed `player_runs`; selectable players require the
backend-provided `analysis_available` and `analysis_status` fields. Completed
analysis results retain their separate unadorned player shape, so selector-only
run state is not incorrectly required in saved or live result artifacts.

The main reducer now models the complete supported upload lifecycle without UI
coupling: uploading, preparing analysis, waiting for players, choosing a stable
player ID, running coaching, recovering an ambiguously completed request, and
displaying a validated result. Each asynchronous state owns an explicit request
ID, so reset, retry, mismatched IDs, and late responses cannot advance the wrong
flow. Retry paths preserve only the context they need. An uncertain coaching
request can only check `GET /result`; it cannot accidentally start a duplicate
model call. Structurally valid results are also checked against the active
`replay_id` and selected `player_id` before entering the result state.

Frontend request helpers now share one public API base URL and one abort-error
guard across the replay, sample, processed-save, and orchestration paths. The
unused saved-fixture adapter, unused fixture composition module, and legacy
coaching-result CSS were removed; all remaining CSS class selectors are backed
by current source usage.

Replay contracts now enforce cross-field invariants in addition to field
shapes, including unique stable player IDs, valid round boundaries, selected
decision ownership, and agreement between the selected decision and coaching
analysis. Manifest validation also keeps visualization failures, coaching
completion, and visualization unlock state internally consistent.
Compatibility sample contracts now mirror the backend's unique-player and
recommended-player rules and enforce the payload associated with each
preparation stage. Both bundled processed replay JSON files and the Inferno
saved-analysis JSON remain validated directly from disk in the test suite.

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

As soon as upload returns `replay_id`, the browser starts
`POST /api/analysis/prepare` and an initial
`GET /api/replay/{replay_id}/json` request together. The initial replay request
may truthfully report processing or locked; analysis preparation continues
independently. Selecting a player pushes an owned browser-history entry and
opens a map-shaped loading workspace using the reviewed radar asset at the same
size and position as the finished 2D viewer. Once coaching succeeds, the
browser polls the replay JSON until it is unlocked, validates and normalizes it,
then replaces the loading overlay with positions, events, controls, and the
timeline without changing the workspace geometry.

Uploaded replay viewers keep the coached player fixed: they have no inline
perspective selector and player markers cannot switch perspective. The visible
`Choose another player` action and browser Back both return to the authoritative
analysis player selector without re-uploading or re-preparing the replay.
Selecting another player reuses the same `analysis_id` and calls
`POST /api/analysis/{analysis_id}/run` again with the new stable `player_id`.
Browser Forward can restore an already completed viewer from in-memory state
without repeating the model call; an incomplete or cancelled request is never
restarted by history navigation.

Responsive replay screens cover upload, preparation, player discovery,
selection, coaching, ambiguous-result recovery, scoped errors/retries, and the
validated coaching result. Progress uses one polite live region, blocking
errors use alerts, headings receive focus on state changes, and later replay
outcomes are not rendered in the coaching result.

## Important paths

- `src/components/DecisionFlow.tsx` - backend sample-list entry, processed replay
  catalog routing, plus uploaded replay polling, timeouts, cancellation, and request
  ownership
- `src/components/ProcessedReplaySelectorScreen.tsx` - two-save processed replay
  list, map summaries, analysis-availability labels, and replay selection
- `src/components/ProcessedReplayPlayerScreen.tsx` - selected-save loading,
  replay summary, analysis status, and stable player-perspective selection
- `src/components/ReplayAnalysisScreen.tsx` - map-aware radar, playback clock,
  controls, event inspector, processed-save perspective switching, fixed
  uploaded-replay perspective, and full-match timeline
- `src/components/ReplayMapLoadingScreen.tsx` - uploaded-replay coaching and
  visualization loading state using the final radar workspace geometry
- `src/app/analysis/page.tsx` - replay- and player-aware viewer route and metadata
- `src/adapters/processed-replay.ts` - catalog-based replay retrieval and safe boundary
  failure handling
- `src/domain/processed-replays.ts` - bundled save catalog and analysis availability
- `src/domain/replay-viewer.ts` - backend-output normalization, frame indexing,
  deterministic seeking, clock formatting, and reviewed map transforms
- `public/replays/*.replay.json` - browser-served Mirage and Inferno processed saves
- `public/replays/inferno-processed.analysis.json` - validated saved coaching
  result paired with the Inferno replay by replay, map, source, player, and tick
- `src/components/ReplayFlowScreen.tsx` - upload/preparation progress, player
  selection, coaching/recovery, safe errors, and final coaching result
- `src/components/SampleSelectorScreen.tsx` - loading, error, empty, list, map
  thumbnail, unavailable, selecting, selected, and retry UI
- `src/components/LandingScreen.tsx` - source selection entry point
- `src/adapters/samples-api.ts` - `GET /api/samples` and `POST /api/analyze`
  transport with JSON/content/status checks
- `src/adapters/replay-api.ts` - typed transport for upload, preparation,
  direct or Blob URL import, status, player selection, coaching, recovery, and
  visualization retrieval
- `src/app/api/blob/upload/route.ts` - same-origin Vercel Blob client-token
  route restricted to `.dem`, public object storage, and a 1 GB maximum
- `src/lib/http.ts` - shared public API base URL and browser abort detection
- `.env.example` - local direct-upload defaults and the Vercel Blob mode switch
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
- `tests/unit/replay-viewer.test.ts` - both full replay fixtures, backend snapshot
  normalization, transforms, interpolation, and event selection
- `tests/unit/replay-ui.test.ts` - enabled upload input, processed replay catalog,
  analysis labels, truthful coaching wait, and outcome-safe result UI

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. Local development
defaults to `http://127.0.0.1:8000` when the variable is absent. The backend
must allow the frontend origin through `REDECIDE_API_ALLOWED_ORIGINS`.

`NEXT_PUBLIC_REPLAY_UPLOAD_MODE` defaults to `direct`, which sends the file to
the local or configured FastAPI base URL. Set it to `blob` in Vercel and connect
a public Blob store so Vercel supplies the server-only `BLOB_READ_WRITE_TOKEN`.
Never expose that token through a `NEXT_PUBLIC_*` variable.

The Next.js image allowlist permits only the referenced repository's thumbnail
folder on `raw.githubusercontent.com` for non-bundled future maps.

## Verification

From `frontend/`, `pnpm run verify` passes:

- Vitest: 9 files and 104 tests passed, including backend-shaped per-player run
  metadata, sample invariants, both bundled processed saves, and 20 upload adapter and Blob
  token-route tests covering direct and public-Blob transports, multipart
  selection, limits, cancellation, safe failures, same-origin checks, and token
  constraints. The intent tests cover per-moment isolation, loading-to-success,
  same-text retry state, stale response rejection, same-round win-estimate
  selection, CT/T perspective swaps, and lethal-damage deduplication. Landing-
  page assertions match the current upload and processed-replay wording.
- TypeScript: passed
- ESLint: passed with no warnings
- Next.js production build: passed in both default direct mode and explicit
  Blob mode; `/` and `/_not-found` prerendered, with `/analysis` and
  `/api/blob/upload` rendered on demand

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

Live processed-replay verification additionally confirmed that a 125-marker
timeline exposes exactly one tab stop, Right Arrow moves focus and selection to
the next event, no browser warnings or errors are emitted, and the 390-by-844
viewer and event inspector remain free of horizontal overflow.

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
- A real public Vercel Blob has not yet completed the hosted end-to-end flow.
  Blob objects are public to anyone with their URL and are not automatically
  deleted after FastAPI imports them. The token route checks same-origin browser
  requests and upload constraints, but a public production deployment still
  needs authentication or platform-level protection to prevent upload abuse.
- Only Inferno currently has a paired saved coaching result for the processed
  save catalog. Uploaded replays use their live completed analysis. The player
  intent UI and typed request lifecycle are implemented, but submission remains
  disabled because no public backend endpoint or response contract exists.

## Contract/API impact

No backend contract changes and no intent endpoint was invented. The local
processed-replay adapter and uploaded
flow consume the documented `replay_visualization_v1` shape directly. In
addition to the compatibility sample APIs, the frontend adapter implements the
documented `/api/replay/*` and `/api/analysis/*` contracts, including the
disabled-by-default public Blob URL import. The rendered upload flow now
consumes preparation, player selection, repeat coaching, result recovery,
visualization unlock, and replay playback endpoints end to end.

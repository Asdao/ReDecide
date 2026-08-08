# Frontend Status

Last verified: 2026-08-08 (Asia/Singapore)

## Vercel Services deployment

The frontend now targets same-origin `/api` routes, while
`NEXT_PUBLIC_API_BASE_URL` remains available for standalone local development.
The root `vercel.json` uses the current `services` schema and ordered rewrites:
`/api/blob/upload`, `/api/blob/cleanup`, and `/api/cron/blob-retention` stay in
Next.js, while other `/api/*`
requests reach FastAPI, public `/service-internal/*` requests are routed away from the
frontend signer, and the frontend handles the catch-all route. The backend has
a deployment-aware private binding to the frontend. It uses that binding to
obtain exact-operation, exact-path, five-minute Blob URLs for durable analysis
and replay JSON; artifact bodies transfer directly between FastAPI and Blob.
Local development remains filesystem-backed unless explicitly opted into Blob.
The backend service now applies a 300-second maximum duration to Python
functions so replay parsing and coaching are not constrained by shorter legacy
defaults; the effective ceiling remains plan-dependent.

Public Blob artifact reads now receive a unique cache-busting query parameter
from the internal signer. This prevents an overwritten analysis `state.json`
from returning its previous `failed` or `processing` value during the immediate
player-selection poll. Private stores continue to use `useCache: false` instead.
The Python service-binding client also retries authorization and direct Blob
transfers up to three times for transport failures, rate limits, and transient
5xx responses, covering the intermittent Blob `503` observed during analysis
state persistence. Neither behavior is used by the default local filesystem
store.

Hosted sample replay IDs are now derived from an explicit cache schema, source
identity, digest/size constraints, and a configurable pipeline cache version.
The backend reuses a sample artifact only when its internal metadata exactly
matches that identity; stale artifacts are reparsed instead of entering player
selection. The 20 MB hosted sample also verifies a pinned SHA-256 digest.
Preparation failures keep a safe generic API error while Vercel runtime logs
receive the exception traceback and analysis/replay IDs.

Durable JSON has a separate server-only retention path. The daily Vercel Cron
deletes failed analysis groups after 1 day, other analysis groups after 14 days,
and non-sample replay groups after 30 days by default. It recognizes only the
known JSON artifact shapes, caps each run, retains pinned sample caches, and
keeps data when metadata inspection fails. `CRON_SECRET` authentication and an
optional dry-run mode prevent browser-driven or accidental broad deletion.

The latest validation state for the merged frontend is recorded under
Verification. Vitest, TypeScript, ESLint, and the production Turbopack build
all pass.

## Status

**Backend sample selection, complete uploaded `.dem` coaching-to-replay playback, a two-save processed replay catalog, and a map-aware 2D replay workspace are implemented.**

The landing page's `Use a sample match` action calls `GET /api/samples` and
renders the backend-returned catalog. Selecting an available entry submits its
stable `sample_id` to `POST /api/analyze`; the returned replay manifest and
analysis metadata then enter the same player-selection, coaching, result
recovery, and visualization lifecycle as an uploaded replay. A separate
`Open processed replays` action remains a local saved-replay catalog and does
not share sample-selection state. The native `.dem` action continues to use
the complete backend flow.

The `.dem` upload is the primary orange landing action; backend samples and the
processed replay catalog use the steel-blue secondary treatment. Their concise help
text shares one line below the action row and is revealed only for the hovered
or keyboard-focused action, with tan help text for upload and steel-blue help
text for the secondary actions. The secondary hover fill now uses a single
diagonal wipe without the earlier arrow-like edge. The product logo is a normal
link to `/`, so activating it performs a fresh page navigation and clears all
in-memory sample, upload, or processed-replay state. The browser-tab title uses
the current one-word location followed by ` - RE:DECIDE`: Home, Samples,
Replays, Replay, or Analysis.

Unknown routes render a dedicated `404 - RE:DECIDE` page. It preserves the
shared diagonal background and product top bar, centers an oversized orange
404 with explanatory text, and provides a primary action back to the homepage.

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
content box, including sample retrieval, the selected sample card during preparation,
browser replay loading and preparation,
and all uploaded-replay progress states. The former
floating square markers and pulse animations were removed. The moving border is
a solid, hard-edged orange segment without a translucent gradient ramp, and the
global reduced-motion treatment still collapses it to a static border state.
Uploaded analysis preparation and coaching now subscribe to the backend-provided
`events_url`. Validated SSE messages replace static loading copy with the latest
backend stage; the coaching map wait screen omits the backend's fixed numeric
milestone because it is not measured completion. Malformed stream records are ignored, request
identity remains scoped to the active analysis, and polling continues to own
completion and failure recovery when streaming is unavailable.

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
starting another model call. Timeline markers are perspective-specific:
ordinary markers show damage received and deaths where the selected player is
the victim, while the selected analysis point is always included for its
analyzed player even when that player was the attacker. An analysis point
replaces competing damage or death markers for the same replay event, uses the blue
analysis treatment, and opens the same coaching inspector for uploaded and
processed saves. If the visualization omits the exact event row, the frontend
synthesizes the marker from the validated selected decision. Round-zero analysis
aliases and duplicate event facts are discarded when resolving that fallback
marker. Markers refresh immediately when the perspective changes. Playback detects the
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
damage, red for death, and blue for an analysis-backed moment. Damage and kill
records for the selected victim at the same round and tick collapse into one
death marker regardless of damage amount or source ordering, while retaining
the merged event details and any attached coaching. The analysis legend swatch has the same visual
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
map. Both processed saves now contain ten saved first-contact analyses for every
player. Changing the selected perspective keeps the playback clock at the same
tick and resolves only that player's event at that exact tick, including when
both players share the same contact event. The inspector opens for the matching
event and remains absent when the newly selected player has no event at that
tick. Analysis-backed moments render as distinct blue timeline markers and also
render the intent follow-up composer
pinned to the bottom of the inspector. The textbox keeps its base height and
scrolls internally instead of resizing. Its typed, per-moment request lifecycle
keeps a one-time submitted intent attached to the stable event ID, disables editing,
preserves the old coaching behind the rotating loading border, ignores stale
responses, and replaces only that moment's coaching after a successful response.
Uploaded and backend-sample viewers now submit the selected moment's stable
`decision_id`, `analysis_id`, `player_id`, and intent text through
`POST /api/analysis/{analysis_id}/intent`. The validated response must identify
the same analysis, player, and decision before its `in_depth_coaching` text can
replace that moment's original coaching. Processed saves keep the composer
disabled because they do not have a live backend analysis job.
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
The selected player's current health appears in the indicator row to the left
of the win-rate strip. Its track remains half the win-rate strip's width and
uses the same thickness. Health is green from 60 HP, tan below 60 HP, and red
below 20 HP; the HP text follows the same color. Unavailable health renders as
an empty muted track.

The processed replay adapter accepts the documented backend
`replay_visualization_v1` output without requiring the sanitized Mirage shape.
It associates backend snapshots with stable top-level players by their unique
display names, normalizes sides and event participants, derives `alive` from
health only when absent, removes duplicate parser event aliases from the viewer,
and generates deterministic event IDs when the backend did not return one. Its
saved-analysis validation requires every player with a decision candidate to
have a corresponding entry in the additive `analyses` array.

The backend-driven sample catalog, replay-envelope schema, adapter, reducer
transition, and tests power the sample-match landing action. The processed
replay catalog remains a distinct, explicitly labelled option.

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

Raw Blob uploads now use an isolated randomized `uploads/` prefix. After the
FastAPI import returns a validated manifest with `visualization_status: ready`,
the browser calls the same-origin Next.js cleanup route to delete that raw
`.dem`; the durable `replays/<replay_id>/` artifacts remain. An incomplete or
failed import keeps the raw object available for recovery, and cleanup failure
does not discard an otherwise usable prepared replay.

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
preparation stage. Both bundled processed replay JSON files and both paired
saved-analysis JSON files are validated directly from disk in the test suite,
including all-player coverage and perspective-specific timeline resolution.

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
- `public/replays/*.analysis.json` - validated all-player saved coaching results
  paired with each processed replay by replay, map, source, player, and tick
- `src/components/ReplayFlowScreen.tsx` - upload/preparation progress, player
  selection, coaching/recovery, safe errors, and final coaching result
- `src/components/SampleSelectorScreen.tsx` - loading, error, empty, list, map
  thumbnail, unavailable, selecting, selected, and retry UI
- `src/components/LandingScreen.tsx` - source selection entry point
- `src/adapters/samples-api.ts` - `GET /api/samples` and replay-envelope
  `POST /api/analyze` transport with JSON/content/status checks
- `src/adapters/replay-api.ts` - typed transport for upload, preparation,
  direct or Blob URL import, status, player selection, coaching, recovery, and
  visualization retrieval
- `src/app/api/blob/upload/route.ts` - same-origin Vercel Blob presigned-upload
  route restricted to `.dem`, public object storage, and a 1 GB maximum
- `src/app/api/blob/cleanup/route.ts` - same-origin deletion route restricted
  to temporary public `uploads/*.dem` objects
- `src/app/api/cron/blob-retention/route.ts` - `CRON_SECRET`-protected,
  allowlisted retention for expired analysis and replay JSON groups
- `src/app/service-internal/blob-artifacts/route.ts` - private service-binding signer
  restricted to known replay/analysis JSON keys, configured access, 128 MB,
  and five-minute single-operation URLs
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
  replay-envelope transition, error/retry/reset, and map-name coverage
- `tests/unit/samples-api.test.ts` - catalog loading and replay-envelope
  selection requests
- `tests/unit/blob-retention-route.test.ts` - Cron authentication, expiration,
  pinned-sample preservation, dry-run reporting, and safe Blob failures
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

Local frontend development is hardened around one dependency/runtime owner per
checkout. The Windows checkout uses PowerShell, Node 24, and pnpm 11; the
preinstall and predev doctor rejects WSL execution through `/mnt/<drive>`, a
non-pnpm installer, the wrong runtime versions, or missing platform-native Next
and Tailwind packages. pnpm's project-local virtual store is explicitly enabled
by disabling the global virtual store, so a user-level setting cannot silently
change the installed workspace structure.

Tailwind source detection is explicitly rooted at `src/`, preventing `.next`,
dependency backups, terminal transcripts, or other project-root artifacts from
being interpreted as arbitrary utility classes. Next development permits the
documented `127.0.0.1` alias in addition to its `localhost` origin.

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. Local development
defaults to `http://127.0.0.1:8000` when the variable is absent. The backend
must allow the frontend origin through `REDECIDE_API_ALLOWED_ORIGINS`.

`NEXT_PUBLIC_REPLAY_UPLOAD_MODE` defaults to `direct`, which sends the file to
the local or configured FastAPI base URL. Set it to `blob` in Vercel and connect
a public Blob store so the Next.js upload and cleanup routes receive the
server-only connected-store credentials. Never expose Blob credentials through
a `NEXT_PUBLIC_*` variable.

Set `CRON_SECRET` only in Vercel's server environment. Retention defaults and
their bounded scan/delete limits are documented in `.env.example`; use
`REDECIDE_RETENTION_DRY_RUN=true` for the first hosted inspection. Increment
`REDECIDE_SAMPLE_CACHE_VERSION` whenever replay preparation semantics become
incompatible with previously cached sample JSON.

Keep `REDECIDE_STORAGE_BACKEND=filesystem` locally. Set it to `blob` for the
Vercel backend. The `REDECIDE_BLOB_SERVICE_URL` service binding is declared in
the root `vercel.json` and injected by Vercel; it is not a dashboard secret and
should not be copied into local `.env` files. Legacy `BLOB_READ_WRITE_TOKEN`
deployments remain supported, but the service binding is used for new OIDC-only
Blob connections.

The Next.js image allowlist permits only the referenced repository's thumbnail
folder on `raw.githubusercontent.com` for non-bundled future maps.

## Verification

The local-development hardening was verified on Windows with Node 24.19.0 and
pnpm 11.9.0. The environment doctor, focused ESLint check, TypeScript check,
frozen-lockfile dry run, real frozen install, and Next.js 16.2.12 Turbopack
production build all passed. A clean development run through
`http://127.0.0.1:3000` rendered without an error overlay or browser console
errors; activating `Use a sample match` navigated to `?view=samples` and
rendered the live backend catalog. The earlier dev-origin warning and pnpm
workspace-structure warning did not recur after the project settings were
synced.

The Blob player-selection consistency fix was checked with 9 passing frontend
signer-route tests, 2 passing focused Python service-binding tests, and a
passing TypeScript check. The legacy-token Blob test is explicitly skipped
when the optional `vercel` Python SDK is absent. The service-binding path used
by the OIDC deployment remains covered without that optional package.

The cache/retention change also passed 21 focused Python regression tests,
covering sample-cache reuse and invalidation, source digest rejection, analysis
preparation behavior, and safe/internal exception logging.

From `frontend/`, the latest checks report:

- Vitest: 13 files and 141 tests collected; all 141 passed, including intent
  response validation and both
  all-player processed-analysis fixtures and perspective-specific event lookup.
- TypeScript: passed
- ESLint: passed with no warnings
- Next.js 16.2.12 production build: passed with Turbopack in the default direct
  mode; `/` and `/_not-found` prerendered, with `/analysis`,
  `/api/blob/upload`, `/api/blob/cleanup`, `/api/cron/blob-retention`, and the private
  `/service-internal/blob-artifacts` signer rendered on demand

The repository-wide Python suite also passed 280 tests with 3 expected skips
and no warnings after installing the root `test` extra, which now includes
Starlette's preferred `httpx2` test transport. One skip needs the optional
legacy Vercel SDK; two need a private processed-replay fixture.

Browser verification against the documented sample responses confirmed:

- landing action opens the selector;
- browser Back returns from samples or showcase to the landing screen;
- browser Forward restores the selected samples or showcase view;
- direct `?view=` links and Back from `/analysis` retain their expected source
  context without console warnings or errors;
- the returned hosted sample renders as a horizontal selectable bar;
- the sample envelope validates as a replay manifest plus analysis metadata;
- sample selection enters the shared player-selection lifecycle;
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
- The hosted sample replay is fixed by the backend and requires its configured
  Blob/model environment; the browser keeps only transient lifecycle state.
- The exact bundled 20 MB native `.dem` completes the local parse and
  preparation pipeline. The versioned-cache fix still needs a hosted
  player-selection smoke test with the deployed Blob/model environment.
- A public Vercel Blob sample has exercised the hosted artifact path, but the
  post-fix end-to-end flow still needs deployment verification.
  Temporary Blob objects are deleted on validated successful import, but a
  failed or interrupted import intentionally retains its object, and cleanup is
  best-effort if Vercel deletion is unavailable. The routes check same-origin
  browser requests and upload constraints, but a public production deployment
  still needs authentication or platform-level protection to prevent upload
  abuse.
- Durable replay and analysis JSON use the private OIDC Blob bridge on Vercel.
  The new retention route still needs one observed scheduled dry run.
- Each processed save contains ten generated coaching moments per player. These
  are static save artifacts rather than live regeneration; uploaded replays use
  their completed backend analysis. Intent submission therefore remains disabled
  for processed saves even though it is connected for uploaded and backend-sample
  analysis jobs.

## Contract/API impact

The frontend now consumes `POST /api/analysis/{analysis_id}/intent` from the
intent-coaching backend branch. It validates the complete structured response,
checks that the returned analysis, player, and decision IDs match the active
request, and uses `in_depth_coaching` as the replacement prose for that selected
moment. The endpoint must be merged into the running backend before this flow is
available locally or in deployment. The sample adapter consumes the backend
replay envelope from `POST /api/analyze`
(`sample_id`, `replay_id`, `manifest`, and `analysis`), while the local
processed-replay adapter and uploaded flow consume the documented
`replay_visualization_v1` shape directly. The frontend implements the
documented `/api/replay/*` and `/api/analysis/*` contracts, including SSE
progress and the disabled-by-default public Blob URL import. Sample and upload
flows share preparation, player selection, repeat coaching, result recovery,
visualization unlock, and replay playback.

The internal Next.js `/api/blob/cleanup` route removes only temporary raw
uploads after successful import and does not change the FastAPI contract. The
`/api/cron/blob-retention` route is authenticated server-only maintenance and
does not expose durable replay deletion to browsers. Sample preparation uses
internal cache metadata and content-aware replay IDs without adding those
fields to the public manifest. The
`/service-internal/blob-artifacts` route is not a browser API; the FastAPI
service binding uses it only to obtain narrowly scoped signed Blob URLs.

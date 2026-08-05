# Frontend Status

Last verified: 2026-08-05 (Asia/Singapore)

## Status

**Backend-driven sample-match selection implemented; replay API adapter ready.**

The landing page's `Use a sample match` action now opens a dedicated sample
selector and calls `GET /api/samples`. Successful responses are validated with
strict Zod schemas before rendering. The same horizontal-list UI handles zero,
one, or many samples and disables backend entries marked unavailable.

Each sample is a full-width selectable bar with its map thumbnail on the left,
backend-provided name, map, description, player count, recommended player, and
availability/selection state. Selecting an available bar submits its stable
`sample_id` to `POST /api/analyze`, validates the preparation response, and
reports how many players the backend made available for the next step. List and
selection errors have separate safe retry paths. Reset aborts in-flight work,
and request cleanup prevents late responses from replacing newer state.

The current backend sample is Mirage. Its reviewed thumbnail from
`MurkyYT/cs2-map-icons` is bundled locally so it does not depend on GitHub being
reachable at runtime. Other canonical map names are normalized to that
repository's base-thumbnail convention and use a remote image with an explicit
missing-image fallback. The UI attributes the thumbnail source.

`AnalysisProgressScreen.tsx` and the old saved-fixture loading path are no
longer part of the rendered flow. Replay upload remains visibly disabled.

The frontend now also has a typed, UI-independent adapter for the complete
uploaded-replay API sequence. It uploads one `.dem` through
`POST /api/replay/upload`, prepares analysis by stable `replay_id`, reads job
and player status, submits the selected stable `player_id` for coaching,
recovers completed results without rerunning coaching, and distinguishes
visualization processing, locked, failed, and ready responses. Every successful
JSON response is validated before the adapter returns it. Abort errors remain
distinguishable from normalized network, HTTP, content-type, JSON, and schema
errors, and backend error details are not exposed through adapter messages.

## Important paths

- `src/components/DecisionFlow.tsx` - request lifecycle, abort handling, and
  sample-selection state wiring
- `src/components/SampleSelectorScreen.tsx` - loading, error, empty, list, map
  thumbnail, unavailable, selecting, selected, and retry UI
- `src/components/LandingScreen.tsx` - source selection entry point
- `src/adapters/samples-api.ts` - `GET /api/samples` and `POST /api/analyze`
  transport with JSON/content/status checks
- `src/adapters/replay-api.ts` - typed transport for upload, preparation,
  status, player selection, coaching, recovery, and visualization retrieval
- `src/domain/replay.ts` - strict replay manifest, analysis, result, and
  visualization boundary schemas
- `src/domain/samples.ts` - strict API schemas, types, and safe map-asset naming
- `src/domain/analysis-flow.ts` - explicit sample-list and selection state
  reducer
- `public/maps/de_mirage.png` - pinned current-sample thumbnail
- `src/app/globals.css` - horizontal sample bars and responsive layout
- `tests/unit/analysis-flow.test.ts` - zero/one/many, unavailable, selection,
  error/retry/reset, and map-name coverage
- `tests/unit/replay-api.test.ts` - multipart upload, endpoint payloads,
  processing states, coaching recovery, visualization gating, validation,
  safe failures, and cancellation

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. Local development
defaults to `http://127.0.0.1:8000` when the variable is absent. The backend
must allow the frontend origin through `REDECIDE_API_ALLOWED_ORIGINS`.

The Next.js image allowlist permits only the referenced repository's thumbnail
folder on `raw.githubusercontent.com` for non-bundled future maps.

## Verification

From `frontend/`, `pnpm run verify` passes:

- Vitest: 3 files, 20 tests passed
- TypeScript: passed
- ESLint: passed with no warnings
- Next.js production build: passed; `/` and `/_not-found` prerendered

Browser verification against the documented sample responses confirmed:

- landing action opens the selector;
- the returned Mirage sample renders as a horizontal selectable bar;
- the local Mirage thumbnail is requested through Next.js image handling;
- selection reaches the selected state after `POST /api/analyze`;
- the preparation result reports one available player;
- no console warnings or errors; and
- no horizontal overflow at a 390-by-844 narrow-screen override.

## Known limitations and next handoff

- Only the thumbnail for the backend's current Mirage fixture is pinned
  locally. Add reviewed local assets to `public/maps/` and the bundled allowlist
  as new backend samples are introduced; otherwise the remote/fallback path is
  used.
- The next player-selection screen is not implemented. The selector stops
  after preserving the validated `analysis_id` and player list returned by
  `/api/analyze`.
- Replay upload, live replay preparation, coaching, intent, and final result UI
  remain outside the rendered flow. The transport is ready, but the landing
  upload control remains disabled until the upload state machine and screens
  are wired.

## Contract/API impact

No backend contract changes. In addition to the compatibility sample APIs, the
frontend adapter now implements the documented `/api/replay/*` and
`/api/analysis/*` contracts without changing the rendered UI.

# Frontend Status

Last verified: 2026-08-05 (Asia/Singapore)

## Status

**Backend-driven sample-match selection implemented.**

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

## Important paths

- `src/components/DecisionFlow.tsx` - request lifecycle, abort handling, and
  sample-selection state wiring
- `src/components/SampleSelectorScreen.tsx` - loading, error, empty, list, map
  thumbnail, unavailable, selecting, selected, and retry UI
- `src/components/LandingScreen.tsx` - source selection entry point
- `src/adapters/samples-api.ts` - `GET /api/samples` and `POST /api/analyze`
  transport with JSON/content/status checks
- `src/domain/samples.ts` - strict API schemas, types, and safe map-asset naming
- `src/domain/analysis-flow.ts` - explicit sample-list and selection state
  reducer
- `public/maps/de_mirage.png` - pinned current-sample thumbnail
- `src/app/globals.css` - horizontal sample bars and responsive layout
- `tests/unit/analysis-flow.test.ts` - zero/one/many, unavailable, selection,
  error/retry/reset, and map-name coverage

## Configuration

Set `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`. Local development
defaults to `http://127.0.0.1:8000` when the variable is absent. The backend
must allow the frontend origin through `REDECIDE_API_ALLOWED_ORIGINS`.

The Next.js image allowlist permits only the referenced repository's thumbnail
folder on `raw.githubusercontent.com` for non-bundled future maps.

## Verification

From `frontend/`, `pnpm run verify` passes:

- Vitest: 2 files, 11 tests passed
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
  remain outside this slice.

## Contract/API impact

No backend contract changes. The frontend now consumes the existing
compatibility endpoints `GET /api/samples` and `POST /api/analyze` exactly as
documented.

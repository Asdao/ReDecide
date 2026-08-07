# Current state of RE:DECIDE

Last reviewed: 2026-08-07 (Asia/Singapore)

## Product flow

```text
Use a sample match
  OR upload a native .dem
  -> backend creates a replay manifest
  -> analysis preparation discovers players and decision moments
  -> user selects a player
  -> coaching runs for that player's eligible moments
  -> replay visualization unlocks
  -> frontend shows the radar, timeline, event inspector, win-rate strip, and advice
```

The frontend also has a separate processed-replay catalog for the bundled
Mirage and Inferno saves. Those saves exercise the viewer without requiring a
new upload; Inferno includes a saved coaching result.

## What works now

- The unified FastAPI gateway exposes health, sample, replay, analysis, SSE,
  and progress-log routes.
- Native `.dem` upload parses the replay once and returns a safe replay manifest
  with stable `replay_id` and `player_id` values.
- The frontend is connected to the upload, preparation, player-selection,
  coaching, result-recovery, and visualization APIs.
- Sample selection calls the backend catalog and enters the same shared analysis
  lifecycle as an uploaded replay.
- The replay engine produces win-chance timelines and outcome-blind coaching
  evidence. A selected player may be analyzed repeatedly; the default quota is
  ten moments per player.
- The viewer supports map-aware player positions, round selection, playback,
  scrubbing, speed controls, event markers, keyboard navigation, and a moment
  inspector.
- Local artifacts use the filesystem under `data/runtime/`. Vercel Services
  can use the private Blob bridge for durable replay and analysis artifacts.
- The Python HTTP coach is selected by default when a provider base URL and key
  are configured. The legacy Node/Pi path remains available with
  `REDECIDE_COACH_MODE=pi`.

## Known limits

- A real native `.dem` has not yet completed the full backend-to-viewer flow in
  this checkout. Browser QA uses validated replay fixtures for post-upload
  states.
- A public Vercel Blob upload/import has not yet completed a hosted end-to-end
  run. The frontend supports Blob mode, but the backend import route remains
  disabled by default and accepts public Blob URLs only.
- Vercel Services automatically use durable Blob restoration when the private
  frontend service binding is present, so repeat sample runs can cross FastAPI
  instances without losing replay or analysis state.
- Player intent and follow-up questions have UI scaffolding, but submission is
  disabled because no public backend endpoint or response contract exists.
- Only Inferno currently has a paired saved coaching result in the processed
  replay catalog.
- Analysis state is process-local in the default filesystem mode and is lost
  when the backend restarts. Use the Blob storage backend for deployment
  durability.

## Timeline semantics

- The selected-player view marks damage received and deaths, plus the selected
  analysis point. It does not treat damage dealt or kills as coaching moments
  for the selected player.
- A run can contain several analyzed moments, capped by
  `REDECIDE_ANALYSES_PER_PLAYER` (default `10`, clamped to `1`–`10`).
- The win-rate strip uses the latest estimate at or before the playback tick in
  the current round. It shows a muted 50/50 baseline when no current-round
  estimate is available.
- Coaching recommendations are model estimates. Unsupported or high-entropy
  states must remain abstentions rather than definitive instructions.

## Main folders

- `backend/app/` joins replay preparation, player selection, storage, and
  coaching orchestration.
- `backend/replay_api/` receives `.dem` files and creates replay artifacts.
- `backend/replay_engine/` parses replay data and calculates model signals.
- `frontend/` contains the Next.js interface, adapters, contracts, and viewer.
- `agent-harness/` contains the optional legacy Pi/Node coaching process.
- `data/public/` and `frontend/public/replays/` contain checked-in demo assets;
  `data/runtime/` is local temporary state and should not be treated as source.

## Configuration references

- Copy `.env.example` to `.env` for local backend settings.
- Set `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` in
  `frontend/.env.local` for standalone local development; Vercel Services uses
  same-origin `/api` routes and normally leaves it unset.
- Keep `NEXT_PUBLIC_REPLAY_UPLOAD_MODE=direct` locally. Use `blob` only with
  the Next.js Blob routes, a public Blob store, and
  `REDECIDE_BLOB_IMPORT_ENABLED=true` configured together.
- See [the API reference](../backend/app/API.md), [frontend status](../frontend/STATUS.md),
  and [deployment guide](VERCEL_DEPLOYMENT.md) for the current contracts and
  verification notes.

## Latest maintenance verification

On 2026-08-07, the frontend passed 138 Vitest tests, TypeScript, ESLint, and a
production Next.js build. The optional agent harness passed 26 Vitest tests,
TypeScript, and its production build. The repository dependency-policy check,
both pnpm high-severity audits, and both uv lockfile checks passed. The Python
suite passed 280 tests with 3 expected skips and no warnings when installed
with the `test` extra. One skip covers the absent optional legacy Vercel SDK;
two require a private processed-replay fixture that is not in this checkout.
The OIDC service-binding deployment path remains covered.

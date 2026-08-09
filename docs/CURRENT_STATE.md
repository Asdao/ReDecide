# Current state of RE:DECIDE

Last reviewed: 2026-08-09 (Asia/Singapore)

## Current product flow

```text
Upload a native .dem or choose a backend sample
  -> FastAPI parses the replay and creates a replay_id
  -> analysis preparation discovers players and first-contact decisions
  -> the user selects a player
  -> the configured coach analyzes up to 10 diverse moments
  -> the visualization unlocks
  -> the frontend shows radar playback, timeline events, win-rate estimates,
     and advice
  -> the user may submit their intent for one analyzed moment
  -> the backend returns contextual coaching for that exact decision
```

The frontend also provides bundled Mirage and Inferno processed replays. They
exercise the viewer without parsing or calling a provider. They contain saved
analysis data, but intent submission is disabled because static saves have no
live `analysis_id`.

## Implemented

- One public FastAPI gateway exposes health, sample, replay, analysis, progress,
  result, and intent-coaching routes.
- Native `.dem` upload parses once and creates separate coaching,
  visualization, and manifest artifacts.
- Player selection uses stable `player_id` values discovered from the replay.
- The replay pipeline detects first-damage contact decisions and selects up to
  `REDECIDE_ANALYSES_PER_PLAYER` diverse moments (default `10`, range `1-10`).
- The replay-value engine produces a CT/T win-probability timeline. These are
  model estimates, not proof that a player made a good or bad decision.
- The frontend supports upload/sample selection, player selection, progress,
  result recovery, radar playback, round navigation, timeline markers, event
  inspection, win-rate display, and coaching advice.
- Uploaded and backend-sample analyses can submit intent through
  `POST /api/analysis/{analysis_id}/intent`.
- Intent coaching resolves the exact completed player and decision, restricts
  evidence to the bounded contact/reaction window, anonymizes provider-visible
  identifiers, and requires a strict tactical-adjustment enum plus
  claim-to-evidence mappings. Feasibility and team coordination remain
  explicitly unestablished because the current telemetry cannot prove them.
  The backend—not the provider—renders visible factual text from
  parser-owned evidence. It rejects unsupported evidence references, internal
  prompt labels, provider-authored fact text, public player aliases, and exact
  tick coordinates in coaching prose, then fails closed when output is unsafe
  or the provider is unavailable.
- When the parser provides the required telemetry, intent context now includes
  contact health/armor/location/inventory, held utility, immediate movement,
  deterministic action signals, and teammate spacing. Missing evidence remains
  unknown rather than being converted into claims that something did not occur.
- Local replay and analysis state persists under `data/runtime/`; completed
  per-player results can be restored after a backend restart.
- Vercel Services can use private Blob-backed replay/analysis persistence and
  optional public Blob upload/import.

## Intent response

The intent API returns:

- the validated `analysis_id`, `player_id`, and `decision_id`;
- the submitted `user_intent`;
- `intent_feasibility`;
- `coordination_gap`;
- `recommended_cs2_adjustment`;
- `in_depth_coaching`;
- `knowledge_cutoff_tick`; and
- grounded `facts_referenced` IDs.

The current UI validates the whole response but displays only
`in_depth_coaching`. Displaying the remaining structured fields is a frontend
enhancement, not a missing backend capability.

## Known limits

- A fresh browser upload through a live provider has not been repeated after
  the latest intent fix. The local Vitality-versus-G2 Inferno `.dem` has been
  freshly parsed and exercised through player selection, analysis, and the
  exact-decision intent API using a deterministic provider.
- Live coaching requires a valid provider URL, supported model name, and API
  key. Provider availability, latency, cost, and account limits are external
  deployment concerns.
- Exact geometry, cover visibility, line of sight, voice communication, and
  enemy intent are not established by the current parser projection. The
  backend rejects provider responses that present those as replay facts.
- Intent results are request responses; they are not currently persisted as a
  conversation history or cached by intent text.
- Bundled processed replays cannot submit live intent.
- Hosted public Blob upload/import and durable restoration still need a full
  deployed smoke test. Public upload must be protected before untrusted use.
- There is no reviewed human evaluation set or versioned coaching rubric yet.
- The replay-job response is not the frozen `DecisionCard` product contract;
  the frozen fixture contracts remain a separate compatibility surface.

## Timeline semantics

- Damage received and deaths are replay markers. First-damage contacts are the
  analysis anchors; not every marker is an analyzed coaching point.
- A player run can contain several analyzed moments. The selector spreads them
  across the match instead of always choosing the first candidate.
- The win-rate strip uses the latest estimate at or before the current replay
  tick in the same round. It shows a muted 50/50 baseline when no estimate is
  available.
- Intent coaching uses the bounded `action_close_tick` as its knowledge cutoff
  so it can inspect the immediate post-contact reaction. Kill, death,
  round-result, match-result, and later events remain excluded.

## Main folders

- `backend/app/` - FastAPI integration, orchestration, contracts, and coaching.
- `backend/replay_api/` - native upload and replay artifacts.
- `backend/replay_engine/` - parsing, replay-value models, and analysis signals.
- `frontend/` - Next.js product, adapters, and replay viewer.
- `agent-harness/` - optional legacy Pi/Node provider process.
- `data/public/` and `frontend/public/replays/` - checked-in public assets.
- `data/runtime/` - ignored local replay and analysis state.

## Configuration

- Copy `.env.example` to `.env`.
- For normal local coaching, set `REDECIDE_COACH_MODE=http`, a supported
  `HARNESS_MODEL`, `HARNESS_MODEL_BASE_URL`, and either `DEEPSEEK_API_KEY` or
  `HARNESS_MODEL_API_KEY`.
- Set `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` and
  `NEXT_PUBLIC_REPLAY_UPLOAD_MODE=direct` in `frontend/.env.local`.
- Use Blob mode only when the Next.js Blob routes and FastAPI import route are
  configured together.

## Latest verification

On 2026-08-09:

- Python: 327 passed, 3 expected skips, 88 subtests passed.
- Intent/transport/API focused suite: 74 passed, 82 subtests passed.
- Frontend: 142 Vitest tests passed; TypeScript, ESLint, and production build
  passed.
- Agent harness: 26 Vitest tests passed; TypeScript and production build passed.
- Endpoint regressions confirm that an unknown decision returns `404`, sparse
  evidence returns `422`, invalid or ungrounded model output returns `503`, and
  provider failure returns `503` without fabricated coaching.
- A fresh full check parsed `vitality-vs-g2-m2-inferno.dem`, found 10 players,
  analyzed an exact HeavyGoD decision, retained its cutoff as structured
  metadata, and returned backend-rendered coaching without prompt tokens,
  player aliases, exact tick prose, raw IDs, or later outcomes.

No paid/live provider call was made during this verification.

Use the [root overview](../README.md) and [local setup guide](README.md) with
this file as the current project-level documentation. Component status, API,
deployment, and plan documents are retained for ownership history and may lag
behind the integrated branch.

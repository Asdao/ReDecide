# RE:DECIDE API

Run the public backend from the repository root

```powershell
uv run uvicorn backend.app.main:app --env-file .env --reload --port 8000
```

Open the interactive API page at `http://127.0.0.1:8000/docs`.

## Main flow

```text
upload .dem -> prepare analysis -> choose player -> run coach -> get result
            -> optionally submit intent for one analyzed decision
```

Intent coaching is an optional follow-up after the selected player's normal
analysis completes. It is available for uploaded and backend-sample jobs with a
live `analysis_id`; bundled static processed replays cannot use it.

## Active APIs

### `GET /api/health`

- **Input:** None.
- **Output:** JSON: `{"status":"ok"}`.
- **Summary:** Checks whether the backend is running.

### `POST /api/replay/upload`

- **Input:** `multipart/form-data` containing one `.dem` file in the `file` field.
- **Output:** JSON replay manifest containing `replay_id`, map, rounds, players, and processing status.
- **Summary:** Uploads and parses the replay once, then creates the files needed for analysis and visualization.

### `POST /api/replay/import-url` (disabled by default)

- **Input:** JSON: `{"url":"<public-vercel-blob-url>","filename":"match.dem"}`.
- **Output:** The same JSON replay manifest returned by `/api/replay/upload`.
- **Summary:** Downloads a `.dem` already stored in public Vercel Blob, then sends it through the normal replay parser.

Set `REDECIDE_BLOB_IMPORT_ENABLED=true` and restart FastAPI to register this
route. When disabled, it returns `404` and does not appear in OpenAPI. The route
accepts only `https://<store-id>.public.blob.vercel-storage.com/...` URLs.

### `GET /api/replay/{replay_id}/status`

- **Input:** `replay_id` in the URL.
- **Output:** JSON replay manifest containing the latest replay, coaching, and visualization status.
- **Summary:** Checks whether replay processing and visualization generation are ready.

### `GET /api/replay/{replay_id}/json`

- **Input:** `replay_id` in the URL.
- **Output:** Downloadable visualization JSON, or a JSON status message if it is locked or still processing.
- **Summary:** Returns the full minimap, timeline, player-position, round, and event data after coaching succeeds.

### `POST /api/analysis/prepare`

- **Input:** JSON: `{"replay_id":"<replay_id>"}`.
- **Output:** JSON analysis job containing `analysis_id`, status, and progress URLs.
- **Summary:** Starts preparing replay events, players, decision moments, and win chances without calling the coach yet.

### `GET /api/analysis/{analysis_id}`

- **Input:** `analysis_id` in the URL.
- **Output:** JSON containing job status, `players_available`, `result_available`, per-player run statuses, and progress URLs.
- **Summary:** Checks whether player selection or the final coaching result is ready.

### `GET /api/analysis/{analysis_id}/players`

- **Input:** `analysis_id` in the URL.
- **Output:** JSON list of selectable players and their stable `player_id` values.
- **Summary:** Returns the players that can be selected for coaching.

### `POST /api/analysis/{analysis_id}/run`

- **Input:** `analysis_id` in the URL and JSON: `{"player_id":"<player_id>"}`.
- **Output:** JSON containing the selected player's events, decision moments, win timeline, and coaching advice.
- **Summary:** Selects one player, runs the live coach, and returns the completed analysis. Calling it again with another player reuses replay preparation and creates a separate per-player run.

### `GET /api/analysis/{analysis_id}/result`

- **Input:** `analysis_id` in the URL. Optionally pass `?player_id=<player_id>` to retrieve that player's saved result.
- **Output:** JSON containing the completed analysis, or a status response if it is not ready.
- **Summary:** Retrieves a saved coaching result again without running the coach a second time. Results are retained separately for each analyzed player.

### `POST /api/analysis/{analysis_id}/intent`

- **Input:** `analysis_id` in the URL and JSON containing the same
  `analysis_id`, the completed analysis's `player_id`, the exact analyzed
  `decision_id`, and `intent_text` from 1 to 240 characters.
- **Output:** JSON containing the validated IDs, `user_intent`,
  `intent_feasibility`, `coordination_gap`, `recommended_cs2_adjustment`,
  `in_depth_coaching`, `knowledge_cutoff_tick`, and grounded
  `facts_referenced` IDs.
- **Summary:** Re-evaluates one completed decision using the player's stated
  intent and only replay evidence available within the bounded contact/reaction
  window ending at `action_close_tick`.

The route requires a completed analysis for that exact player and decision. It
does not fall back to the first analyzed moment. Errors are `400` for a path/body
analysis-ID mismatch, `404` for an unknown analysis/player/decision, `409` when
the player run is incomplete, `422` for insufficient bounded evidence, `503`
for an unavailable provider or invalid/ungrounded provider response, and `504`
for provider timeout. Provider failure never returns fabricated coaching.
When available, the bounded provider context contains the player's contact
health, armor, parser region, inventory/utility, immediate movement and
teammate spacing. It does not expose the complete replay, raw player IDs,
kill/death outcomes, round results, or events after `action_close_tick`.
The provider returns conservative assessment markers, one tactical-adjustment
enum, and structured claim-to-evidence mappings. Intent feasibility and team
coordination remain `NOT_ESTABLISHED` because current telemetry cannot prove
them. Public factual prose is rendered by the backend
from parser-owned evidence statements. Provider-authored factual sentences,
unknown evidence IDs, internal prompt labels, player aliases, and exact tick
coordinates in coaching prose fail closed. `knowledge_cutoff_tick` remains
available as structured response metadata.
Explicit user wording is conservatively categorized as information gathering,
escape/reset, taking a duel, waiting for support, creating space with utility,
or repositioning. When no tactical goal is clear, the route returns a concise
clarification request without calling the provider or exposing replay details.
Player-facing evidence uses normal CS2 language rather than parser fields,
movement thresholds, or internal action-classifier labels.

### `GET /api/analysis/{analysis_id}/events`

- **Input:** `analysis_id` in the URL.
- **Output:** `text/event-stream` containing live progress updates.
- **Summary:** Streams analysis progress to the frontend while the job is running.

### `GET /api/analysis/{analysis_id}/logs`

- **Input:** `analysis_id` in the URL.
- **Output:** Plain-text JSONL progress logs.
- **Summary:** Returns saved progress messages for debugging and status display.

## Compatibility APIs

These routes still exist, but the new uploaded-replay frontend should not use
them unless specifically required.

### `POST /api/replay/convert`

- **Input:** `multipart/form-data` containing one `.dem` file in the `file` field.
- **Output:** The same JSON replay manifest returned by `/api/replay/upload`.
- **Summary:** Older name for the replay upload endpoint; new code should use `/api/replay/upload`.

### `GET /api/samples`

- **Input:** None.
- **Output:** The stable `SamplesResponse` shape with the hosted Ancient samples.
- **Summary:** Lists the public samples without downloading or parsing either demo. The
  catalog includes the original full-size sample. On Vercel (`VERCEL=1`), it
  also includes a separately selectable `3dmax-vs-falcons-m2-ancient-20mb`
  quick sample.

### `POST /api/analyze`

- **Input:** JSON containing one of the sample ids returned by `GET /api/samples`,
  such as `{"sample_id":"3dmax-vs-falcons-m2-ancient-20mb"}`.
- **Output:** `{sample_id, replay_id, manifest, analysis}`. `manifest` is the
  `replay_manifest_v1` payload and `analysis` is the normal analysis-job metadata.
- **Summary:** Downloads and parses the hosted sample only when its deterministic
  replay artifacts are absent or invalid, then runs the real replay preparation
  pipeline. Subsequent requests reuse the cached manifest/coaching/visualization
  artifacts only when their internal cache metadata exactly matches the current
  sample source and pipeline cache version.

The primary hosted sample's current deterministic `replay_id` is
`a9b8732ecaadca5ec78218ac6c647258`; the 20 MB sample uses
`5b575a75255d339223c5df6e52c33ec7`. These IDs are content/configuration
fingerprints, not permanent public constants. Increment
`REDECIDE_SAMPLE_CACHE_VERSION` when sample preparation semantics change so a
deployment cannot reuse artifacts produced by incompatible code. The raw source
is validated as an allowlisted public Vercel Blob URL and by expected size for
the full sample; `REDECIDE_SAMPLE_SHA256` can additionally pin its exact digest.
The quick sample has a built-in SHA-256 digest check.
The frontend can continue with `/api/analysis/{analysis_id}/players`,
`/api/analysis/{analysis_id}/run`, `/api/analysis/{analysis_id}/result`, and
`/api/replay/{replay_id}/json` using the returned IDs.

## Unavailable API

### `POST /api/analyze-json`

- **Input:** Not accepted by the public backend.
- **Output:** HTTP `404`.
- **Summary:** This old frozen-contract fixture route is intentionally disabled
  on the public gateway. Use `/api/analysis/{analysis_id}/intent` for the live
  replay intent flow.

## IDs to remember

- `replay_id` identifies the uploaded replay and its visualization files.
- `analysis_id` identifies the preparation and coaching job.
- `player_id` identifies the selected player inside that replay.
- `decision_id` identifies one analyzed moment for that player and must match
  the exact decision being discussed.

## Current requirements and limits

- With `HARNESS_MODEL_BASE_URL` and `DEEPSEEK_API_KEY` (or
  `HARNESS_MODEL_API_KEY`) configured, live coaching uses the Python HTTP
  adapter by default. Start Uvicorn with `--env-file .env`, because Uvicorn
  does not load a repository `.env` implicitly.
- The legacy Pi subprocess remains available by setting
  `REDECIDE_COACH_MODE=pi`; that mode requires Node.js and installed
  `agent-harness` dependencies.
- Direct upload expects the `.dem` file; the separate Blob URL route is disabled by default.
- The local Vitality-versus-G2 Inferno `.dem` has completed a fresh parse,
  player-selection, analysis-run, and exact-decision intent API check using a
  deterministic provider. A fresh browser/live-provider and hosted deployment
  flow still need smoke testing.
- On Vercel Services, analysis state and results automatically use the private
  frontend Blob binding and survive function restarts. Set
  `REDECIDE_STORAGE_BACKEND=filesystem` only to opt out explicitly.
  The integrated backend's default local state is under
  `data/runtime/analysis-logs/analysis-state/<analysis_id>/`.
- Preparation exceptions retain a generic public job error while their full
  traceback and analysis ID are written to server runtime logs.
- Intent coaching requires a completed per-player analysis and a configured
  provider. The current UI renders `in_depth_coaching`; the complete structured
  response remains available in the API response.
- Each selected player run coaches up to ten distinct moments by default. Set
  `REDECIDE_ANALYSES_PER_PLAYER` to an integer from 1 to 10 to change the quota.
  Results expose an additive `analyses` array; `selected_decision` and
  `coach_analysis` remain aliases for the first entry.

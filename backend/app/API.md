# RE:DECIDE API

Run the public backend from the repository root:

```powershell
uv run uvicorn backend.app.main:app --env-file .env --reload --port 8000
```

Open the interactive API page at `http://127.0.0.1:8000/docs`.

## Main flow

```text
upload .dem -> prepare analysis -> choose player -> run coach -> get result
```

Player intent and follow-up questions are not supported yet. The frontend should
not build or send intent data at this stage.

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
- **Output:** The stable `SamplesResponse` shape with the hosted Ancient sample.
- **Summary:** Lists the public sample without downloading or parsing its 321,584,788-byte demo.

### `POST /api/analyze`

- **Input:** JSON: `{"sample_id":"3dmax-vs-falcons-m2-ancient"}`.
- **Output:** `{sample_id, replay_id, manifest, analysis}`. `manifest` is the
  `replay_manifest_v1` payload and `analysis` is the normal analysis-job metadata.
- **Summary:** Downloads and parses the hosted sample only when its deterministic
  replay artifacts are absent, then runs the real replay preparation pipeline.
  Subsequent requests reuse the cached manifest/coaching/visualization artifacts.

The hosted sample's deterministic `replay_id` is
`59a7b7145da41a0c86f60bb59cb6c033`. The raw source is validated as an
allowlisted public Vercel Blob URL with the expected 321,584,788-byte seed.
The frontend can continue with `/api/analysis/{analysis_id}/players`,
`/api/analysis/{analysis_id}/run`, `/api/analysis/{analysis_id}/result`, and
`/api/replay/{replay_id}/json` using the returned IDs.

## Unavailable API

### `POST /api/analyze-json`

- **Input:** Not accepted by the public backend.
- **Output:** HTTP `404`.
- **Summary:** This old fixture intent route is intentionally disabled and must not be used by the frontend.

## IDs to remember

- `replay_id` identifies the uploaded replay and its visualization files.
- `analysis_id` identifies the preparation and coaching job.
- `player_id` identifies the selected player inside that replay.

## Current requirements and limits

- With `HARNESS_MODEL_BASE_URL` and `DEEPSEEK_API_KEY` (or
  `HARNESS_MODEL_API_KEY`) configured, live coaching uses the Python HTTP
  adapter by default. Start Uvicorn with `--env-file .env`, because Uvicorn
  does not load a repository `.env` implicitly.
- The legacy Pi subprocess remains available by setting
  `REDECIDE_COACH_MODE=pi`; that mode requires Node.js and installed
  `agent-harness` dependencies.
- Direct upload expects the `.dem` file; the separate Blob URL route is disabled by default.
- No real `.dem` has completed the full flow yet.
- With `REDECIDE_STORAGE_BACKEND=blob` on Vercel Services, analysis state and
  results survive function restarts through the private frontend Blob binding.
  The default local filesystem mode persists under `data/runtime/analysis`.
- Player intent and follow-up questions are not implemented.

# Replay FastAPI

This service accepts a native CS2 `.dem`, calls the replay engine's loader once, and
creates three artifacts under `REDECIDE_REPLAY_STORE`:

```text
visualization.json  -> full replay JSON, released after coaching
coaching.json       -> coaching FastAPI and decision pipeline
manifest.json       -> safe map/player/status metadata
```

The default local artifact root is `data/runtime/replays/<replay_id>/`.
With `REDECIDE_STORAGE_BACKEND=blob`, replay artifacts are durable Blob JSON.
Vercel Services enable this automatically when their private Blob service
binding is present, unless filesystem storage is explicitly selected.
New Vercel OIDC connections use the private `REDECIDE_BLOB_SERVICE_URL`
service binding declared in `vercel.json`; local development does not set that
binding and continues to use the filesystem by default.

These JSON artifacts are server-side application data, not browser cache. A
successful native replay produces all three files above. The integrated local
backend stores restart-safe analysis data separately under
`data/runtime/analysis-logs/analysis-state/<analysis_id>/state.json` and
`result.json`. Blob-backed deployments use the
`analysis/<analysis_id>/state.json` and `result.json` object keys.
The Vercel deployment runs the authenticated `/api/cron/blob-retention` route
daily. By default it removes failed analysis groups after 1 day, other analysis
groups after 14 days, and ordinary replay groups after 30 days. Hosted sample
replays carry internal `_sample_cache.pinned: true` metadata and are retained.
The route deletes only complete allowlisted JSON groups, caps each run, keeps a
group when inspection fails, and can be tested with
`REDECIDE_RETENTION_DRY_RUN=true`. It is not a public replay-deletion API.

The default frontend origins are `http://localhost:3000` and
`http://127.0.0.1:3000`. Set `REPLAY_API_ALLOWED_ORIGINS` to a
comma-separated list to override them.
Only `GET` and `POST` are allowed by the configured CORS policy.

## Run

```powershell
uvicorn backend.replay_api.main:app --port 8001
```

## `GET /api/health`

Returns `{"status":"ok"}` with HTTP `200`.

## `POST /api/replay/upload`

Accepts a `multipart/form-data` upload with field `file`. The filename must
end in `.dem`. Native parsing completes before the response; parsing runs in a
worker thread so it does not block the async server loop. After parsing, this
endpoint immediately returns the safe manifest while the large visualization
JSON is generated in the background. A missing `file` field produces FastAPI's
standard `422` validation response.

Response `202`:

```json
{
  "schema_version": "replay_manifest_v1",
  "replay_id": "0123456789abcdef0123456789abcdef",
  "source": "match.dem",
  "map": {"name": "de_mirage", "tick_rate": 64.0},
  "players": [
    {"player_id": "p1", "display_name": "Player One", "sides": ["CT"]}
  ],
  "rounds": [{"round_num": 1, "start": 100, "end": 5000}],
  "visualization_status": "processing",
  "coaching_status": "ready",
  "visualization_unlocked": false
}
```

The frontend can use `players` immediately and send `replay_id` to the
Coaching FastAPI. Manifest rounds contain only safe boundaries; winners and
other outcome fields are not included before coaching completes.

Manifest variables:

| Field | Meaning |
|---|---|
| `schema_version` | `replay_manifest_v1`. |
| `replay_id` | Shared identifier for both artifact branches. |
| `source` | Uploaded `.dem` filename. |
| `map` | Map name and numeric tick rate. |
| `players` | Player IDs, display names, and observed sides. |
| `rounds` | Safe round boundaries before coaching. |
| `visualization_status` | `processing`, `ready`, or `failed`. |
| `coaching_status` | `ready` after `coaching.json` is persisted, then `complete` after successful `/run`. |
| `visualization_unlocked` | `false` until coaching completes successfully. |

Upload errors:

- `415`: filename is not a `.dem`.
- `422`: replay engine could not parse the demo.

The application does not impose a demo-size limit. Reverse proxies, hosting
platforms, or the operating system may still impose their own limits.

## `GET /api/replay/{replay_id}/status`

Returns the persisted safe manifest. `visualization_status` is one of:

- `processing`: player/map metadata is ready; full JSON is being generated.
- `ready`: full JSON is generated but remains locked until coaching completes.
- `failed`: generation failed and `visualization_error` is provided.

The response is the same manifest shape returned by `/upload`. Errors: `404`
when `replay_id` is unknown.
`visualization_status: "ready"` does not mean the frontend can download the
file; `visualization_unlocked` must also be `true`.

## `GET /api/replay/{replay_id}/json`

Returns the full visualization JSON as an attachment only after both of these
conditions are true:

```text
visualization_status == "ready"
visualization_unlocked == true
```

Before coaching, it returns `403` with:

```json
{"replay_id":"<id>","status":"locked_until_coaching_complete"}
```

While visualization generation is still running, it returns `202`.
The processing response is:

```json
{"replay_id":"<id>","status":"processing"}
```

The released JSON contains:

| Field | Meaning |
|---|---|
| `schema_version` | `replay_visualization_v1`. |
| `replay_id` | Shared artifact ID. |
| `source` | Uploaded filename. |
| `map` | Map name and tick rate. |
| `players` | All discovered players and observed sides. |
| `rounds` | Full round metadata, including outcome fields after unlock. |
| `events` | Flattened kill, damage, bomb, and parser events sorted by tick. |
| `ticks` | All player snapshots, including `X`, `Y`, `Z`, health, side, and alive state when available. |

In filesystem mode the response is an `application/json` attachment named
`<uploaded-name>.replay.json`. In Blob mode the endpoint returns a `307`
redirect to the stored visualization so the serverless function does not relay
the large payload. Other statuses are `403` while locked, `202` while
generation is running, `404` for an unknown replay, and `422` when
visualization generation failed.

Response status: `200` when released; `403` while coaching has not unlocked it;
`202` while visualization generation is still running; `404` for an unknown
replay; `422` if visualization generation failed.

If coaching fails, `coaching_status` remains `ready` and
`visualization_unlocked` remains `false`; the full visualization JSON stays
unavailable.

## `POST /api/replay/convert`

Compatibility alias for `/api/replay/upload`. It now returns the same `202`
safe manifest and does not bypass the coaching unlock. New clients should use
`/upload`.

It has the same `multipart/form-data` request and `415`/`422` upload errors as
`/upload`.

## Analysis and coaching handoff

The public product normally runs the unified gateway at
`backend.app.main:app`. After `/api/replay/upload` returns, start analysis with:

```json
{"replay_id":"0123456789abcdef0123456789abcdef"}
```

Send this body to `POST /api/analysis/prepare`, read the available players from
`GET /api/analysis/{analysis_id}/players`, and submit the selected `player_id`
to `POST /api/analysis/{analysis_id}/run`. A successful player run unlocks the
visualization. An optional intent follow-up then uses
`POST /api/analysis/{analysis_id}/intent` with that completed player and an
exact analyzed `decision_id`.

The analysis/coaching pipeline reads `coaching.json`; it does not receive the
frontend visualization artifact and does not reparse the native `.dem`.

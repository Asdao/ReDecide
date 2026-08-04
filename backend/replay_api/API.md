# Replay FastAPI

This service accepts a native CS2 `.dem`, calls Blackbox's loader once, and
creates two artifacts under `REDECIDE_REPLAY_STORE`:

```text
visualization.json  -> full replay JSON, released after coaching
coaching.json       -> coaching FastAPI and decision pipeline
manifest.json       -> safe map/player/status metadata
```

The default artifact root is `data/runtime/replays/<replay_id>/`.

## Run

```powershell
uvicorn backend.replay_api.main:app --port 8001
```

## `GET /api/health`

Returns `{"status":"ok"}` with HTTP `200`.

## `POST /api/replay/upload`

Accepts a multipart upload with field `file`. The filename must end in
`.dem`. Parsing is performed in a worker thread. After parsing, this endpoint
immediately returns the safe manifest while the large visualization JSON is
generated in the background.

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

Upload errors:

- `415`: filename is not a `.dem`.
- `422`: Blackbox could not parse the demo.

The application does not impose a demo-size limit. Reverse proxies, hosting
platforms, or the operating system may still impose their own limits.

## `GET /api/replay/{replay_id}/status`

Returns the persisted safe manifest. `visualization_status` is one of:

- `processing`: player/map metadata is ready; full JSON is being generated.
- `ready`: full JSON is generated but remains locked until coaching completes.
- `failed`: generation failed and `visualization_error` is provided.

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

## `POST /api/replay/convert`

Compatibility alias for `/api/replay/upload`. It now returns the same `202`
safe manifest and does not bypass the coaching unlock. New clients should use
`/upload`.

## Coaching handoff

Immediately after `/upload` returns, call the Coaching FastAPI with:

```json
{"replay_id":"0123456789abcdef0123456789abcdef"}
```

The coaching service reads `coaching.json`. It never receives the frontend
visualization artifact and never reparses the native `.dem`.

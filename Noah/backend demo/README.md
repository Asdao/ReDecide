# RE:DECIDE backend demo

This is the first runnable backend demo for RE:DECIDE. It drives the actual
FastAPI application in-process, so the demo exercises the same route and
orchestration boundaries used by a frontend.

## Run

From the repository root:

```powershell
uv run --extra test python "Noah/backend demo/cli.py"
```

The `test` extra supplies the HTTP client used to call the ASGI application.
The demo does not start a second web server; `httpx.ASGITransport` sends real
HTTP requests directly to the FastAPI app.

## Request flow

The command performs this sequence automatically:

```text
replay input
  -> GET /api/health
  -> POST /api/analysis/prepare
  -> poll GET /api/analysis/{id}/players
  -> choose first player with a decision candidate
  -> POST /api/analysis/{id}/run
  -> GET /api/analysis/{id}/events
  -> GET /api/analysis/{id}/result
```

Preparation runs through `AnalysisService`, the replay pipeline, progress
logging, player indexing, probability estimation, and the configured coach
adapter. The demo coach attempts Noah's outcome-blind analysis and uses a
deterministic reset recommendation if the optional model runtime is
unavailable.

## Input selection

The replay source is selected automatically. Once preparation returns the
player selector, the demo prompts you to choose one of the eligible players.
Pass `--player-id` to run without that prompt.

- `--demo PATH` explicitly supplies a native `.dem` input.
- Without `--demo`, the first `.dem`/`.demo` under `data/samples/` or this
  folder is tried.
- If native extraction fails, `--json PATH` is used.
- Without `--json`, the bundled [`demo_replay.json`](demo_replay.json) is used.

Examples:

```powershell
uv run --extra test python "Noah/backend demo/cli.py" --demo data/samples/match.dem
uv run --extra test python "Noah/backend demo/cli.py" --json path/to/normalized.json
uv run --extra test python "Noah/backend demo/cli.py" --version v5
uv run --extra test python "Noah/backend demo/cli.py" --player-id t1
```

## Output

Standard output contains only key event rows:

```text
0002.56  FIRST_DAMAGE_CONTACT  T One -> CT One       CT 58.4% | T 41.6%
           Better: Reset behind cover before re-engaging.
```

The probability is the closest global CT/T timeline estimate at or before the
event tick. A `Better:` line is emitted for major events when the coach returns
a modeled alternative. Input source, fallback, and model warnings go to
standard error so they do not pollute the event output.

## Exit behavior

The command exits `0` after the complete API flow returns a result. It exits
`1` when both input paths fail, preparation times out, no eligible decision is
found, or an API request fails.

The bundled JSON is a sanitized smoke fixture, not a legal CS2 demo. Native
`.dem` parsing still depends on the optional extractor environment and a
legally cleared sample.

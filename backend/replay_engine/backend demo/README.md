# RE:DECIDE backend demo

This is the first runnable backend demo for RE:DECIDE. It drives the actual
FastAPI application in-process, so the demo exercises the same route and
orchestration boundaries used by a frontend.

## Run

From the repository root:

```powershell
uv run --extra test python "backend/replay_engine/backend demo/cli.py"
```

The `test` extra supplies the HTTP client used to call the ASGI application.
The demo does not start a second web server; `httpx.ASGITransport` sends real
HTTP requests directly to the FastAPI app.

## Request flow

The command performs this sequence automatically:

```text
native .dem input
  -> Replay FastAPI POST /api/replay/upload
  -> receive replay_id and player manifest
  -> Coaching FastAPI POST /api/analysis/prepare {replay_id}
  -> poll GET /api/analysis/{id} until players_available
  -> GET /api/analysis/{id}/players
  -> choose a player
  -> POST /api/analysis/{id}/run
  -> GET /api/analysis/{id}/events
  -> GET /api/analysis/{id}/result
  -> Replay FastAPI GET /api/replay/{replay_id}/json
  -> verify full visualization JSON was received

normalized JSON compatibility input
  -> GET /api/health
  -> POST /api/analysis/prepare
  -> poll GET /api/analysis/{id} until players_available
  -> GET /api/analysis/{id}/players
  -> choose first player with a decision candidate
  -> POST /api/analysis/{id}/run
  -> GET /api/analysis/{id}/events
  -> GET /api/analysis/{id}/result
```

Preparation runs through `AnalysisService`, the replay pipeline, progress
logging, player indexing, probability estimation, and the configured coach
adapter. The default FastAPI service launches the real Pi agent through
`agent-harness` with the already-selected, anonymized decision payload. The
demo contains no private coach integration of its own.

## Input selection

The replay source is selected automatically. Once preparation returns the
player selector, the demo prompts you to choose one of the eligible players.
Pass `--player-id` to run without that prompt.

- `--demo PATH` explicitly supplies a native `.dem` input.
- Without `--demo`, the first `.dem`/`.demo` under `data/samples/` or this
  folder is tried.
- If native extraction fails, `--json PATH` is used.
- Without `--json`, the first normalized record from
  `data/private/processed/full_replays.jsonl` is used.

Examples:

```powershell
uv run --extra test python "backend/replay_engine/backend demo/cli.py" --demo data/samples/match.dem
uv run --extra test python "backend/replay_engine/backend demo/cli.py" --json data/private/processed/full_replays.jsonl
uv run --extra test python "backend/replay_engine/backend demo/cli.py" --player-id t1
```

## Output

Standard output contains only key event rows:

```text
0002.56  FIRST_DAMAGE_CONTACT  T One -> CT One       CT 58.4% | T 41.6%
           Better: Reset behind cover before re-engaging.
```

After the coaching result is complete, the CLI also prints the eventual replay
winner and round score, for example:

```text
Eventual winner: T (12-16)
```

For a native `.dem`, it also prints:

```text
Full visualization JSON received: true
```

This confirms that the frontend's full split artifact was returned only after
the coaching request completed. The JSON compatibility path does not use the
Replay API upload route and therefore does not print this native-artifact check.

This is post-match metadata from the final API result. It is not sent to Pi or
used to generate the coaching recommendation.

The probability is the closest global CT/T timeline estimate at or before the
event tick. A `Better:` line is emitted for major events when the coach returns
a modeled alternative. Input source, fallback, and model warnings go to
standard error so they do not pollute the event output.

## Exit behavior

The command exits `0` after the complete API flow returns a result. It exits
`1` when both input paths fail, FastAPI reports a preparation failure, no
eligible decision is found, or an API request fails. Replay preparation has no
fixed CLI deadline because native extraction and full-model inference can take
longer than ten seconds; press `Ctrl+C` to stop it manually.

The default JSONL and raw demos are real local replay data and may be private;
do not commit or publish them. Native `.dem` parsing still depends on the
optional extractor environment. Pi also requires the `agent-harness` Node
dependencies and its configured provider credentials/authentication. The
FastAPI Pi adapter automatically points each agent process at the repository
root `.env`; an existing `HARNESS_ENV_FILE` or deployment environment still
takes precedence. `pnpm install` is a setup step only; FastAPI launches the
installed TypeScript entrypoint directly with Node so package-manager install
or build-policy checks cannot interrupt a coaching request.

## Troubleshooting

- `Preparing replay through FastAPI` is not a timeout. The CLI polls the job
  status until FastAPI reports either `players_available: true` or `failed`.
- A coaching `503` means preparation and player selection succeeded but the Pi
  stage failed. The adapter accepts strict JSON and the narrow unquoted object
  form returned by some OpenAI-compatible providers, then normalizes it before
  calling `merge_pi_output`. Safe adapter failures now appear in the HTTP error
  detail instead of being collapsed into an unexplained generic 503.
- Provider settings are read from the process environment first and the
  repository-root `.env` second. The expected local variables are
  `DEEPSEEK_API_KEY`, `HARNESS_MODEL`, and `HARNESS_MODEL_BASE_URL`; optional
  overrides include `HARNESS_MODEL_PROVIDER`, `HARNESS_MODEL_API`, and
  `HARNESS_ENV_FILE`.
- Per-job progress is recorded under
  `data/runtime/analysis-logs/<analysis_id>.jsonl`. Logs contain safe stage
  messages, not provider keys, prompts, or raw provider responses.

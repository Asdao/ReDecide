# Getting started

`agent-harness` is a local TypeScript boundary around the Pi coding-agent SDK and the CS2 Python simulator. Pi handles model orchestration and streaming; this package decides which tools and skills may be exposed and executes simulator calls through a bounded process boundary.

## Prerequisites

- Node.js 20 or newer
- Python 3.12 or newer
- `pnpm`
- Model-provider credentials only when running the model-backed CLI. The bridge and automated tests run offline.

Install and verify the package from this directory:

```powershell
pnpm install
pnpm build
pnpm test
```

Run the CLI with an explicit prompt:

```powershell
pnpm dev -- --prompt "Run seed 7 for the example scenario with the baseline policy"
```

The CLI defaults to `src/cs2_sim/agent_bridge.py`, Python executable `python`, in-memory sessions, and the read-only `simulate_round` tool.

The bridge is intentionally separate from the domain facades. For direct Python
integration, use [`../../docs/MODULE_API.md`](../../docs/MODULE_API.md) and call
`cs2_sim.ReplayModel`, `replay_extractor.ReplayExtractor`, or
`training.TrainingPipeline` from their package roots.

## CLI options

| Option | Purpose |
| --- | --- |
| `--prompt <text>` | Prompt sent to the Pi session. |
| `--cwd <path>` | Working directory used by the session and bridge. |
| `--bridge <path>` | Python bridge script; defaults to `src/cs2_sim/agent_bridge.py`. |
| `--python <path>` | Python executable; defaults to `python`. |
| `--tool <name>` | Explicitly enabled tool; defaults to `simulate_round`. |
| `--skill-dir <path>` | Directory containing reviewed `SKILL.md` files; may be repeated. |

The same values can be supplied through `HARNESS_CWD`, `HARNESS_BRIDGE`, and `HARNESS_PYTHON` when integrating the CLI into a wrapper. Command-line values take precedence.

## Model and API configuration

The CLI loads `.env` from the package/current working directory for local development. Existing deployment environment variables are never overwritten. Copy [`.env.example`](../.env.example) and set a provider key:

```dotenv
DEEPSEEK_API_KEY=replace-with-a-secret
HARNESS_MODEL_PROVIDER=deepseek
HARNESS_MODEL=deepseek-v4-pro
HARNESS_MODEL_BASE_URL=https://api.deepseek.com
```

Pi already includes a DeepSeek provider, so this selects the model and can redirect requests through an OpenAI-compatible gateway by changing `HARNESS_MODEL_BASE_URL`. `HARNESS_MODEL_API_KEY` overrides `DEEPSEEK_API_KEY` when a deployment uses a different secret name. `HARNESS_ENV_FILE` can point to an explicit env file. Do not put secrets in source control; production webapps should inject them through the hosting platform's secret manager.

For a different built-in Pi provider, set `HARNESS_MODEL_PROVIDER`, `HARNESS_MODEL`, and optionally `HARNESS_MODEL_BASE_URL`. The provider and model must exist in the installed Pi catalog. The harness creates an in-memory `ModelRuntime` and explicitly selects the configured model, so it does not depend on a user's interactive Pi settings files.

Codex is also a supported provider. For a local CLI using Pi's existing Codex authentication, select it explicitly without putting an API key in `.env`:

```dotenv
HARNESS_MODEL_PROVIDER=openai-codex
HARNESS_MODEL=gpt-5.5
```

If neither `DEEPSEEK_API_KEY` nor any `HARNESS_MODEL_*` override is set, the harness preserves Pi's normal provider/model selection, so existing Codex configuration continues to work. A future multi-user webapp should keep each user's authorization on the server; never send Codex credentials to browser JavaScript.

DeepSeek's official OpenAI-compatible endpoint is `https://api.deepseek.com`; check its current model catalog before pinning a model in production: [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing).

## Calling the bridge directly

The bridge accepts one JSON request on stdin and emits one JSON response on stdout. From the repository root:

```powershell
@'{"version":1,"operation":"simulate_round","arguments":{"seed":7,"scenario":"example","policy":"baseline","max_events":3}}'@ |
  python agent-harness\src\cs2_sim\agent_bridge.py
```

The response is a versioned envelope. A successful response contains `data` with the winner, event count, bounded key events, and final state; a failed response contains a stable `error.code` and safe message. See [Tool protocol](TOOLS.md) for the complete contract.

The planned demo-to-analysis workflow is documented in [Analysis pipeline](ANALYSIS_PIPELINE.md). It is intentionally separate from the current `simulate_round` tool until replay storage, death/loss events, and deterministic scoring are implemented.

## Development notes

`pnpm build` writes compiled files to `dist/`, and `pnpm dev` runs the TypeScript entrypoint through `tsx`. Generated files, local audit output, sessions, and credentials are intentionally ignored by git. The package does not create or persist Pi sessions unless an embedding application explicitly selects persisted session mode.

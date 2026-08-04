# CS2 agent harness

This package is a small policy-first TypeScript boundary around the Pi SDK. Pi
owns model orchestration and streaming; the harness owns the explicit tool
registry, approval policy, audit events, and a process-per-call JSON bridge to
the Python simulator.

## Quick start

```powershell
pnpm install
pnpm build
pnpm test
pnpm dev -- --prompt "Run seed 7 for the example scenario with the baseline policy"
```

The CLI defaults to `src/cs2_sim/agent_bridge.py` inside this folder, uses the
`simulate_round` by default, and disables Pi built-in shell/filesystem tools.
Use `--replay <path>` to enable the outcome-blind `analyze_replay` pipeline,
which indexes first-damage decisions for every player and returns bounded
win-estimator points.
Override paths with `--bridge`, `--cwd`, `--python`, and `--skill-dir`.

The bridge is a transport boundary, not the Python domain API. Python callers
should use the package-root facades documented in
[`../backend/replay_engine/docs/MODULE_API.md`](../backend/replay_engine/docs/MODULE_API.md); the harness invokes only the
bounded bridge contract.

Model selection and credentials can be supplied through environment variables
or a local `.env` file. See [Getting started](docs/GETTING_STARTED.md) and
[`.env.example`](.env.example). The CLI never prints API keys.

When the harness is launched by the repository's FastAPI service, the server
passes its configured dotenv path through `HARNESS_ENV_FILE` for each Pi
request. Deployment environment variables and an explicit `HARNESS_ENV_FILE`
take precedence over the repository-root fallback. The browser never receives
provider credentials or the raw replay path.

The Pi SDK dependency is loaded by `session.ts`; offline tests cover policy,
validation, result bounds, and the bridge protocol without model credentials.
No credentials, sessions, or audit logs belong in this directory's source.

## Documentation

- [Getting started](docs/GETTING_STARTED.md) — install, run, configure, and use the CLI or bridge directly.
- [Architecture](docs/ARCHITECTURE.md) — runtime flow, ownership boundaries, and lifecycle.
- [Tool protocol](docs/TOOLS.md) — `simulate_round` inputs, envelopes, limits, and errors.
- [Analysis pipeline](docs/ANALYSIS_PIPELINE.md) — demo-to-timeline workflow, target contracts, and webapp usage.
- [Skills](docs/SKILLS.md) — how reviewed `SKILL.md` instructions are discovered and loaded.
- [Security](docs/SECURITY.md) — threat model, controls, and production hardening checklist.

## Security boundary

Unknown tool names are denied before dispatch. Every Python call uses an
explicit executable and script path with `shell: false`, bounded output, a
timeout, and cancellation cleanup. The bridge accepts a fixed operation table
and returns versioned JSON envelopes; stderr is never sent to the model.

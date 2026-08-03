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
`simulate_round` tool only, and disables Pi built-in shell/filesystem tools.
Override paths with `--bridge`, `--cwd`, `--python`, and `--skill-dir`.

Model selection and credentials can be supplied through environment variables
or a local `.env` file. See [Getting started](docs/GETTING_STARTED.md) and
[`.env.example`](.env.example). The CLI never prints API keys.

The Pi SDK dependency is loaded by `session.ts`; offline tests cover policy,
validation, result bounds, and the bridge protocol without model credentials.
No credentials, sessions, or audit logs belong in this directory's source.

## Documentation

- [Getting started](docs/GETTING_STARTED.md) — install, run, configure, and use the CLI or bridge directly.
- [Architecture](docs/ARCHITECTURE.md) — runtime flow, ownership boundaries, and lifecycle.
- [Tool protocol](docs/TOOLS.md) — `simulate_round` inputs, envelopes, limits, and errors.
- [Skills](docs/SKILLS.md) — how reviewed `SKILL.md` instructions are discovered and loaded.
- [Security](docs/SECURITY.md) — threat model, controls, and production hardening checklist.

## Security boundary

Unknown tool names are denied before dispatch. Every Python call uses an
explicit executable and script path with `shell: false`, bounded output, a
timeout, and cancellation cleanup. The bridge accepts a fixed operation table
and returns versioned JSON envelopes; stderr is never sent to the model.

# Architecture

## Runtime flow

```text
User prompt
    │
    ▼
Pi AgentSession ── reviewed skill catalog
    │ model requests an approved tool
    ▼
ToolRegistry / policy ── allowlist, call limits, approval, audit
    │
    ▼
TypeScript adapter ── TypeBox shape + semantic validation
    │ process-per-call JSON (shell disabled)
    ▼
Python bridge ── versioned envelope + operation table
    │
    ▼
CS2 simulator ── deterministic seeded result
    │ bounded JSON result
    └──────────────► Pi session / final response
```

## Ownership boundaries

| Component | Owns | Does not own |
| --- | --- | --- |
| Pi SDK | Model session, streaming, prompt assembly, turn events | Which external programs can run |
| TypeScript harness | Explicit tool registry, policy decisions, schemas, semantic checks, audit events, timeouts, cancellation, result bounds | Simulator rules or model credentials |
| Python bridge | JSON protocol, operation dispatch, simulator import, stable errors, output serialization | Arbitrary Python execution |
| Simulator | CS2 state transitions, policies, events, deterministic outcomes | Tool authorization or prompt interpretation |
| Skills | Reviewed instructions that guide tool use and explanation | Executable code or extra permissions |

## Model configuration

At process startup the CLI loads deployment-safe environment variables, then optionally creates an in-memory Pi `ModelRuntime`. `HARNESS_MODEL_PROVIDER` and `HARNESS_MODEL` select a built-in provider/model; `HARNESS_MODEL_BASE_URL` overlays a compatible gateway; and `HARNESS_MODEL_API_KEY` supplies a runtime-only credential. `DEEPSEEK_API_KEY` is a convenience default for the built-in `deepseek` provider. The key is never logged or sent to the tool bridge.

## Defaults and limits

- Built-in Pi tools are disabled (`noTools: "builtin"`); only explicitly registered custom tools are available.
- The default allowlist contains `simulate_round`.
- A session allows at most 8 tool calls per model turn; `simulate_round` allows at most 4.
- Tool calls time out after 30 seconds by default.
- A tool result is capped at 64 KiB; bridge stdout is capped at 256 KiB.
- `max_events` is bounded to 1–100, and the bridge request is bounded to 64 KiB.
- Sessions are in memory by default. Persisted mode is an explicit embedding choice.

These are defense-in-depth limits, not substitutes for operating-system isolation.

## Request lifecycle

1. `createHarnessSession` creates a correlation ID, bridge, policy registry, reviewed skill catalog, and Pi resource loader.
2. Pi receives the prompt and may request an exposed custom tool.
3. The registry checks name, allowlist, call counts, approval, and side-effect policy before dispatch.
4. The adapter validates arguments, writes audit events, and invokes one Python process with an explicit executable and script path.
5. Timeout or abort terminates the child; stdout is parsed as exactly one versioned envelope and bounded before returning to Pi.
6. The embedding application calls `dispose()` to emit the request-finished event and release the session.

## Current versus planned adapters

| Tool | Status | Notes |
| --- | --- | --- |
| `simulate_round` | Enabled | Fully validated and backed by the Python bridge. |
| `inspect_legal_actions` | Scaffolded | TypeScript adapter shape exists, but it is not registered or exposed. |
| `compare_policies` | Scaffolded | TypeScript adapter shape exists, but it is not registered or exposed. |

Keep future adapters unexposed until their Python operation, validation, limits, tests, and documentation are complete.

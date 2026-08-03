# Architecture

## Core model

Treat tools and skills as different things:

- A **tool** is executable code with a name, description, input schema, result,
  timeout, and side-effect classification.
- A **skill** is trusted, versioned guidance that tells the model when and how
  to combine tools. It may reference helper files, but it is not itself a tool
  invocation.

The runtime flow is:

```text
user request
    |
    v
Pi AgentSession + system policy + skill catalog
    |
    v
model response ---- final text ----------------------> caller
    |
    `---- tool call
              |
              v
       policy/approval gate
              |
              v
       TypeScript tool adapter
              |
              v
       validated JSON boundary
              |
              v
       Python CS2 simulator
              |
              v
       bounded structured result + audit event
              |
              `-------------------------------> model
```

## Components

### 1. Session factory

Create one function that constructs `AgentSession`. It should receive all
environment-specific dependencies rather than reading globals throughout the
code:

```ts
type HarnessConfig = {
  cwd: string;
  skillDirs: string[];
  allowedTools: string[];
  sessionMode: "memory" | "persisted";
  maxToolCallsPerTurn: number;
  toolTimeoutMs: number;
};
```

Initial defaults:

- in-memory session;
- no Pi `bash`, `write`, or `edit` tools;
- only explicitly registered CS2 tools;
- fixed model supplied by configuration;
- one request processed at a time;
- maximum 8 tool calls per user turn;
- 30-second timeout per simulator call.

Pi's SDK supports selecting built-in tools or disabling them while retaining
custom tools. Use that capability to start with no general-purpose shell or
filesystem mutation access.

### 2. Tool registry

Do not dynamically turn every Python function into a model tool. Maintain an
explicit registry whose entries include:

```ts
type ToolMetadata = {
  name: string;
  effect: "read" | "write" | "external";
  approval: "never" | "always" | "policy";
  timeoutMs: number;
  maxResultBytes: number;
};
```

Each tool adapter must:

1. Validate model arguments with a TypeBox schema.
2. Enforce semantic limits, such as seed ranges and maximum simulations.
3. Call only one named Python bridge operation.
4. Parse and validate the returned envelope.
5. Truncate or summarize oversized results deterministically.
6. Return errors as structured tool results, not raw stack traces.
7. Emit an audit event with secrets and large payloads removed.

Recommended first tools:

| Tool | Effect | Purpose |
|---|---|---|
| `simulate_round` | read | Run one deterministic scenario and return summary plus key events. |
| `inspect_legal_actions` | read | Show legal actions for one player in a supplied state. |
| `compare_policies` | read | Run a bounded seeded batch and compare aggregate metrics. |

Although simulation consumes CPU, it is classified as read because it does not
persist or externally publish state.

### 3. Python bridge

Use a narrow JSON-in/JSON-out command first. Example request:

```json
{
  "version": 1,
  "operation": "simulate_round",
  "arguments": {
    "seed": 7,
    "scenario": "example",
    "policy": "baseline"
  }
}
```

Example success envelope:

```json
{
  "version": 1,
  "ok": true,
  "data": {
    "winner": "CT",
    "duration_seconds": 42.25,
    "event_count": 18,
    "key_events": []
  }
}
```

Example failure envelope:

```json
{
  "version": 1,
  "ok": false,
  "error": {
    "code": "INVALID_SCENARIO",
    "message": "Unknown scenario"
  }
}
```

Rules for the bridge:

- JSON only on stdout; logs go to stderr.
- No Python object serialization such as pickle.
- Validate operation names against a fixed dispatch table.
- Reject unknown fields when practical.
- Return stable error codes.
- Cap batch sizes and event counts.
- Make results deterministic for the same versioned input and seed.

A process-per-call bridge is easiest to test and isolate. Replace it with a
long-lived local service only if profiling shows startup overhead matters.

### 4. Skills

Use standard `SKILL.md` packages with concise frontmatter and progressive
disclosure. A first skill could look like:

```markdown
---
name: analyze-cs2-round
description: Runs and explains a seeded CS2 simulation. Use for tactical round analysis, legal-action explanations, or policy comparisons.
---

# Analyze a CS2 round

1. Ask for a seed only when reproducibility matters and none was supplied.
2. Use `simulate_round` for one scenario.
3. Base claims on returned events; do not invent hidden state.
4. Distinguish simulator behavior from real professional CS2 advice.
```

Skill controls:

- Review all skill content before enabling it.
- Pin skills in source control.
- Do not put secrets, tokens, or credentials in skill files.
- Treat referenced scripts as executable dependencies requiring review.
- Test skill activation and tool choice with representative prompts.

Pi scans names and descriptions first and loads full skill content on demand.
Descriptions therefore need clear trigger conditions. The harness should also
allow a caller to force a known skill for deterministic workflows.

### 5. Policy and approvals

The policy layer remains application-owned even when Pi runs the loop.

Initial policy:

- Deny unknown tools.
- Allow the three read-only CS2 tools without approval.
- Deny arbitrary commands and arbitrary file paths.
- Require explicit user approval before future write or external tools.
- Enforce per-turn call and cumulative CPU/time budgets.
- Cancel child processes on timeout or caller abort.
- Never pass API keys through tool arguments or tool results.

Pi's project trust is a resource-loading decision, not a sandbox. Pi runs with
the permissions of its process, so production use must add operating-system or
container isolation. On Windows development, a dedicated low-privilege process
or Docker is more meaningful than relying on prompts alone.

### 6. Observability

Record one JSON event per significant transition:

- request started/finished;
- selected model and skill names;
- tool requested/allowed/denied;
- tool duration and result status;
- input/output sizes, not full sensitive payloads;
- token and cost data when exposed;
- timeout, cancellation, and schema error.

Use a correlation ID per user request and a unique call ID per tool execution.
Logs should support replaying the bridge inputs without storing model secrets.

## Testing strategy

### Contract tests

- Every tool schema accepts documented examples and rejects malformed inputs.
- TypeScript and Python agree on request and response versions.
- Unknown operations and fields fail closed.
- Error envelopes never expose tracebacks to the model.

### Unit tests

- Policy decisions for every effect/approval combination.
- Result truncation at byte and event limits.
- Timeout and cancellation cleanup.
- Skill discovery, collision, and missing-description behavior.

### Integration tests

- Use a deterministic/fake model that emits a known tool call.
- Verify model call -> policy -> adapter -> Python -> tool result -> final text.
- Verify a denied tool never reaches Python.
- Verify the same seeded request yields the same simulator result.

### Evaluation tests

Create a small prompt suite and score:

- correct tool selection;
- correct arguments;
- no tool use when unnecessary;
- grounded final answer;
- tool-call count and latency;
- compliance with unavailable/denied operations.

Do not make live, paid model calls part of the default test suite.

## Portability boundary

To keep migration possible:

- Domain operations live in Python and know nothing about Pi.
- Schemas use JSON-compatible types.
- Skills follow the Agent Skills layout.
- Policy rules are plain data plus pure functions.
- Audit events use an application-owned schema.
- Pi-specific code stays inside `session.ts` and tool registration adapters.

If Pi is replaced later, the new harness should only need to implement session
orchestration and adapt the same tool registry.


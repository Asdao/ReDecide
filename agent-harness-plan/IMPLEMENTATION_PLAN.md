# Implementation Plan

## Scope

Build a local, single-agent proof of concept that can load project skills and
call safe CS2 simulator tools. It does not need a browser UI, multi-agent
coordination, remote deployment, write-capable tools, or arbitrary shell access.

The planned proof of concept is implemented in `agent-harness/`. Its Python
bridge discovers the simulator under `model/src/cs2_sim`; direct Python domain
callers use the package-root facades documented in `docs/MODULE_API.md`.

## Phase 0: Decision checks

Before implementation, confirm:

- Node.js can be included alongside the Python 3.12 runtime.
- Pi's license and dependency tree are acceptable.
- The first caller is a CLI or programmatic API, not an HTTP service.
- Model authentication will be supplied at runtime and never committed.

Exit criterion: no requirement forces a Python-only/manual runtime.

## Phase 1: Prove Pi in isolation

`agent-harness/` is its own TypeScript package.

Tasks:

1. Install and pin `@earendil-works/pi-coding-agent`.
2. Construct an in-memory `AgentSession` with built-in tools disabled.
3. Add one inline `echo_fixture` tool with a strict schema.
4. Stream assistant text and tool lifecycle events to the CLI.
5. Add a fake-model integration test so tests do not require credentials.

Exit criteria:

- One prompt triggers the fixture tool and receives its result.
- Unknown tools cannot run.
- Ctrl+C/abort stops the turn cleanly.
- The test suite runs without network access or an API key.

Estimated effort: half a day.

## Phase 2: Add the Python domain boundary

Tasks:

1. `src/cs2_sim/agent_bridge.py` provides a fixed operation dispatch table.
2. Implement `simulate_round` using the existing `Simulator`, `SimConfig`, and
   policy classes.
3. Define versioned request, success, and error envelopes.
4. Add Python tests for malformed JSON, unknown operations, deterministic seed
   behavior, output limits, and internal exceptions.
5. Add a TypeScript process adapter with timeout, abort, stderr capture, and
   response validation.

Exit criteria:

- A standalone bridge call returns valid JSON and no log text on stdout.
- The same seed produces the same result.
- Invalid input returns a stable error envelope and non-sensitive message.
- A killed or timed-out process leaves no child process running.

Estimated effort: one day.

## Phase 3: Register real tools

Tasks:

1. Replace `echo_fixture` with `simulate_round`.
2. Add the central tool metadata registry and default-deny policy.
3. Enforce argument, batch, time, and result-size limits.
4. Add structured audit events.
5. Add `inspect_legal_actions` only after the first tool is stable.

Exit criteria:

- The model can complete the minimal round-analysis use case.
- Every tool call has a correlation ID, duration, and allow/deny result.
- General shell/filesystem tools are absent from the model's tool list.
- Tool failures are recoverable and understandable to the model.

Estimated effort: one day.

## Phase 4: Add skills

Tasks:

1. Create `analyze-cs2-round/SKILL.md`.
2. Configure the resource loader to use the harness skill directory explicitly.
3. Add a validation check for skill frontmatter and duplicate names.
4. Test automatic activation prompts and an explicit/forced skill path.
5. Add a second skill only if it changes behavior meaningfully.

Exit criteria:

- The correct skill is available without placing its entire body in every
  prompt.
- The agent grounds explanations in returned simulator events.
- An unrelated prompt does not cause unnecessary simulator calls.
- A malformed or duplicate skill fails startup in this application, even if
  Pi itself would only warn.

Estimated effort: half a day.

## Phase 5: Reliability and evaluation

Tasks:

1. Create 15-25 fixed evaluation prompts covering direct answers, one tool,
   multiple tools, malformed requests, and denied operations.
2. Capture tool choice, arguments, call count, result status, latency, and final
   grounding.
3. Add maximum calls per turn and total wall-clock budget.
4. Test cancellation during both model streaming and Python execution.
5. Document supported model/provider combinations.

Exit criteria:

- At least 90% of in-scope prompts select the expected tool or no-tool path.
- No denied tool reaches the dispatcher.
- All outputs in the evaluation set are supported by tool results.
- One failing request cannot corrupt the next in-memory session.

Estimated effort: one to two days.

## Phase 6: Decide whether to productize

Only after the proof of concept, choose the deployment shape:

| Need | Next step |
|---|---|
| Local developer assistant | Keep Pi CLI/SDK and persisted local sessions. |
| Web or desktop product | Embed the SDK behind an application service and define tenant isolation. |
| Untrusted code execution | Move tool execution into a container or policy sandbox. |
| High-throughput service | Replace process-per-call bridge with a supervised Python service. |
| Python-only deployment | Reassess a manual loop or a Python-native runtime using the same contracts. |

Do not add persistence, queues, a database, or a web API before a concrete
caller needs them.

## Manual-harness fallback plan

If Phase 0 rules out Pi, the minimum manual loop must still implement:

1. provider adapter and streaming;
2. message and tool-call state machine;
3. JSON Schema validation;
4. tool dispatch, timeouts, cancellation, and result limits;
5. skill catalog discovery and progressive loading;
6. session persistence and schema versioning;
7. context/token budgeting and compaction;
8. policy/approval hooks;
9. structured audit events;
10. deterministic fake-provider tests.

Estimate this separately. A credible manual prototype is likely several days;
a hardened multi-provider harness is a continuing subsystem, not a small
utility.

## Definition of done for the proof of concept

- A clean checkout can install the TypeScript package and run its offline tests.
- One documented command starts the harness.
- A seeded CS2 request invokes only approved tools and returns a grounded answer.
- Skills are discovered from a reviewed, version-controlled directory.
- Tool inputs and Python responses are validated on both sides.
- Timeouts, cancellation, and output bounds are tested.
- No secrets, sessions, or generated audit logs are committed.
- Architecture and migration boundaries match `ARCHITECTURE.md`.

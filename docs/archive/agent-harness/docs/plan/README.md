# Agent Harness Plan

## Decision

Use the **Pi SDK as the agent runtime**, and implement this project's domain
tools manually as a small Python bridge.

Do not build the complete agent loop from scratch. Pi already provides the
parts that are easy to underestimate: model/provider integration, iterative
tool calling, streaming events, session state, compaction, skill discovery,
and extension hooks. The project should own only the parts that are specific to
the CS2 simulator: tool schemas, validation, permissions, Python execution, and
domain skills.

This is a hybrid decision rather than a lock-in to Pi at every layer:

- Pi owns orchestration.
- TypeScript adapters register safe tools with Pi.
- Python remains the source of truth for simulation and model behavior.
- Skills follow the portable Agent Skills `SKILL.md` convention.
- Tool contracts and domain services remain independent enough to move to a
  different harness later.

## Why Pi fits

The requested harness needs both tools and skills, which map directly to Pi's
two extension points:

- The SDK accepts custom tools and exposes session and streaming events.
- The resource loader discovers skills and makes their short descriptions
  available before loading full instructions on demand.
- Extensions can intercept tool calls, add approval gates, and record audit
  information.
- In-memory sessions work for tests; persisted sessions can be enabled later.

The current repository is Python. Pi's SDK is TypeScript, so the clean boundary
is a small TypeScript package that calls a narrow Python command/API. Rewriting
the simulator in TypeScript would create unnecessary risk.

## When a manual harness would be better

Build the loop manually only if at least one of these becomes a hard
requirement:

- The deployed runtime must be Python-only with no Node.js process.
- The product needs a protocol or execution model Pi cannot expose.
- Every persisted event must use a pre-existing proprietary schema.
- Dependency review rejects Pi or its transitive dependencies.
- The goal is specifically to learn how agent loops work, not ship a reliable
  harness quickly.

If none applies, a manual implementation would mostly reproduce solved
infrastructure while leaving less time for useful tools and evaluation.

## Implemented deliverable

The sibling implementation is now present and keeps the simulator in
`model/src/cs2_sim` while providing a narrow Python bridge:

```text
agent-harness/
|-- package.json
|-- tsconfig.json
|-- src/
|   |-- main.ts                 # CLI or service entry point
|   |-- session.ts              # Pi session construction
|   |-- policy.ts               # tool allowlists and approval rules
|   |-- audit.ts                # structured tool-call event log
|   `-- tools/
|       |-- simulate-round.ts
|       |-- inspect-state.ts
|       `-- compare-policies.ts
|-- skills/
|   |-- analyze-round/
|   |   `-- SKILL.md
|   `-- compare-policies/
|       `-- SKILL.md
|-- tests/
|   |-- tool-contracts.test.ts
|   |-- policy.test.ts
|   `-- smoke.test.ts
`-- README.md

src/cs2_sim/agent_bridge.py  # JSON-in/JSON-out Python boundary
tests/test_agent_bridge.py
```

Keep skills under `agent-harness/skills/` in source control and pass that
directory explicitly to Pi's resource loader. If compatibility with multiple
harnesses is more important, use a repository-level `.agents/skills/` instead.

## Minimal first use case

The first vertical slice should answer one bounded request:

> Run a seeded round, summarize the important events, and explain why the
> chosen policy acted as it did.

It requires only one read-only domain tool, one skill, and an in-memory session.
It proves the whole loop without granting shell access or introducing a web UI.

## Documents in this folder

- [ARCHITECTURE.md](ARCHITECTURE.md) defines runtime boundaries, tool and skill
  contracts, security, and testing.
- [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) breaks the work into small
  milestones with acceptance criteria.

## Verified references

- [Pi SDK](https://pi.dev/docs/latest/sdk)
- [Pi custom tools and extensions](https://pi.dev/docs/latest/extensions)
- [Pi skills](https://pi.dev/docs/latest/skills)
- [Pi security model](https://pi.dev/docs/latest/security)
- [Pi containerization options](https://pi.dev/docs/latest/containerization)

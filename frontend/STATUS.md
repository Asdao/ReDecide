# Frontend Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 4 - Frontend Product Experience

## Status

**Not implemented.**

`frontend/` currently has no application scaffold, typed API client, screens,
components, fixtures, or frontend tests.

## Required experience

1. Choose bundled sample or upload `.dem`.
2. Show truthful analysis progress.
3. Collect intent before judgement.
4. Display one evidence-linked Decision Card and practice quest.

The knowledge-boundary timeline must distinguish known evidence, decision open,
observed action, and future hidden from the coach.

## Important path

```text
frontend/**
```

## API dependency

Consume only the four endpoints and frozen schemas maintained by Person 1. Use
a typed fixture adapter until the live parser/model path is available. Do not
use `any` at the API boundary or invent missing facts in the browser.

## Tests and validation

No frontend tests exist yet.

Required states include normal, risky, insufficient evidence, loading, timeout,
parser error, model failure, no eligible decision, fallback fixture, keyboard
focus, and demo-resolution layout.

## Known limitations and blockers

- No frontend framework has been scaffolded in this path.
- No frozen TypeScript contract or checked-in Decision Card fixture is present.
- No backend endpoint is available for integration.

## Contract/API impact

None implemented. Report mismatches to Person 1 rather than changing the shared
contract locally.

## Next handoff

After the fixture contract is available, render the four-screen flow from typed
fixtures and prove evidence expansion plus the knowledge-boundary visual.

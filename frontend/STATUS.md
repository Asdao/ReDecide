# Frontend Status

Last verified: 2026-08-04 (Asia/Singapore)

Owner: Person 4 - Frontend Product Experience

Branch: `04/frontend`

## Status

**Saved-example landing and progress slice implemented; live/sample analysis is not integrated.**

The standalone Next.js frontend now has a dark, responsive landing screen,
outcome-blind product copy, privacy-safe copy, and a semantic preview of the
knowledge boundary. The primary sample button now explicitly opens the
checked-in saved demo packet, validates it through the shared frontend schema,
and shows the three pre-intent replay stages. The page explains that the replay
steps were completed when the example was prepared and does not claim that a
new backend analysis ran. The upload control remains disabled with a visible
explanation until the preparation API contract is resolved.

The landing page, product header, saved-example loader, screen state, and
progress screen are split into separate files. The progress screen supports a
safe invalid-fixture error, retry, reset, heading focus on screen changes, one
polite progress region, and validated map, round, and aliased-player details.
It stops before the intent checkpoint and never mounts the checked-in Decision
Card.

The checked-in visual identity uses bundled Saira for interface/branding,
Saira Condensed for display headings and prominent labels, and Noto Sans for
longer copy and language fallback. Deep charcoal (`#0C0F12`) is the background,
signature orange (`#F7941D`) marks decisions and primary interactions, muted
steel blue (`#5D79AE`) defines supporting structure, and tactical tan
(`#CCBA7C`) is reserved for uncertainty and staged-status messaging.
Interactive/card geometry uses sharp corners. Flat CSS-only diagonal bars carry
that palette behind the interface without gradients, a copied game asset, or an
external image request.

Strict Zod schemas mirror the executable version `1.0` Pydantic contracts for
`DecisionPacket`, `IntentInput`, and `DecisionCard`. They trim boundary strings,
reject extra fields, enforce numeric/enum constraints and knowledge cutoffs,
reject duplicate evidence references, and reject mismatched packet/card
`decision_id` values. A frontend-local rehearsal packet/card is parsed through
the same schema and tested for exact drift against the canonical backend
fixtures.

`INTEGRATION_STATUS.md` still describes the executable contracts and fixtures
as absent. The inspected backend code and fixtures are the current
implementation evidence; Person 1 owns that integration-status correction.

## Important paths

- `src/app/page.tsx` - minimal route entry point
- `src/app/globals.css` - restrained theme, responsive layout, focus, and
  reduced-motion defaults
- `src/components/DecisionFlow.tsx` - landing/progress screen control and saved
  example loading
- `src/components/LandingScreen.tsx` - sample and disabled-upload choices plus
  knowledge-boundary preview
- `src/components/AnalysisProgressScreen.tsx` - truthful saved-example progress,
  error, retry, reset, and packet summary
- `src/domain/analysis-flow.ts` - explicit choose/loading/ready/error states
- `src/domain/contracts.ts` - strict version `1.0` runtime schemas and inferred
  TypeScript types
- `src/adapters/saved-example.ts` - validated local packet loader
- `src/fixtures/` - deployable local rehearsal packet/card
- `tests/unit/analysis-flow.test.ts` - saved packet and state-transition tests
- `tests/unit/contracts.test.ts` - boundary, pairing, and fixture-drift tests
- `package.json` and `pnpm-lock.yaml` - pinned standalone frontend toolchain

## Inputs, outputs, and dependencies

- Input today: the validated local packet fixture. The local card remains
  unmounted.
- Output today: an interactive landing-to-progress route at `/`, explicitly
  labelled as a saved demo example.
- Runtime: Node 24, pnpm 11, Next.js 16, React 19, Zod 4, Tailwind CSS 4, and
  self-hosted Fontsource Saira/Saira Condensed/Noto Sans packages.
- Validation: strict TypeScript, ESLint, Vitest, and a production Next.js build.

## Tests and latest verification

From `frontend/`:

```text
pnpm install
pnpm peers check
pnpm run verify
```

Latest result on 2026-08-04:

- Vitest: 2 files, 9 tests passed;
- TypeScript: passed;
- ESLint: passed with no warnings;
- production build: passed; `/` and `/_not-found` prerendered.

The in-app browser verified the sample button, ready-state content, heading
focus, and return-to-start action. Browser console errors: none. Body-level
horizontal overflow was absent at `1440x900` and `1280x720`. The loading and
invalid-fixture states were not held open for a visual check because the valid
local packet loads immediately.

## Open P0 integration gates for Person 1

1. Define a preparation response that lets the frontend collect intent before
   requesting or revealing judgement.
2. Return or retrieve a validated packet together with its matching card.
3. Define uploaded-player discovery.
4. Provide structured observed-action evidence; current action evidence is
   bare IDs and cannot support expandable details.
5. Freeze the safe response for future-information or contradiction checks.
6. Freeze sample, upload, preparation, success, no-decision, and typed error
   shapes, including retry rules, content type, file-size limit, timeouts, and
   the optional intent-note limit.
7. Confirm whether global `facts_used` is the accepted claim-citation scope or
   add a coordinated structured citation contract.

Until gate 5 is resolved, the frontend must fail closed for unsafe cards by
suppressing coaching prose and verified-evidence presentation. None of these
questions is represented as a frozen browser contract.

## Known limitations

- Genuine backend sample analysis and replay upload are not implemented yet.
- The intent checkpoint and Decision Card screens are not implemented yet.
- The saved example is a development/recovery path, not proof of a genuine
  replay analysis.
- Evidence resolution, unsafe-result suppression, the remaining screen states,
  component tests, and automated browser tests remain to be implemented. The
  initial choose/loading/ready/error states and local retry are implemented;
  network timeout, cancellation, and stale-response handling are not.
- The supported-browser list and optional intent-note limit are not frozen.

## Contract/API impact

No backend or frozen contract change. The frontend consumes and mirrors the
current executable version `1.0` schemas only.

## Next handoff

Add the intent checkpoint using the validated packet's timestamp and a neutral
event summary. Collect one of the five frozen intent choices without mounting
judgement content. Person 1 should answer the P0 gates before the genuine
live/sample path is connected.

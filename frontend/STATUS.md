# Frontend Status

Last verified: 2026-08-03 (Asia/Singapore)

Owner: Person 4 - Frontend Product Experience

Branch: `04/frontend`

## Status

**Initial fixture-first slice implemented; live/sample analysis is not integrated.**

The standalone Next.js frontend now has a dark, responsive landing screen,
outcome-blind product copy, privacy-safe copy, and a semantic preview of the
knowledge boundary. Sample and upload controls are intentionally disabled with
a visible explanation until the preparation API contract is resolved; the
browser does not invent a temporary endpoint or silently use fixture output.

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

- `src/app/page.tsx` - landing screen and knowledge-boundary preview
- `src/app/globals.css` - restrained theme, responsive layout, focus, and
  reduced-motion defaults
- `src/domain/contracts.ts` - strict version `1.0` runtime schemas and inferred
  TypeScript types
- `src/fixtures/` - deployable local rehearsal packet/card
- `tests/unit/contracts.test.ts` - boundary, pairing, and fixture-drift tests
- `package.json` and `pnpm-lock.yaml` - pinned standalone frontend toolchain

## Inputs, outputs, and dependencies

- Input today: validated local packet/card fixtures only; they are not yet
  mounted into the user flow.
- Output today: a statically rendered landing route at `/`.
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

Latest result on 2026-08-03:

- dependency install completed and native builds ran;
- no peer dependency issues;
- Vitest: 1 file, 5 tests passed;
- TypeScript: passed;
- ESLint: passed with no warnings;
- production build: passed; `/` and `/_not-found` prerendered.

The in-app browser visual check could not start because the desktop browser
runtime was denied access to its local bootstrap path. No browser-level or
viewport claim is made for this slice.

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

- Sample/upload selection, progress, intent, and Decision Card screens are not
  implemented yet.
- Fixture mode is validated but not exposed in the user experience.
- Evidence resolution, unsafe-result suppression, reducer states, retry/abort,
  component tests, and browser tests remain to be implemented.
- The supported-browser list and optional intent-note limit are not frozen.

## Contract/API impact

No backend or frozen contract change. The frontend consumes and mirrors the
current executable version `1.0` schemas only.

## Next handoff

Add the typed reducer and fixture adapter, then make the sample path move from
landing through truthful pre-intent progress to the intent checkpoint without
mounting judgement content early. Person 1 should answer the P0 gates before
the live/sample adapter is connected.

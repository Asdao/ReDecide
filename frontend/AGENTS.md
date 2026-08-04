# Frontend agent instructions

These instructions apply to every file under `frontend/`. They extend the
repository-level `AGENTS.md`; when they conflict, the repository-level rules
and the numbered role briefs take precedence.

## Required context

Before implementing or changing frontend behavior, read:

1. `../AGENTS.md`
2. `../Project_Context.md`
3. `../04_FRONTEND_PRODUCT_EXPERIENCE.md`
4. `../INTEGRATION_STATUS.md`
5. `STATUS.md`
6. `../backend/app/contracts.py` and the current fixtures under
   `../backend/tests/fixtures/`

Inspect the current frontend tree, working-tree status, and diff before every
material change. Preserve user work and reuse existing frontend conventions
once they exist.

## Mission and scope

Build the complete RE:DECIDE browser experience for one outcome-blind CS2
post-contact decision. The user must be able to choose or upload a match, see
truthful analysis progress, state their intent before judgement, and inspect an
evidence-linked Decision Card plus one practice quest.

Person 4 owns `frontend/**`. Do not edit backend code, frozen contracts, root
dependency files, role briefs, or another owner's status file. Report contract
or endpoint mismatches to Person 1 instead of repairing them in the browser.

Do not add login, profiles, match history, leaderboards, social features, a
chat interface, a full VOD player, a 3D map, a live overlay, or a mobile app.

## Validated readiness and integration gates

Architecture, QA, and product/accessibility reviews rate this plan **GO WITH
CHANGES**. Fixture-first implementation may begin. Do not describe the live or
sample product as integrated until Person 1 has resolved and documented all of
these P0 gates:

1. **Intent-before-judgement flow:** the frontend needs a prepared decision and
   neutral summary before collecting intent, while the documented one-shot
   `/api/analyze` request accepts intent up front.
2. **Packet/card pairing:** the final experience needs both the validated
   `DecisionPacket` and matching `DecisionCard`, but the documented endpoint
   returns only the card. Reject a mismatched `decision_id`.
3. **Uploaded-player discovery:** player choices are not known until an upload
   is parsed, and no preparation response currently defines how they are
   returned.
4. **Structured action evidence:** version `1.0` carries complete
   `EvidenceItem` objects only for `known_before_decision`; observed-action
   evidence is currently a list of bare IDs and cannot provide expandable
   tick, source, and statement details.
5. **Unsafe result checks:** Person 1 must freeze the safe outcome when
   `future_information_detected` or `contradiction_detected` is true. Until
   agreed otherwise, fail closed: suppress coaching prose and verified-evidence
   presentation, show a neutral invalid/unverified-analysis state, and offer
   retry or an explicitly labelled example. Do not rewrite the backend verdict.
6. **Request/response details:** freeze sample, upload, preparation, success,
   no-decision, and error shapes, including HTTP status mapping, retryability,
   content type, file-size limit, and optional intent-note limit.
7. **Claim citations:** the current global `facts_used` list supports the claim
   that the card's supporting evidence is inspectable. It cannot map every
   sentence in `assessment` or `why` to an exact evidence ID. Person 1 must
   either accept that narrower requirement or coordinate a structured
   claim-citation addition.

Keep these gates visible in `STATUS.md` until the agreed contracts and a real
end-to-end sample have been verified. Frontend code may define internal ports,
errors, and view models for fixture development, but it must not present those
as frozen backend contracts.

Current status documents may lag the tree: executable Pydantic contracts and
JSON fixtures already exist even though `STATUS.md`/`../INTEGRATION_STATUS.md`
may still say otherwise. Treat inspected code as implementation evidence, note
the mismatch in the frontend handoff, update only `STATUS.md` after material
frontend work, and leave the integration-status correction to Person 1. The
working branch may also differ from the brief's `ux/decision-card` name;
coordinate rather than renaming or rewriting history automatically.

## Product invariants

- Collect intent before revealing the verdict.
- Never reveal or use later death, survival, kill, win, or round outcome while
  presenting the decision analysis.
- Display only facts provided by a validated runtime response. Never infer or
  manufacture missing CS2 facts in frontend code or copy.
- Treat `INSUFFICIENT_EVIDENCE` as a valid coaching result, not an application
  error.
- Keep unknowns and limitations readable and prominent.
- Never expose provider credentials, private replay data, or server-only
  configuration in browser bundles, logs, fixtures, or screenshots.
- Use aliases for player names in fixtures and screenshots unless consent has
  been recorded.

## Contracts and API boundary

Create one strict frontend schema source for the current version `1.0`
contracts. Prefer strict Zod schemas with inferred TypeScript types so runtime
validation and compile-time types cannot drift:

- `DecisionPacket`
- `IntentInput`
- `DecisionCard`

Do not use `any` at the API boundary. Receive network and fixture data as
`unknown`, validate it, then expose typed values to components. Keep enum
values, field names, nullability, and numeric ranges aligned with Person 1's
contract. Do not add browser-only fields to shared contract types; use separate
view-model types when the UI needs derived state. Mirror fixed schema version
`1.0`, strict extra-field rejection, recursive JSON values, optional versus
nullable fields, confidence/data-quality ranges, and Pydantic's boundary
whitespace behavior. Parse once at the adapter boundary.

Consume only the agreed endpoints:

- `GET /api/health`
- `GET /api/samples`
- `POST /api/analyze`
- `POST /api/analyze-json` for fixture or fallback integration when available

Before live integration, inspect and test the actual request, response, sample,
upload, no-decision, and error schemas. The required intent-before-judgement
flow needs an agreed two-stage backend behavior: prepare/detect the replay and
return player choices plus a packet, then submit intent and return the matching
card, or an equivalent design using the allowed endpoints. Do not invent a
permanent endpoint or silently change the shared contract to work around that
gap.

The shared API decision must specify:

- `/api/samples` response fields;
- upload field names, content type, and maximum size;
- uploaded-player discovery;
- prepared-decision response and neutral summary;
- final packet/card response envelope or retrieval mechanism;
- typed error fields/codes for parser failure, unsupported demo, no decision,
  missing provider configuration, timeout, invalid model output, future-data
  detection, and contradiction;
- which failures are retryable and whether retry can repeat a paid model call;
- separate detection and coaching timeout behavior; and
- maximum length/normalization for the optional intent note.

Handle network loss, CORS failure, non-JSON errors, malformed successful
responses, and ordinary `4xx`/`5xx` responses without rendering unvalidated
content. Decide and document whether `/api/health` blocks analysis actions or
only reports availability.

## Evidence handling

Checked-in fixtures and evidence IDs such as `E1`, `E2`, `E3`, and `E4` are
illustrative examples. Runtime `DecisionPacket` and `DecisionCard` values are
authoritative for the analyzed match.

The normal backend invariant is:

1. the replay pipeline emits the evidence records available for that match;
2. the coach includes only corresponding valid IDs in `facts_used`; and
3. deterministic backend checks reject or flag unsupported references.

The frontend must still fail safely if malformed or stale data reaches it:

- Build one evidence index keyed by `evidence_id` from the structured evidence
  records actually present in the response.
- Resolve `facts_used` and action evidence references through that index using
  exact, case-sensitive IDs. Do not trim, normalize, or guess an ID after the
  response has passed contract validation.
- Render an evidence chip or expansion only when the referenced record exists.
- Silently omit unresolved evidence references from the visible evidence list;
  continue rendering the rest of the card.
- Never create a placeholder statement, tick, source, value, or replacement ID.
- Never present an ID listed in `checks.unsupported_evidence_ids` as verified.
- Preserve valid evidence order and avoid duplicate chips.
- Keep the neutral observed-action description when it is present, even if one
  of its optional evidence expansions cannot be resolved.

For the Decision Card's supporting-evidence section, `no evidence remains`
means that zero valid, supported IDs from `DecisionCard.facts_used` resolve to
structured evidence records after filtering. Unreferenced packet facts and bare
observed-action IDs do not count as support for the card's assessment.

If at least one valid `facts_used` item remains, show the valid evidence and no
notice. If none remain, replace the empty evidence list with one visible,
neutral notice:

> Evidence details aren't available for this card. You can still review the
> coaching summary, but its supporting replay facts can't be verified here.

Place the notice inside the evidence section where the chips would otherwise
appear. Use amber/uncertainty styling rather than verified green or error red,
and use an icon plus text so color is not the only signal. If the notice appears
after asynchronous loading, announce it once as a polite status, not an urgent
alert. Do not render empty drawers or popovers.

Zero resolved frontend evidence is a stale, incomplete, or mismatched display
response; it is not the same as the backend verdict `INSUFFICIENT_EVIDENCE`.
Keep the backend verdict unchanged and keep the rest of the card usable,
including the assessment, observed-action description, options, quest,
unknowns, and limitations. Do not imply that the unavailable evidence was
verified.

Put this logic in a shared pure helper rather than repeating filtering in
components. The helper should return the resolved items in `facts_used` order,
an internal list of omitted IDs for diagnostics/tests, and whether the notice
must be shown. Do not expose omitted IDs in the UI. A malformed structured
evidence object or mismatched packet/card `decision_id` is an invalid response,
not a missing-reference case, and must use the safe invalid-response state.
Missing evidence must not crash the page or hide valid evidence that remains.
Display supplied `data_quality.warnings` as quality notes or limitations. Do
not derive a new verdict from `data_quality.score` in the browser.

## Required experience

Implement one clear flow, preferably as explicit typed application states:

1. **Choose match**
   - Lead with `Try a sample match` as the one-click primary action.
   - Offer `.dem` upload as the secondary path.
   - Show player selection when supplied by the sample or upload response.
   - Explain the difference immediately in plain language: `We judge the choice
     using only what was knowable at that moment—not whether you later won,
     died, or lost the round.`
   - State only confirmed privacy behavior. Safe default copy may say replay
     data is sent to the analysis service and provider keys remain on the
     server; do not promise deletion or retention behavior until confirmed.
2. **Analysis progress**
   - Before intent, show only `Parse replay events`, `Find a post-contact
     decision`, and `Freeze what was knowable`.
   - After intent submission, show `Compare action with stated intent` and
     `Verify evidence and limitations`.
   - Animate waiting without claiming backend stages have completed unless the
     backend confirms them.
   - Without backend stage events, show one current/waiting stage rather than
     completing stages on a timer.
   - Provide clear timeout, retry, and safe fallback behavior.
3. **Intent checkpoint**
   - Show only the decision timestamp and a neutral event summary.
   - Offer the five frozen intent tags and an optional one-sentence note.
   - Explain briefly why intent changes the assessment.
   - Do not mount verdict, judgement, later-outcome, or recommendation copy in
     the DOM before intent is submitted.
4. **Decision Card**
   - Prioritize verdict and calibrated confidence, knowledge boundary, known
     evidence, observed choice, intent-relative assessment, alternatives and
     trade-offs, practice quest, unknowns, and limitations.
   - Make each rendered evidence item expandable with its real ID, tick or
     timestamp, source, and exact statement.
   - Convert enum labels into readable language and explain confidence as
     `Confidence in this judgement, not your chance of winning.`
   - Explain unknowns as facts the replay could not capture and limitations as
     constraints on the judgement.
   - For `INSUFFICIENT_EVIDENCE`, use neutral/amber styling, foreground missing
     facts and limitations, preserve any safe evidence, and offer another
     decision or sample.

Create the knowledge-boundary timeline as a compact chronological figure:

```text
known before decision → decision moment → immediate action through close tick
                                            → everything after was hidden
```

Use the real decision and action-close time/tick values where supplied. Label
the future region `hidden from the coach` and provide the same meaning in a
text caption for screen readers. Do not rely on color, hatching, or horizontal
position alone. At narrow widths, use a stacked ordered representation instead
of horizontal scrolling or chronology-breaking wrapping. Do not reveal later
outcomes unless an explicitly approved demo-only reveal is added after the
completed card.

At `1440x900`, the first Decision Card viewport should contain the verdict,
confidence explanation, knowledge boundary, and beginning of the evidence
section. Options, quest, and limitations may continue below without shrinking
text to force everything into one screen.

## Run modes and architecture

Keep presentation components independent of the data source. Provide typed
adapters with the same frontend-facing interface for:

- `live`: uploaded replay through the real parser and coach;
- `sample`: bundled match through the real path; and
- `fixture`: checked-in deterministic data for development and recovery.

Treat `upload` and `sample` as user-selected analysis sources. They should share
one real backend adapter. Treat `fixture` as a deterministic adapter used for
development or explicit recovery, not as a second fake implementation of the
live path. A small frontend port may expose operations such as `listSamples`,
`prepareDecision`, and `submitIntent`, with backend and fixture implementations
behind it.

Select enabled/default modes through validated environment/configuration, not a
hidden production control. A public API base URL may be exposed to the browser;
keys and provider configuration may not. Never silently replace a failed real
sample or upload with fixture output. Offer an explicit action such as `Open a
demo example` and retain a visible label such as `Demo example — not generated
from your uploaded match.` The recorded submission must use the genuine sample
path.

Fixture mode must remain deployable without the backend. Coordinate whether to
keep a validated frontend-local rehearsal fixture or package a shared canonical
fixture with Person 1. Do not assume a standalone Next.js build will include
arbitrary files imported from above the frontend project root. If a local copy
is approved, validate it with the same schema and add a drift/compatibility
test. Add fixture variants for every required verdict, failure, evidence, and
fallback state; do not mutate one fixture through untyped overrides.

When scaffolding, use the stack recommended by Person 1 unless the team has
agreed otherwise: Next.js App Router, React, strict TypeScript, Tailwind, and
the repository's available `pnpm`. Keep the frontend package, lockfile,
configuration, and tests inside `frontend/`. Use small reusable components and
plain design tokens; do not build a general-purpose design system. A minimal
layout is sufficient:

```text
src/app
src/components
src/domain       # schemas, state, evidence resolution
src/adapters
src/fixtures
tests/e2e
```

Use native `fetch` plus `AbortController`. Avoid server actions, Redux, XState,
Zustand, query libraries, Storybook, a design-system package, and network-fetched
fonts unless a demonstrated requirement justifies them.

Use a small reducer with a discriminated union rather than scattered booleans:

```text
choose
  → detecting
  → intent
  → coaching
  → result | abstention
```

Detection may instead end in parser error, timeout, invalid response, or no
decision. Coaching may instead end in model failure, timeout, unsafe result, or
invalid response. Carry the source and retry context explicitly. Ignore late
responses after reset, timeout, abort, or a newer request. Prevent duplicate
submission and preserve the user's file, player, and intent when a retry is
safe. Reset must abort pending work and clear replay data and sensitive client
state.

## Visual and accessibility requirements

- Use a dark, restrained competitive-game style without copying official CS2
  branding.
- Use one warm decision accent, green only for verified evidence, amber for
  uncertainty, and red only for errors or genuinely poor decisions.
- Design desktop-first for `1440x900`; also verify `1366x768` and `1280x720`.
- Prevent horizontal overflow and clipped content.
- Meet WCAG AA contrast. Use semantic HTML, labelled controls, visible keyboard
  focus, sensible heading order, at least practical `44px` pointer targets, and
  reduced-motion support.
- Move focus to the new main heading, blocking error summary, or card title on
  meaningful screen transitions.
- Implement intent with a real `fieldset`, `legend`, and radio inputs. Label
  and describe the file input and associate validation errors with it.
- Use native `details` or buttons with `aria-expanded` and `aria-controls` for
  evidence disclosure. Restore focus correctly when closing any drawer.
- Announce progress changes sparingly through one polite live region. Do not
  repeatedly announce animations. Use `alert` only for blocking errors.
- Ensure keyboard order follows visual chronology and status/verdict meaning is
  always communicated with text or an icon, not color alone.
- Motion must explain a transition or waiting state rather than decorate it.
- Never hide limitations in small or low-contrast text.

At supported viewports and 200% zoom where feasible, verify the entire page,
expanded evidence, optional intent note, notices, and errors for overflow,
clipping, obscured focus, and unusable popovers.

## Security and privacy checks

- Only a public API base URL may use browser-public environment variables.
  Provider keys and server configuration must never enter source or bundles.
- Do not put replay contents, real player names, intent text, or omitted
  evidence IDs in console logs, analytics, URLs, or persistent browser storage.
- Do not use `dangerouslySetInnerHTML` for API/model output.
- Send raw uploads only to the configured backend. Do not add silent analytics
  or third-party upload destinations.
- Reset must clear sensitive client state and abort pending upload/analysis.
- Inspect production bundles and real network responses for secrets before the
  demo. Frontend-only checks cannot prove backend responses are clean.
- Privacy copy must match confirmed backend processing and retention behavior;
  do not make stronger promises than the implementation supports.

## Required states and tests

Implement and verify at least:

- normal successful card;
- `REASONABLE_BUT_RISKY`;
- `POOR_DECISION`;
- `INSUFFICIENT_EVIDENCE`;
- loading and truthful progress;
- parser or upload error;
- API timeout and retry;
- model failure;
- no eligible decision;
- sample failure with fixture fallback;
- malformed or partially missing evidence references;
- zero valid supporting-evidence references and its visible notice;
- unsafe future-information or contradiction checks;
- malformed success, non-JSON error, network loss, CORS, and `4xx`/`5xx`;
- keyboard-only navigation and visible focus; and
- the complete sample route at the recorded-demo resolution.

Use clear recovery behavior and non-technical copy:

- Parser/upload error: state the usable reason, then offer another `.dem` or a
  sample. Do not expose a stack trace.
- Timeout: say `Analysis is taking longer than expected`, prevent duplicate
  work, and offer retry or sample selection.
- Model failure/invalid or unsafe response: say the judgement could not be
  produced or verified, suppress unsafe prose, and offer retry.
- No eligible decision: explain that no supported post-contact reset decision
  was found and offer another match or sample; this is not a parser error.
- Fixture recovery: require the explicit, persistent provenance label defined
  above.
- Empty `options`, `limitations`, or `unknowns`: omit or explain the empty
  section without inserting invented content. Record the chosen rendering rule
  in tests.

Add focused unit/component tests for contract parsing, state transitions,
evidence resolution, all verdicts, and error recovery. Add one browser-level
test for the complete sample flow. Test that intent appears before the verdict
and that the hidden-future region is clearly labelled. Evidence tests must
cover all valid, partially valid, all missing, empty `facts_used`, all
unsupported, duplicate references, bare action IDs, and
`INSUFFICIENT_EVIDENCE` with no resolvable supporting facts. Partial evidence
must not show the notice; zero resolved supporting evidence must show it once.

Use a modest test stack: Vitest, Testing Library/user-event, and Playwright.
The complete validation matrix must include:

- strict schema parsing and rejection of extra/malformed fields;
- packet/card `decision_id` mismatch;
- reducer transitions and impossible-state prevention;
- pre-intent versus post-intent progress order;
- no judgement or verdict content in the DOM before intent submission;
- all verdict, empty, timeout, parser, model, unsafe-result, and invalid-response
  states;
- retry cancellation, stale-response rejection, and duplicate-submit
  prevention;
- explicit fixture provenance and no silent fallback;
- evidence disclosure keyboard behavior and no empty popovers;
- focus movement, polite status announcements, reduced motion, and a
  keyboard-only sample flow;
- semantic/text fallback for the knowledge boundary;
- the complete sample path in at most five actions, using an agreed counting
  rule; and
- no clipping or body-level horizontal overflow at `1440x900`, `1366x768`, and
  `1280x720`.

Fixture coverage must include `GOOD_DECISION`, `REASONABLE_BUT_RISKY`,
`POOR_DECISION`, `INSUFFICIENT_EVIDENCE`, no decision, parser error, timeout,
model failure, malformed response, partial evidence, zero evidence, unsafe
checks, and explicit fallback. A mocked backend adapter test does not count as
a genuine live/sample end-to-end test.

Run type checking, linting, component tests, the browser flow, and a production
build after relevant changes. Record exact commands and results. If a check
cannot run because a service or dependency is unavailable, report that rather
than claiming it passed.

Before a demo or release, also require a pinned Node version, committed lockfile,
clean dependency install, production-server smoke test, network-offline fixture
rehearsal, genuine primary and secondary sample runs, explicit recovery
rehearsal, second-machine verification, and a `1440x900` timed walkthrough. Do
not rely on globally installed tools, a warm cache, or development mode alone.

## Product acceptance validation

Coordinate five first-time-viewer sessions with Person 5. Within sixty seconds,
measure whether each person can explain:

- which decision was judged;
- what the player knew;
- what immediate action was observed;
- what information was hidden;
- why the judgement was made; and
- what to try in the next match.

Record observed results and the number of participants honestly. Fix the top
three comprehension failures; do not invent a pass or a percentage. Define the
five-action sample criterion before measuring it. A recommended count is:

1. try sample;
2. choose player when required;
3. choose intent;
4. submit intent; and
5. optionally inspect evidence.

Progress transitions must be automatic and must not require `Next` clicks.
Decide and document supported browsers, tick-versus-timestamp formatting when
tick rate is unavailable, fixture-mode production availability, and the
optional intent-note length before feature freeze.

## Delivery workflow

Work in the smallest demonstrable increments:

1. Record the P0 integration gates and questions for Person 1.
2. Scaffold the standalone frontend package and theme.
3. Add strict schemas/types and the approved deployable fixture strategy.
4. Add the reducer state model and typed backend/fixture ports.
5. Render all four screens from fixtures, splitting progress around intent.
6. Add the knowledge boundary, evidence resolver, notice, and unsafe-result
   gate.
7. Add failure, abstention, timeout, abort, retry, no-decision, invalid-response,
   and explicit fallback states.
8. Connect the frozen sample/upload API shapes without changing backend code.
9. Add component and browser tests, accessibility checks, responsive polish,
   production-build verification, and demo reset.
10. Run usability tests with Person 5 and fix the top comprehension failures.

After material frontend work, replace stale information in `STATUS.md` with the
current operational truth: implemented behavior, important paths, dependencies,
exact validation commands/results, limitations, contract impact, blockers, and
the next integration handoff. Do not edit `../INTEGRATION_STATUS.md`; Person 1
updates it only after merged end-to-end verification.

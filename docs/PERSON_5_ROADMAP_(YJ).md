# Person 5 Evidence, QA, Pitch, and Demo Roadmap

Last updated: 2026-08-05 (Asia/Singapore)

Owner: YJ (Person 5 - User Evidence, QA, Pitch Deck, and Demo)

Branch: `05/evidence_I_think`

## File naming convention

- Personal working and tracking files use `_(YJ)` immediately before the file
  extension.
- Shared deliverables keep an exact team-required filename when integrations or
  governance expect it, and identify YJ in the document's owner field.

## How to use this roadmap

- Change `[ ]` to `[x]` when an item is complete.
- Add links to completed documents beside their checklist items.
- Record real counts, dates, commands, and test results. Do not replace missing
  evidence with estimates.
- Keep personal data, raw interview recordings, private replays, and API keys
  out of Git.
- Work only in `docs/**` and `data/eval/human/**`. Report software defects to
  the relevant owner rather than editing teammate code.

## Deadline and submission details

- [ ] Record the exact submission date and time: `TBD`
- [ ] Record the submission timezone: `TBD`
- [ ] Confirm the maximum deck length: 15 slides
- [ ] Confirm the maximum video duration: 5:00
- [ ] Record the required repository collaborator or access setting: `TBD`
- [ ] Record the final Drive/submission location: `TBD`

## Current product truth to confirm

The repository currently has a working backend architecture, but the final
submission flow is not yet proven end to end. The current `main` frontend is a
landing slice, while `origin/04/frontend` contains substantial unmerged flow
work. Player intent and the full evidence-linked Decision Card are not part of
the documented live replay API.

Ask the team lead and component owners:

- [ ] Which commit or branch is the final demo candidate?
- [ ] When will `origin/04/frontend` be reviewed and merged?
- [ ] Which legal `.dem` or bundled sample will be shown?
- [ ] Has that exact input completed replay upload, player selection, coaching,
      and result display with the real provider?
- [ ] Is player intent implemented in the final build?
- [ ] Does the final build produce the complete Decision Card?
- [ ] Are evidence expansion and the practice quest implemented?
- [ ] Which AI provider and model must be disclosed?
- [ ] Which claims must be removed or labelled as future work?

Decision record:

| Question | Decision | Owner | Date confirmed |
| --- | --- | --- | --- |
| Final demo branch/commit | TBD | Person 1 | TBD |
| Primary demo input | TBD | Persons 1/2 | TBD |
| Player intent status | TBD | Persons 1/4 | TBD |
| Decision Card status | TBD | Persons 1/3 | TBD |
| AI provider/model | TBD | Persons 1/3 | TBD |

## Must-have deliverables

- [ ] `docs/STATUS.md` - current Person 5 status and blockers
- [ ] `docs/USER_RESEARCH.md` - cited secondary research and limitations
- [ ] `docs/HUMAN_REVIEW_PROTOCOL.md` - masked evaluation instructions
- [ ] `data/eval/human/review_cases.csv` - anonymized case results
- [ ] `docs/QA_MATRIX.md` - scenarios, evidence, severity, and status
- [ ] `docs/DECK_OUTLINE.md` - slide-by-slide claims and evidence
- [ ] `docs/DEMO_SCRIPT.md` - timed script based on implemented behavior
- [ ] `docs/THIRD_PARTY_DISCLOSURES.md` - models, APIs, data, assets, licences
- [ ] `docs/README_CONTRIBUTIONS.md` - suggested text for Person 1
- [ ] `docs/SUBMISSION_CHECKLIST.md` - final verification record
- [ ] Final PDF inspected and no more than 15 slides
- [ ] Final video inspected and no longer than 5:00

## Phase 1 - Establish product truth and evidence

Target: first working session

### Coordination

- [ ] Send the current-product questions above to Person 1.
- [ ] Ask Person 2 for legal samples and extracted decision cases.
- [ ] Ask Person 3 for provider/model details, outputs, and evaluation needs.
- [ ] Ask Person 4 for the frontend merge and demo readiness status.
- [ ] Reserve two rehearsal sessions with the team.

### Secondary research

Formal interviews may not be possible within the deadline. Use secondary
research honestly; do not describe it as user interviews or validated demand.

- [ ] Define the research questions.
- [ ] Research how CS2 players currently review matches.
- [ ] Research the limitations of statistics-only feedback.
- [ ] Research outcome bias and decision quality.
- [ ] Research evidence-linked or explainable AI recommendations.
- [ ] Compare Leetify, Scope.gg, Refrag, manual demo review, and generic AI
      coaching using cited sources.
- [ ] Record dissenting evidence and limitations.
- [ ] Clearly label the method as secondary research.
- [ ] If possible, collect a few short asynchronous player responses and report
      the exact convenience-sample size.

Research source tracker:

| Claim or question | Source | Date accessed | Finding | Limitation |
| --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | TBD |

### Phase 1 completion gate

- [ ] Demonstrable features are confirmed.
- [ ] Unsupported pitch claims are identified.
- [ ] Research method and limitations are written down.
- [ ] Slides 1-4 have evidence-backed draft content.

## Phase 2 - Human review design and QA

Target: second working session

### Review protocol

- [ ] Show reviewers only pre-decision evidence and the short action window.
- [ ] Include intent only when it is available in the real product flow.
- [ ] Hide later kills, deaths, survival, round outcome, and match outcome.
- [ ] Record acceptable verdicts and alternatives as sets.
- [ ] Allow reviewers to mark a case ambiguous or requiring abstention.
- [ ] Record missing material facts, one-sentence reasoning, and confidence 1-5.
- [ ] Do not force a single gold label when knowledgeable reviewers disagree.

### Evaluation cases

- [ ] Obtain cases from Persons 2 and 3.
- [ ] Assign anonymized case and decision IDs.
- [ ] Split cases before tuning: 60% development, 20% validation, 20% holdout.
- [ ] Keep the final holdout untouched until the agreed evaluation run.
- [ ] Target at least 20 cases when possible.
- [ ] If fewer cases are available, report the exact count and limitation.
- [ ] Report raw numerators and denominators beside every percentage.
- [ ] Never describe unreviewed or synthetic labels as human validation.

Evaluation counts:

| Measure | Count |
| --- | ---: |
| Total cases | 0 |
| Development cases | 0 |
| Validation cases | 0 |
| Holdout cases | 0 |
| Knowledgeable reviewers | 0 |
| Cases with two or more reviewers | 0 |

### QA priority matrix

P0 - submission or trust failure:

- [ ] Complete demo path succeeds.
- [ ] No API key or private data appears in source, logs, screenshots, or the
      frontend bundle.
- [ ] Nonexistent evidence is never presented as verified.
- [ ] Later outcome information does not influence outcome-blind coaching.
- [ ] Clean-machine setup succeeds or has an honest documented mitigation.

P1 - major product failure:

- [ ] Primary replay/sample parses successfully.
- [ ] Secondary replay/sample behavior is documented.
- [ ] Player selection works for an eligible player.
- [ ] No-eligible-decision behavior is understandable.
- [ ] Missing provider key is handled safely.
- [ ] Provider timeout/failure is handled safely.
- [ ] Malformed provider output is rejected or handled safely.
- [ ] Low-quality and contradictory evidence cause uncertainty or abstention.
- [ ] Refresh, reset, retry, and back navigation do not expose stale results.

P2/P3 - polish after P0/P1:

- [ ] Confusing copy and layout defects are recorded.
- [ ] Keyboard and narrow-screen behavior is checked.
- [ ] Cosmetic issues are separated from submission blockers.

Bug report template:

```text
Issue ID:
Decision ID:
Severity: P0 / P1 / P2 / P3
Environment and commit:
Reproduction steps:
Expected result:
Actual result:
Screenshot or evidence:
Assigned owner:
Status:
```

### Phase 2 completion gate

- [ ] Review protocol is frozen.
- [ ] Available cases are recorded with honest provenance.
- [ ] P0/P1 QA is complete for the demo candidate.
- [ ] Open P0/P1 issues have an owner and mitigation.
- [ ] Preliminary results for slides 10-12 are available.

## Phase 3 - Deck, demo, and submission package

Target: final working session before freeze

### Deck plan

- [ ] Slide 1 - title and one-line promise
- [ ] Slide 2 - problem
- [ ] Slide 3 - research evidence and method
- [ ] Slide 4 - decision quality is not outcome quality
- [ ] Slide 5 - implemented product flow
- [ ] Slide 6 - Knowledge-Boundary Decision Loop
- [ ] Slide 7 - annotated product screen
- [ ] Slide 8 - why AI is useful and where it is bounded
- [ ] Slide 9 - architecture
- [ ] Slide 10 - reliability controls actually implemented
- [ ] Slide 11 - evaluation method
- [ ] Slide 12 - results with sample sizes
- [ ] Slide 13 - impact and clearly labelled future work
- [ ] Slide 14 - limitations, privacy, and third parties
- [ ] Mark each claim as implemented, experimental, or future work.
- [ ] Remove all unfilled metric placeholders before export.

### Demo plan

- [ ] `0:00-0:25` - hook and problem
- [ ] `0:25-0:55` - replay/sample input
- [ ] `0:55-1:25` - detected decision and knowledge boundary
- [ ] `1:25-2:45` - coaching result
- [ ] `2:45-3:20` - outcome reveal only if supported by the final UI
- [ ] `3:20-4:00` - architecture and verified trust controls
- [ ] `4:00-4:20` - close
- [ ] Remove intent, evidence expansion, or quest segments if absent from the
      final build.
- [ ] Avoid terminal/code detours unless they prove an important claim.
- [ ] Complete rehearsal 1 and record duration: `TBD`
- [ ] Complete rehearsal 2 and record duration: `TBD`
- [ ] Record final video duration: `TBD`

### Disclosures and README handoff

- [ ] Record AI provider, model, and API configuration category.
- [ ] Record Pi SDK and agent-harness usage.
- [ ] Record FastAPI, Next.js, React, replay parser, LightGBM, and major
      libraries.
- [ ] Record replay/dataset sources and usage restrictions.
- [ ] Record map-image, font, and other asset sources and licences.
- [ ] Document privacy, retention, limitations, and exception handling without
      making unsupported legal claims.
- [ ] Send README contribution text to Person 1.

### Final audit

- [ ] Final repository commit is recorded: `TBD`
- [ ] Final deck is 15 slides or fewer.
- [ ] Final video is 5:00 or shorter.
- [ ] Text is readable at normal playback resolution.
- [ ] Audio is clear.
- [ ] No secret appears in Git history, frontend output, screenshots, or video.
- [ ] `.env.example` contains placeholders only.
- [ ] Setup instructions have been checked on a clean machine.
- [ ] Metrics include numerators, denominators, and limitations.
- [ ] Interviews are not claimed when only secondary research was performed.
- [ ] Future work is visibly labelled.
- [ ] Repository access and required collaborator are verified.
- [ ] Submission links work in a logged-out/incognito check.
- [ ] Final copies are stored in the agreed submission location.
- [ ] No files are modified after the final submission cutoff.

## If time becomes critical

Cut first:

- Elaborate deck animation and visual polish
- The 30-50 case stretch target
- Broad competitor coverage beyond the main comparison
- Cosmetic P2/P3 fixes
- Additional demo examples

Do not cut:

- One proven end-to-end demo
- Honest research and evaluation limitations
- P0 testing and secret inspection
- Third-party disclosures
- Accurate feature claims
- Slide-count, video-duration, access, and link checks

## Progress log

| Date/time | Work completed | Evidence/link | Next action or blocker |
| --- | --- | --- | --- |
| 2026-08-05 | Created Person 5 roadmap on a fresh branch | This file | Confirm deadline and product truth with team |

# Evidence, QA, Pitch, and Demo Status

Last updated: 2026-08-06 (Asia/Singapore)

Owner: YJ (Person 5 - User Evidence, QA, Pitch Deck, and Demo)

Branch: `05/evidence_I_think`

## Current status

**Person 5 workspace setup, the initial secondary-research review, the masked
human-review protocol, the review-data schema, the QA test plan, the first
third-party disclosure audit, and the 14-slide deck outline are complete.
Formal human review, QA execution, slide production, demo, disclosure approval,
and final submission verification have not yet been completed.**

The research draft compares public CS2 analytics, demo-review, and training
workflows; reviews outcome-bias research and explainable-AI guidance; and keeps
unsupported product claims out of the proposed pitch. Formal user interviews
were not conducted, so the findings are labelled as secondary research rather
than user validation. The reviewer protocol separates independent judgement
from system-output assessment, and the header-only CSV records one reviewer per
decision without fabricating cases. The team must now confirm the exact
deadline, final product scope, available decision cases, and potential
knowledgeable reviewers. The QA matrix contains 60 planned checks, all of which
remain `NOT_RUN` until tested against a recorded branch, commit, environment,
and input.

## Completed

- [x] Reviewed the Person 5 task brief.
- [x] Inspected the current repository structure and component status files.
- [x] Created the working branch `05/evidence_I_think` from `main`.
- [x] Created `docs/PERSON_5_ROADMAP_(YJ).md`.
- [x] Defined the `_(YJ)` naming convention for personal working files.
- [x] Created `docs/USER_RESEARCH_(YJ).md`.
- [x] Reviewed and registered 13 secondary sources covering competitors,
      outcome bias, explainable AI, and anecdotal community signals.
- [x] Documented safe pitch wording, unsupported claims, and research
      limitations.
- [x] Created `docs/HUMAN_REVIEW_PROTOCOL_(YJ).md` for masked two-phase review.
- [x] Created the 45-column header schema in
      `data/eval/human/review_cases_(YJ).csv`.
- [x] Kept the evaluation dataset empty until genuine cases and reviewer
      responses are available.
- [x] Created `docs/QA_MATRIX_(YJ).md` with 60 prioritized product,
      reliability, accessibility, and submission checks.
- [x] Kept every QA result at `NOT_RUN`; no code inspection or verbal report
      has been counted as an executed test.
- [x] Created `docs/THIRD_PARTY_DISCLOSURES_(YJ).md` from the repository's
      manifests, service configuration, dataset references, trained artifacts,
      fonts, and visual-asset sources.
- [x] Recorded disclosure blockers without treating attribution or a package
      licence as permission for separately owned data or game assets.
- [x] Created `docs/DECK_OUTLINE_(YJ).md` with a 14-slide narrative mapped to
      the judging criteria, available evidence, visual suggestions, safe claims,
      and slide-specific completion states.
- [x] Registered 15 missing-information items (`M01`-`M15`) with the owner,
      affected slides, and evidence required to resolve each one.

## In progress

- [ ] Confirming the final product and submission details with the team.
- [ ] Requesting genuine decision cases and system outputs from Persons 2 and
      3.
- [ ] Identifying possible knowledgeable reviewers and recording whether they
      are external or internal to the project.
- [ ] Obtaining component-owner confirmations for the final AI model, replay
      and training-data rights, model provenance, visual assets, deployment,
      and repository-licence decision.
- [ ] Building slides from the approved outline and replacing missing-content
      markers only when their required evidence is supplied.

## Not started

- [ ] Populated anonymized review cases and formal human-review results
- [ ] QA execution and issue reporting
- [ ] Final pitch deck content, screenshots, results, and PDF export
- [ ] Timed demo script and rehearsals
- [ ] Final third-party disclosure approval and final-commit re-audit
- [ ] README evidence/disclosure handoff to Person 1
- [ ] Final submission audit

## Decisions required from the team

| Question | Required owner | Status |
| --- | --- | --- |
| What is the exact submission deadline and timezone? | Person 1 | TBD |
| Which branch and commit will be the demo candidate? | Person 1 | TBD |
| Which legal `.dem` or sample will be used? | Persons 1 and 2 | TBD |
| Has that input completed the real end-to-end flow? | Persons 1-4 | TBD |
| Will player intent appear in the submitted build? | Persons 1 and 4 | TBD |
| Will the complete Decision Card appear? | Persons 1 and 3 | TBD |
| Will evidence expansion and a practice quest appear? | Persons 3 and 4 | TBD |
| Which AI provider and model must be disclosed? | Persons 1 and 3 | TBD |
| Who will record and edit the final video? | Team | TBD |
| Where will the final deck and video be submitted? | Person 1 | TBD |

## Current repository observations to verify

- The backend documents an uploaded-replay flow covering upload, preparation,
  player selection, coaching, and result retrieval.
- The current product documentation says a real `.dem` has not yet completed
  the entire flow.
- The documented live replay API does not currently support player intent or
  follow-up questions.
- The complete frontend work on `origin/04/frontend` was not merged into `main`
  when this branch was created.
- The live replay-job coaching result and the frozen version `1.0` Decision
  Card are documented as separate integration surfaces.

These observations must be rechecked against the final demo commit before they
are used in the deck, demo, or submission claims.

## Research and evaluation status

| Measure | Current count | Notes |
| --- | ---: | --- |
| Secondary sources reviewed | 13 | Initial source register completed |
| Personal interviews | 0 | May not be feasible within timeline |
| Asynchronous research responses | 0 | Optional convenience sample |
| Knowledgeable human reviewers | 0 | Not yet recruited |
| Genuine decision cases available | 0 | Awaiting Persons 2 and 3 |
| Cases reviewed | 0 | Human review not executed |
| Holdout cases evaluated | 0 | Not started |

No user-validation, coaching-accuracy, usefulness, or reliability percentage
may be claimed from these current counts.

## QA status

| Priority | Passed | Failed | Blocked | Not tested |
| --- | ---: | ---: | ---: | ---: |
| P0 | 0 | 0 | 0 | 8 |
| P1 | 0 | 0 | 0 | 32 |
| P2/P3 | 0 | 0 | 0 | 11 |
| Submission | 0 | 0 | 0 | 9 |

QA will begin after the team identifies a stable demo candidate. A test result
must record the branch or commit, environment, expected result, actual result,
severity, and supporting evidence.

## How each YJ file is used

| File | Primary user | How it is utilised | Final-submission role |
| --- | --- | --- | --- |
| `docs/PERSON_5_ROADMAP_(YJ).md` | YJ | Master schedule and progress checklist; updated as deliverables and gates are completed | Prevents missed Person 5 tasks and records the work sequence |
| `docs/STATUS_(YJ).md` | YJ and the team | Short operational handoff showing completed work, real counts, dependencies, blockers, and next actions | Gives Person 1 current verified claims and limitations without reading every working file |
| `docs/USER_RESEARCH_(YJ).md` | YJ, Person 1, and deck reviewers | Source-backed problem, competitor, outcome-bias, and explainable-AI research; separates evidence from hypotheses | Supports deck problem/insight slides and prevents unsupported market claims |
| `docs/HUMAN_REVIEW_PROTOCOL_(YJ).md` | YJ and knowledgeable reviewers | Defines masked Phase A independent judgement and Phase B system-output assessment | Makes any later coaching evaluation reproducible and honest; remains a proposed protocol if not executed |
| `data/eval/human/review_cases_(YJ).csv` | YJ | Master anonymized result table with one row per reviewer-decision pair; populated only from genuine cases and responses | Supplies raw counts and denominators for evaluation metrics; remains header-only if review is not executed |
| `docs/QA_MATRIX_(YJ).md` | YJ and component owners | Freezes scope, prioritizes tests, records actual results/evidence, assigns failures, and preserves retests | Supports build-quality claims, demo readiness, known limitations, and the final release decision |
| `docs/THIRD_PARTY_DISCLOSURES_(YJ).md` | YJ, component owners, and Person 1 | Living inventory of software, services, models, data, fonts, and assets; assigns verification owners and records unresolved rights or provenance | Supplies approved README/submission disclosures and prevents the team from treating attribution as permission |
| `docs/DECK_OUTLINE_(YJ).md` | YJ, Person 1, and slide contributors | Provides the 14-slide narrative, draft copy, visual direction, evidence mapping, missing-information register, and slide completion gates | Becomes the controlled content source for the final PDF while keeping unsupported, proposed, and future claims visible |

These files have different purposes. The roadmap plans the work, this status
file summarizes it, the research supports the problem narrative, the protocol
defines human evaluation, the CSV stores responses, the QA matrix verifies the
application and submission, the disclosure inventory tracks third-party inputs
and owner approvals, and the deck outline converts verified material into a
slide plan. A prepared template is not evidence of a passed test, completed
evaluation, cleared asset, implemented feature, or approved disclosure.

## Dependencies and handoffs

- **Person 1:** deadline, final integration state, README ownership, submission
  access, and final claims.
- **Person 2:** legal replay samples, masked decision windows, decision IDs,
  pre-decision evidence, and observed actions.
- **Person 3:** system outputs, provider/model details, rubric/reliability
  behavior, evaluation version, and evidence references.
- **Person 4:** final frontend flow, screenshots, supported states, usability
  test build, and demo readiness.
- **YJ:** cited research, evaluation organization, QA records, honest metrics,
  deck narrative, demo script, disclosures, and submission checks.

## Current blockers and risks

- Exact submission deadline has not been recorded in the Person 5 workspace.
- The final demo branch and commit have not been confirmed.
- The primary demo input and real end-to-end success have not been confirmed.
- Final support for intent, the complete Decision Card, evidence expansion, and
  the practice quest is unknown.
- No review cases or knowledgeable reviewers have been confirmed.
- The initial disclosure inventory has unresolved owner confirmations: exact
  deployed model, replay/tournament rights, trained-artifact provenance,
  Valve-derived imagery, hosting, final dependency versions, and the root
  repository-licence decision.

## Next actions

1. Send the decision questions above to the relevant team members.
2. Record the exact deadline and final demo scope.
3. Ask Persons 2 and 3 how many genuine masked decision cases are available.
4. Identify knowledgeable reviewers or record that recruitment is not feasible.
5. Freeze applicable QA rows and execute P0 tests on the final demo candidate.
6. Create `docs/DECK_OUTLINE_(YJ).md` after the demonstrable feature scope is
   confirmed.
7. Review the research claims with the team before using them in the deck.
8. Send the disclosure blockers to their named owners and record their evidence.
9. Re-audit disclosures against the exact final submission commit.
10. Build slides 1-4 and the reusable visual layouts for slides 6, 8, 9, 11,
    13, and 14 from the deck outline.
11. Resolve deck missing-information IDs as owners provide final evidence.
12. Update this file whenever a blocker or deliverable materially changes.

## Update log

| Date | Update | Evidence or next action |
| --- | --- | --- |
| 2026-08-05 | Created initial Person 5 status | Confirm deadline and product truth with team |
| 2026-08-05 | Completed initial secondary-research draft with 13 registered sources | Review claims with team and prepare human-review protocol |
| 2026-08-05 | Completed masked review protocol and empty 45-column evaluation schema | Obtain genuine cases and reviewers; do not fabricate rows |
| 2026-08-06 | Completed 60-check QA plan and documented how each YJ file is utilised | Freeze the final demo scope, obtain test inputs, and execute P0 checks |
| 2026-08-06 | Completed the initial third-party disclosure audit and documented its update triggers | Obtain owner confirmations and re-audit the exact final submission commit |
| 2026-08-06 | Completed the 14-slide deck outline with 15 owned missing-information items | Build stable slides now and fill final product/results content only from verified evidence |

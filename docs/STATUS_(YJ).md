# Evidence, QA, Pitch, and Demo Status

Last updated: 2026-08-05 (Asia/Singapore)

Owner: YJ (Person 5 - User Evidence, QA, Pitch Deck, and Demo)

Branch: `05/evidence_I_think`

## Current status

**Person 5 workspace setup and the initial secondary-research review are
complete. Human review, QA, deck, demo, disclosures, and final submission
verification have not yet been completed.**

The research draft compares public CS2 analytics, demo-review, and training
workflows; reviews outcome-bias research and explainable-AI guidance; and keeps
unsupported product claims out of the proposed pitch. Formal user interviews
were not conducted, so the findings are labelled as secondary research rather
than user validation. The next document is the human-review protocol, while
the team confirms the exact deadline, final product scope, and available
decision cases.

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

## In progress

- [ ] Confirming the final product and submission details with the team.
- [ ] Preparing the masked human-review protocol.
- [ ] Requesting genuine decision cases and system outputs from Persons 2 and
      3.

## Not started

- [ ] Human-review protocol
- [ ] Anonymized review cases
- [ ] QA execution and issue reporting
- [ ] Pitch deck content
- [ ] Timed demo script and rehearsals
- [ ] Third-party disclosure inventory
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
| P0 | 0 | 0 | 0 | TBD |
| P1 | 0 | 0 | 0 | TBD |
| P2/P3 | 0 | 0 | 0 | TBD |

QA will begin after the team identifies a stable demo candidate. A test result
must record the branch or commit, environment, expected result, actual result,
severity, and supporting evidence.

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
- No final third-party inventory has been supplied by component owners.

## Next actions

1. Send the decision questions above to the relevant team members.
2. Record the exact deadline and final demo scope.
3. Create `docs/HUMAN_REVIEW_PROTOCOL_(YJ).md`.
4. Ask Persons 2 and 3 how many genuine masked decision cases are available.
5. Review the research claims with the team before using them in the deck.
6. Update this file whenever a blocker or deliverable materially changes.

## Update log

| Date | Update | Evidence or next action |
| --- | --- | --- |
| 2026-08-05 | Created initial Person 5 status | Confirm deadline and product truth with team |
| 2026-08-05 | Completed initial secondary-research draft with 13 registered sources | Review claims with team and prepare human-review protocol |

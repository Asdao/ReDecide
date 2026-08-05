# RE:DECIDE Pitch Deck Outline

Last updated: 2026-08-06 (Asia/Singapore)

Owner: YJ (Person 5 - evidence, pitch, QA, and demo)

Status: **STRUCTURE READY; FINAL PRODUCT, QA, AND EVALUATION CONTENT MISSING**

Target: 14 slides, within the 15-slide submission maximum

Judging weights: Problem-Solution Fit 40%, Build Quality 30%, Originality 30%

## How to use this outline

You can build the visual layout and draft the stable copy now. Every slide has:

- a purpose;
- draft content;
- a suggested visual;
- evidence already available;
- missing information identified by an `M-ID`; and
- a completion state.

Use these labels in working slides and speaker notes:

| Label | Meaning |
| --- | --- |
| `SUPPORTED` | Backed by cited research or verified repository evidence |
| `REPO-REPORTED` | Reported in a component status file; recheck the final commit before submission |
| `PROPOSED` | Evaluation method, design, or workflow that has not been executed |
| `FUTURE WORK` | Not part of the demonstrated build |
| `MISSING` | Required information or evidence has not been supplied |

Remove internal `M-ID` labels from the exported PDF only after each item is
resolved. Keep user-facing `PROPOSED` and `FUTURE WORK` labels wherever they
are needed to avoid overstating the build.

## Missing-information register

| ID | Missing information | Required owner | Slides affected | What counts as resolution |
| --- | --- | --- | --- | --- |
| M01 | Final team name, member names/roles, approved logo, and presenter | Person 1 / team | 1, 14 | Approved text and assets |
| M02 | Exact final demo branch, commit, deployment URL, and verification date | Person 1 | 5-10, 12, 14 | Recorded commit and working URL |
| M03 | Final implemented feature scope: upload/sample, player selection, intent, Decision Card, evidence expansion, outcome reveal, practice quest | Persons 1, 3, and 4 | 5-8, 10, 13 | Feature checklist verified against final build |
| M04 | Final screenshots at presentation resolution | Person 4 / YJ | 5, 7, 10 | Screenshots from M02 with no secrets/private data |
| M05 | Exact deployed AI provider, model ID/version, endpoint category, and fallback | Persons 1 and 3 | 8, 9, 14 | Deployment evidence excluding secrets |
| M06 | Legal primary demo replay/sample, source, attribution, and redistribution decision | Persons 1 and 2 | 5, 7, 12, 14 | Named sample and documented permission basis |
| M07 | Proven real end-to-end run and duration for the primary demo input | Persons 1-4 | 5, 7, 12 | Recorded run on M02 with result evidence |
| M08 | Executed P0/P1 QA results, failures, mitigations, and retests | YJ and component owners | 10, 12, 14 | Completed QA rows with commit/environment/evidence |
| M09 | Genuine cases, reviewer count, review results, denominators, and limitations | Persons 2 and 3 / YJ | 11, 12 | Completed review records or explicit non-execution statement |
| M10 | Team-approved final architecture and which validators run in the demonstrated path | Persons 1-4 | 6, 8-10 | Diagram checked against M02 |
| M11 | Final privacy, replay retention/deletion, logging, and provider-data handling | Persons 1 and 3 | 14 | Approved deployment-specific statements |
| M12 | Final third-party decisions: repository licence, dataset revision/terms, model provenance, map imagery, fonts, hosting | Named owners in disclosure inventory | 9, 14 | Resolved rows in `THIRD_PARTY_DISCLOSURES_(YJ).md` |
| M13 | Realistic impact statement and approved future roadmap | Person 1 / team | 13 | Team-approved wording without unmeasured claims |
| M14 | Any direct user responses or usability sessions that can be reported honestly | YJ / team | 3, 12 | Consent-safe notes and exact sample count; otherwise state zero |
| M15 | Final submission link/location and any required acknowledgement wording | Person 1 | 14 | Submission instructions recorded |

## Recommended visual system

Mirror the current frontend identity so the deck feels like the product:

- deep charcoal `#0C0F12` background;
- signature orange `#F7941D` for decisions and primary emphasis;
- muted steel blue `#5D79AE` for evidence and system structure;
- tactical tan `#CCBA7C` for uncertainty, limitations, and abstention;
- sharp card geometry and restrained diagonal bars;
- Saira/Saira Condensed for display text and Noto Sans for body copy, subject
  to final font-notice verification.

Keep one message per slide, use large labels, and avoid screenshots whose text
cannot be read at normal PDF size or 1080p video resolution.

---

## Slide 1 - Title and promise

**Completion state:** `READY TO BUILD` with M01

**Purpose:** Establish the product and memorable thesis immediately.

**Draft headline:**

> RE:DECIDE

**Draft sub-headline:**

> Don't replay the match. Replay the decision.

**Supporting line:**

> Evidence-bounded reflection on what a CS2 player could know when the choice
> was made.

**Suggested visual:** One decision boundary cutting a round timeline into
“known then” and “revealed later.” Avoid an unverified product screenshot here.

**Evidence available:** Product thesis from the Person 5 brief; repository
documents an outcome-blind first-damage decision pipeline.

**MISSING:** M01.

**Do not claim yet:** Accuracy, user adoption, improvement rate, or complete
end-to-end readiness.

## Slide 2 - The problem: results do not explain the choice

**Completion state:** `READY TO BUILD`

**Purpose:** Frame a focused player problem without attacking competitors.

**Draft headline:**

> A death tells you what happened—not whether the decision was reasonable.

**Draft content:**

- Existing CS2 tools already provide detailed statistics, benchmarks, replay
  viewers, clips, and training workflows.
- The remaining product question is how to translate one replay moment into an
  understandable decision lesson.
- RE:DECIDE tests whether separating information available at the choice from
  the later outcome can make reflection more useful and fair.

**Suggested visual:** “Scoreboard/statistics” on the left, “decision context” on
the right, separated by the question “What could I know at that moment?”

**Evidence available:** Competitor research on Leetify, SCOPE.GG, and Refrag in
`USER_RESEARCH_(YJ).md`.

**MISSING:** None for the general framing. M14 only if the team wants to add a
direct-user pain statement.

**Do not claim:** “All existing tools only show statistics” or “players dislike
current tools.”

## Slide 3 - Evidence so far: secondary research, not interviews

**Completion state:** `READY TO BUILD`; optional M14

**Purpose:** Demonstrate problem research while being explicit about its limits.

**Draft headline:**

> We found a credible question to test—not proof of validated demand.

**Draft content:**

- 13 secondary sources reviewed across competitor capabilities, public
  community discussions, outcome bias, and explainable-AI guidance.
- Public products confirm a mature ecosystem of analytics, replay review, and
  practice tools.
- Community discussions provide anecdotal signals that translating statistics
  and demos into action can be difficult.
- Personal interviews completed: **0**. Formal usability sessions: **0**.

**Suggested visual:** Four-source evidence stack with a visible limitation bar:
official products / peer-reviewed research / institutional guidance / anecdotal
community signals.

**Evidence available:** Research method and 13-source register in
`USER_RESEARCH_(YJ).md`.

**MISSING:** M14 if genuine responses become available. Otherwise retain the
zero counts and remove any quote placeholder.

**Do not include:** Invented personas, fabricated quotes, prevalence
percentages, or language such as “users validated.”

## Slide 4 - Insight: decision quality is not outcome quality

**Completion state:** `READY TO BUILD`

**Purpose:** Explain the reasoning behind outcome-blind review.

**Draft headline:**

> Good decisions can end badly. Bad decisions can still win.

**Draft content:**

- Outcome-bias research shows that knowledge of the result can distort how an
  earlier decision is evaluated.
- The cited studies are not CS2 studies; they justify testing the design, not
  claiming the product is correct.
- RE:DECIDE's principle: judge the choice using the knowledge boundary first,
  then reveal the outcome separately.

**Suggested visual:** A 2x2 matrix: good/bad decision versus good/bad outcome.
Highlight the two counterintuitive cells.

**Evidence available:** Baron and Hershey (1988) and Aiyer et al. (2023), cited
in `USER_RESEARCH_(YJ).md`.

**MISSING:** None.

## Slide 5 - Product flow

**Completion state:** `LAYOUT NOW; CONTENT PARTIAL`

**Purpose:** Show the demonstrated user journey rather than the aspirational one.

**Working flow:**

```text
Replay input -> parse once -> select player -> prepare analysis
-> identify first-damage decisions -> run coach -> show timeline and advice
```

**Target flow from the product thesis:**

```text
Replay -> knowledge boundary -> player intent -> Decision Card
-> inspectable evidence -> one practice quest
```

Only show the target flow as implemented if every stage is verified in M03 and
M07. Otherwise present the first flow as “current prototype” and mark missing
target stages `FUTURE WORK`.

**Suggested visual:** Five or six horizontal numbered cards. Reserve screenshot
slots, but use neutral wireframes until final images arrive.

**Evidence available:** `CURRENT_STATE.md` and component status files.

**MISSING:** M02, M03, M04, M06, M07.

## Slide 6 - Signature innovation: Knowledge-Boundary Decision Loop

**Completion state:** `LAYOUT NOW; FINAL VERIFICATION REQUIRED`

**Purpose:** Carry the Originality argument.

**Draft headline:**

> Freeze what was knowable. Evaluate the choice. Reveal the result later.

**Draft loop:**

1. Detect a meaningful first-contact decision window.
2. Freeze replay facts at the knowledge cutoff.
3. Record the observed short action without later-round information.
4. Add player intent only if the product genuinely collects it before judgement.
5. Produce bounded coaching or abstain.
6. Reveal later outcome separately and create a transfer cue only if supported.

**Suggested visual:** Circular loop with an orange decision boundary and a
locked blue evidence region. Put unimplemented stages in a dashed outline.

**Evidence available:** Backend status reports decision and action cutoffs plus
an outcome-blind projection.

**MISSING:** M03 and M10.

**Do not claim:** That all six stages run end to end until verified.

## Slide 7 - Product screen: make the coaching inspectable

**Completion state:** `BLOCKED FOR FINAL CONTENT; LAYOUT CAN START`

**Purpose:** Make the product concrete and readable.

**Planned annotations, only where implemented:**

- selected player and decision moment;
- verdict and calibrated confidence;
- facts/evidence references;
- observed action and acceptable alternatives;
- missing facts, uncertainty, or abstention;
- one actionable practice cue.

**Suggested visual:** One large final-build screenshot with no more than five
numbered callouts. Use a clearly labelled conceptual wireframe while waiting.

**Evidence available:** Version `1.0` packet/card fixtures exist, but current
status says the full user-facing Decision Card remains a separate integration
surface and the frontend flow is not complete.

**MISSING:** M02, M03, M04, M06, M07.

**Do not do:** Present a fixture or mock-up as a live product screen.

## Slide 8 - Why AI, and where it is bounded

**Completion state:** `PARTIAL`

**Purpose:** Explain why an LLM adds value without claiming it owns the facts.

**Draft headline:**

> Deterministic replay facts set the boundary; AI explains trade-offs inside it.

**Draft content:**

- Replay parsing, cutoffs, player identity, and evidence should remain
  authoritative system facts.
- The AI layer translates structured context into concise coaching language.
- The model should not watch the full replay, invent evidence, or override
  deterministic validation.
- Weak or contradictory evidence should lead to uncertainty or abstention.

**Suggested visual:** Two-column responsibility split: deterministic system
versus language model, joined by a narrow validated JSON boundary.

**Evidence available:** The current Pi adapter removes post-cutoff events,
anonymises player identifiers, disables Pi tools, and validates a narrow
response shape. The complete Decision Card validator is still separate work.

**MISSING:** M03, M05, and M10.

## Slide 9 - Architecture

**Completion state:** `LAYOUT NOW; FINAL PATH MISSING`

**Purpose:** Demonstrate Build Quality with an understandable system boundary.

**Working architecture:**

```text
Next.js UI
  -> FastAPI replay/upload and analysis jobs
  -> replay extractor and decision pipeline
  -> replay/model analysis
  -> server-side Pi coaching adapter
  -> validated player-scoped result
  -> UI timeline and coaching view
```

**Suggested visual:** Six boxes with trust boundaries. Use solid connectors for
implemented paths and dashed connectors for target adapters not in the final
build. Show API keys only as “server-side secret,” never as a value.

**Evidence available:** `CURRENT_STATE.md`, replay/coach status files, and
agent-harness architecture documentation.

**MISSING:** M02, M05, M10, and M12.

## Slide 10 - Reliability and trust controls

**Completion state:** `PARTIAL; QA RESULTS MISSING`

**Purpose:** Convert technical controls into user trust claims.

**Candidate rows:**

| Risk | Control to verify | Final evidence |
| --- | --- | --- |
| Outcome leakage | Decision/action cutoffs and outcome-blind projection | M08 / final test ID |
| Invented evidence | Evidence-ID validation or fail-closed handling | M03, M08 |
| Contradictory or sparse facts | Confidence cap and abstention | M03, M08 |
| Invalid provider output | Strict schema/response handling | M08 |
| Identity/privacy leakage | Anonymisation and server-side credentials | M08, M11 |
| Operational failure | Typed errors, timeout/retry/fallback behavior | M08 |

**Suggested visual:** Risk -> control -> proof table with pass/fail icons only
after actual QA execution.

**Evidence available:** Component tests are reported, and the QA matrix defines
60 planned checks. YJ's execution count is currently 0; all 60 are `NOT_RUN`.

**MISSING:** M02, M03, M08, M10, and M11.

**Do not claim:** “Fully safe,” “hallucination-free,” or a pass rate before QA.

## Slide 11 - Validation method

**Completion state:** `READY AS PROPOSED METHOD`

**Purpose:** Show how coaching quality would be judged without outcome leakage.

**Draft headline:**

> Review the decision before showing reviewers what happened later.

**Draft method:**

1. Give knowledgeable reviewers only pre-decision evidence and the short
   observed action window.
2. Collect acceptable verdicts/actions, missing facts, ambiguity, reasoning,
   and confidence.
3. Then show the system output and audit factual errors, unsupported claims,
   evidence references, recommendation acceptability, abstention, and
   usefulness.
4. Preserve disagreement instead of forcing one fake gold label.

**Suggested visual:** Masked Phase A -> system assessment Phase B -> aggregate
with raw numerator/denominator.

**Evidence available:** `HUMAN_REVIEW_PROTOCOL_(YJ).md` and the empty review CSV
schema.

**MISSING:** M09 for execution. Label the entire slide `PROPOSED METHOD` until
genuine review is completed.

## Slide 12 - Results and evidence

**Completion state:** `BLOCKED`

**Purpose:** Present only measured evidence with its denominator and limits.

**Reserve space for:**

- end-to-end demo success on the named input;
- P0/P1 QA passed, failed, blocked, and not-run counts;
- factual-error and unsupported-claim counts;
- valid evidence-reference rate;
- acceptable verdict/recommendation counts;
- appropriate abstention count;
- reviewer usefulness distribution; and
- latency for the final configuration.

**Required display format:**

```text
Metric: [numerator] / [denominator] ([percentage only when appropriate])
System version: [commit/model/rubric]
Limitation: [sample and scope]
```

**Safe fallback if no human review occurs:** Replace the evaluation chart with
“Human coaching evaluation not completed before submission” and show only
verified engineering/demo evidence. Do not turn repository unit-test counts
into coaching-accuracy evidence.

**MISSING:** M02, M06, M07, M08, M09, and M14.

## Slide 13 - Impact and next-match loop

**Completion state:** `PARTIAL; FUTURE ROADMAP MISSING`

**Purpose:** Show why one decision review could matter and where the product can
go next.

**Draft headline:**

> From one replay moment to one cue the player can recognize next match.

**Current-impact wording:**

> RE:DECIDE is designed to reduce a complex replay into a bounded decision,
> supporting facts, and an actionable reflection.

**Possible future work, visibly labelled:**

- next-match transfer receipt;
- repeated-match progress tracking;
- additional decision families;
- coach/team review workflows; and
- user-controlled replay retention and comparison.

**Suggested visual:** Current prototype in a solid card; future learning loop in
dashed cards.

**MISSING:** M03 and M13.

**Do not claim:** Measured behavior improvement, automatic learning, retention,
or market scale without evidence.

## Slide 14 - Honest scope, privacy, and close

**Completion state:** `LAYOUT NOW; FINAL FACTS MISSING`

**Purpose:** Close with credibility and show that limitations are deliberate.

**Draft sections:**

**What the prototype demonstrates**

- Fill from M03 and M07 only.

**Current limitations**

- Human interviews and formal coaching review may remain unexecuted.
- Final frontend integration and real replay flow must be stated exactly.
- Coaching is bounded analysis, not proof of a uniquely correct move.

**Privacy and third parties**

- Replay retention/deletion and model-provider handling: M11.
- Provider/model, dataset, asset, font, and hosting disclosures: M05/M12.
- Counter-Strike/Valve non-affiliation wording: final owner approval required.

**Closing line:**

> RE:DECIDE does not ask AI to know the perfect move. It asks the system to
> explain one decision using only what was knowable then.

**Suggested visual:** Three compact cards—demonstrated, bounded, next—plus team
identity and repository/demo reference if permitted.

**MISSING:** M01, M02, M03, M05, M11, M12, and M15.

---

## Slide-building order

### Build now

- Slides 1-4: stable narrative and cited research.
- Slide 6: loop graphic, with dashed unverified stages.
- Slide 8: AI-versus-deterministic responsibility layout.
- Slide 9: architecture layout, pending final connector status.
- Slide 11: proposed review-method visual.
- Slides 13-14: layout with clearly marked future/missing content.

### Add after team confirmation

- Slide 5 final implemented flow.
- Slide 7 final screenshot and callouts.
- Slides 8-10 final model, architecture, and reliability claims.
- Slide 14 final privacy and third-party disclosures.

### Add only after execution

- Slide 10 QA pass/fail evidence.
- Slide 12 all results and metrics.
- Any direct-user quote, usability finding, accuracy percentage, usefulness
  result, or latency claim.

## Final deck quality gate

- [ ] Every slide has one clear takeaway.
- [ ] Every factual claim maps to research, repository evidence, or a recorded test.
- [ ] No mock-up or fixture is presented as a live final-build screenshot.
- [ ] Implemented, proposed, and future work are visually distinguishable.
- [ ] Research is described as secondary research; interviews remain at the real count.
- [ ] Results show raw numerator and denominator and identify the tested version.
- [ ] No placeholder, `TBD`, `M-ID`, or bracketed field remains accidentally.
- [ ] No API key, personal identifier, private replay data, or unapproved logo appears.
- [ ] Third-party assets and disclosures match the final build.
- [ ] Screenshots remain readable at normal PDF size and video resolution.
- [ ] PDF contains no more than 15 slides.
- [ ] The final PDF is rendered and visually inspected page by page.

## Evidence files for drafting

- `docs/USER_RESEARCH_(YJ).md`
- `docs/HUMAN_REVIEW_PROTOCOL_(YJ).md`
- `docs/QA_MATRIX_(YJ).md`
- `docs/THIRD_PARTY_DISCLOSURES_(YJ).md`
- `docs/STATUS_(YJ).md`
- `docs/CURRENT_STATE.md`
- `frontend/STATUS.md`
- `backend/app/replay/STATUS.md`
- `backend/app/coach/STATUS.md`
- `agent-harness/docs/ARCHITECTURE.md`

This outline must be updated when the final feature scope or submission commit
changes. The exported deck, not this working file, is the submission artifact.

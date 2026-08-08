# RE:DECIDE Masked Human-Review Protocol

Last updated: 2026-08-05 (Asia/Singapore)

Owner: YJ (Person 5 - User Evidence, QA, Pitch Deck, and Demo)

Status: Protocol prepared; formal human review not yet executed

## Purpose

This protocol describes how knowledgeable human reviewers should assess
RE:DECIDE decision cases and coaching outputs without seeing later match
outcomes. It is designed to answer:

1. Is the system verdict within the set of verdicts a knowledgeable reviewer
   considers acceptable?
2. Is the recommended action acceptable given the evidence available at the
   decision boundary?
3. Does the coaching contain factual errors or unsupported claims?
4. Does the system abstain when the evidence is insufficient or contradictory?
5. Is the result useful as a concise next-match lesson?

This is an evaluation document for people. It is not an AI-agent `SKILL.md`, a
provider prompt, or the coaching rubric. Reviewers must form an independent
judgement rather than reproduce the system's instructions.

## Current execution status

- Knowledgeable reviewers recruited: 0
- Genuine decision cases received: 0
- Cases reviewed: 0
- Formal review executed: no

Until real reviewers and cases are recorded, this document describes a planned
method only. It must not be cited as evidence that the coaching is accurate,
useful, or trustworthy.

## Roles and responsibilities

- **Person 2** supplies legal, outcome-blind decision windows, stable decision
  IDs, pre-decision evidence, observed actions, unknowns, and data-quality
  warnings.
- **Person 3** supplies versioned system outputs, evidence references,
  confidence, limitations, checks, and model/rubric identifiers.
- **YJ** assigns anonymized case IDs, verifies masking, prepares review forms,
  records reviewer responses, calculates descriptive results, and reports
  limitations.
- **Reviewers** make independent CS2 judgements and disclose relevant
  expertise or conflicts.
- **Person 1** approves any claim that moves from evaluation results into the
  final README, deck, or submission.

## Reviewer eligibility

Preferred reviewers are experienced CS2 players, coaches, analysts, or people
who regularly review demos. Record expertise through self-report rather than
inventing a rank or expert label.

For each reviewer record:

- anonymized reviewer alias;
- self-described CS2 experience;
- current or recent rank/level when voluntarily provided;
- demo-review or coaching experience;
- whether they contributed to RE:DECIDE; and
- any other conflict that may affect independence.

Prefer two or three reviewers per case. If only one reviewer is available,
report that fact. Team members may provide an internal review when external
reviewers are unavailable, but results must be labelled non-independent and
must not be presented as external expert validation.

Do not commit reviewer names, contact information, account identifiers, raw
recordings, or private messages. Keep consent and recruitment records outside
the public or shared repository unless the participant explicitly agreed to
their inclusion.

## Case eligibility

A review case must have:

- a stable `decision_id`;
- a versioned source or extraction record;
- one `POST_CONTACT_RESET` decision window;
- `decision_open_tick` and `action_close_tick` boundaries;
- evidence available at or before the decision opening;
- an immediate observed-action description or an honest `UNCLASSIFIED` label;
- unknowns and data-quality information;
- a system/rubric/model version for the evaluated output; and
- a clear record that later outcome fields were withheld from review input.

Checked-in fixtures may be used to rehearse the protocol and form. They do not
automatically count as independent real-world evaluation cases. Multiple
copies or cosmetic variations of one fixture must not be counted as separate
cases.

Reject or quarantine a case when:

- its identity or data provenance is unclear;
- evidence labelled as pre-decision occurs after `decision_open_tick`;
- later kill, death, survival, round winner, or match winner is present;
- the packet and result use different decision IDs;
- the observed action uses evidence beyond `action_close_tick`;
- evidence has been manually rewritten to make the system look better; or
- the case was selected only because its result supports a desired metric.

Record excluded cases and reasons. Do not silently replace failed or difficult
cases.

## Information shown to reviewers

### Phase A - Independent judgement

Show the reviewer only:

- anonymized case ID;
- map and round alias;
- decision type;
- neutral decision timestamp or tick;
- evidence known at or before the decision boundary;
- the immediate observed-action label and neutral description;
- player intent only when it was genuinely captured before judgement;
- unknowns;
- data-quality score and warnings; and
- definitions of the available verdict labels.

Do not show the system verdict, confidence, assessment, recommended action,
explanation, practice quest, or later outcome during Phase A. This reduces
anchoring on the system answer.

Player intent is a subjective report, not a replay fact. Label it accordingly.
If the final product does not collect intent, omit it rather than inventing an
intent or deriving one from movement.

### Phase B - System-output assessment

After the reviewer submits Phase A, show the evaluated system output:

- verdict and confidence;
- assessment;
- player-intent summary when applicable;
- referenced evidence IDs;
- alternative options and trade-offs;
- recommended action and rationale;
- execution note when present;
- next-match quest when present;
- limitations; and
- unsupported-evidence, future-information, and contradiction checks.

Do not change the reviewer's Phase A response after exposing the system output.
The later match outcome remains hidden throughout scoring.

## Information that must remain hidden

The reviewer must not receive information after `action_close_tick`, including:

- whether the player later died or survived;
- whether an opponent was later killed;
- the round winner or final score;
- the match winner;
- post-window damage, trades, utility, movement, or positioning;
- future model labels or training targets;
- retrospective commentary that reveals the result; or
- filenames, screenshots, or metadata that reveal the outcome.

If future information is accidentally exposed, mark the response contaminated
and exclude it from masked-review metrics. Retain an anonymized exclusion
record.

## Verdict definitions for reviewers

Reviewers may select more than one acceptable verdict.

| Verdict | Reviewer meaning |
| --- | --- |
| `GOOD_DECISION` | The immediate choice was well supported by the information available at the time. |
| `REASONABLE_BUT_RISKY` | The choice was defensible but carried an important avoidable or acknowledged risk. |
| `POOR_DECISION` | The available evidence supports that another immediate choice was materially better. |
| `INSUFFICIENT_EVIDENCE` | The evidence is too incomplete, uncertain, or contradictory for a responsible directional verdict. |

These labels evaluate the decision, not mechanical execution quality or the
later result. A reviewer may distinguish execution from decision quality in
their notes.

## Phase A reviewer questions

Record answers before showing the system output.

1. Which verdicts are acceptable? Select one or more.
2. Is the case too ambiguous for a directional verdict? `yes`, `no`, or
   `unsure`.
3. Should a responsible coach abstain? `yes`, `no`, or `unsure`.
4. Which immediate actions or alternatives are acceptable?
5. What material facts, if any, are missing?
6. Give a one-sentence explanation using only the displayed information.
7. Rate confidence in this judgement from 1 to 5.
8. Did any displayed information appear to reveal a later outcome?

Confidence scale:

| Score | Meaning |
| ---: | --- |
| 1 | Very uncertain; key information is absent or contradictory |
| 2 | Uncertain; a tentative judgement is possible |
| 3 | Moderate confidence; reasonable alternatives remain |
| 4 | High confidence; evidence supports a narrow acceptable set |
| 5 | Very high confidence; evidence is unusually complete and clear |

## Phase B reviewer questions

1. Is the system verdict inside your Phase A acceptable-verdict set?
2. Is the recommended action acceptable?
3. Does the assessment accurately describe the displayed facts?
4. Count clear factual errors.
5. Count claims that are not supported by displayed evidence.
6. Do all `facts_used` references resolve to evidence the reviewer can inspect?
7. Does the output mention or imply later outcome information?
8. Does the output contradict the packet or itself?
9. Was abstention appropriate or required?
10. Are the limitations honest and material?
11. Is the next-match cue specific and usable, when one is present?
12. Rate overall usefulness from 1 to 5.
13. Give one short reason for accepting or rejecting the coaching.

Usefulness scale:

| Score | Meaning |
| ---: | --- |
| 1 | Misleading, unsupported, or unusable |
| 2 | Mostly unhelpful; major correction required |
| 3 | Partly useful; important caveats or edits required |
| 4 | Useful and actionable with minor caveats |
| 5 | Clear, evidence-consistent, and immediately actionable |

## Evidence-reference audit

For each system `facts_used` ID:

1. match the ID exactly and case-sensitively;
2. confirm that it exists in the supplied case evidence;
3. confirm that its content supports the associated claim;
4. confirm that its tick respects the knowledge boundary; and
5. confirm that it is not listed as unsupported.

Do not repair, normalize, guess, or create a missing evidence record. If an
observed-action ID is supplied without a structured evidence item, record it as
not inspectable under the current review packet rather than inventing its
details.

Suggested counts per case:

- total evidence references;
- valid and inspectable references;
- missing references;
- unsupported references;
- future references;
- factual errors; and
- unsupported narrative claims.

## Ambiguity and abstention rules

Reviewers should consider `INSUFFICIENT_EVIDENCE` acceptable or required when:

- material game-state evidence is missing;
- the observed action is `UNCLASSIFIED` and the distinction matters;
- data-quality warnings undermine the judgement;
- evidence is contradictory;
- the available alternatives cannot be compared responsibly;
- intent is required for the judgement but unavailable; or
- the visible facts support several materially different interpretations.

Abstention is a valid coaching outcome, not an application failure. Do not
reward a directional answer merely for sounding confident.

## Dataset split and review order

Before tuning prompts, rules, or thresholds, assign cases to:

- 60% development;
- 20% validation; and
- 20% untouched final holdout.

Use stable case IDs and record the split. Do not move a difficult holdout case
into development after seeing its result. Run the final holdout once after the
system version is frozen.

Where practical:

- randomize case order;
- avoid showing several near-duplicate cases together;
- avoid telling reviewers the desired result;
- keep Phase A and Phase B responses separate; and
- record the exact system version evaluated.

## Optional three-condition comparison

Run this only if Person 3 can generate all conditions consistently:

1. generic narrative coaching;
2. structured evidence without the full RE:DECIDE controls; and
3. full RE:DECIDE with the available rubric, evidence links, checks, and
   abstention.

Keep the same cases across conditions. Hide condition names from reviewers when
possible and vary presentation order to reduce order effects. Do not claim a
comparative win if conditions use different cases or if the sample is too small
to interpret responsibly.

## Metrics and reporting

Report raw counts and denominators beside percentages.

### Verdict acceptability

```text
cases where system verdict is in the reviewer acceptable set
divided by
eligible reviewed cases with a system verdict
```

### Recommendation acceptability

```text
cases where the reviewer accepts the recommended action
divided by
eligible reviewed cases containing a recommendation
```

### Appropriate abstention

```text
cases where system abstention matches reviewer abstention requirement
divided by
eligible cases where abstention was assessed
```

### Valid evidence-reference rate

```text
valid and inspectable referenced evidence IDs
divided by
all referenced evidence IDs audited
```

Also report:

- factual-error count;
- unsupported-claim count;
- reviewer confidence distribution;
- usefulness-score distribution;
- number of ambiguous cases;
- number and reasons for excluded cases; and
- disagreements between reviewers.

Do not force disagreement into a false majority gold label. Report acceptable
sets and ambiguity. Do not advertise a percentage from fewer than ten cases
without placing the sample size directly beside it.

## Recording reviewer disagreements

When reviewers disagree:

- retain every original response;
- record the union and intersection of acceptable verdicts;
- identify the evidence or interpretation causing disagreement;
- mark the case ambiguous when appropriate; and
- do not ask reviewers to change an answer solely to increase agreement.

A short adjudication discussion may be recorded separately, but the original
independent judgements remain the evaluation evidence.

## Data handling

- Use aliases for players and reviewers.
- Store no contact information in the evaluation CSV.
- Keep private replay files outside Git.
- Keep later outcomes in a separate access-controlled field or file.
- Never put intent text, reviewer identity, or replay contents in public URLs.
- Commit only anonymized, consent-compatible summaries and structured results.
- Record consent outside the case data when participant identity is required.

## Suggested review session

Target 20-30 minutes per reviewer for a small batch:

1. 3 minutes - explain the knowledge boundary and verdict definitions;
2. 2 minutes - complete one unscored practice fixture;
3. 10-15 minutes - complete Phase A for the assigned cases;
4. 5-8 minutes - complete Phase B after system outputs are revealed; and
5. 2 minutes - collect overall comments and record usability problems.

Do not coach the reviewer toward a preferred verdict during the session.

## Case-preparation checklist

- [ ] Genuine case source and permission are recorded.
- [ ] Player and match identifiers are anonymized.
- [ ] Stable `case_id` and `decision_id` are present.
- [ ] System, model, rubric, and parser versions are recorded.
- [ ] Pre-decision evidence does not exceed `decision_open_tick`.
- [ ] Observed action does not use evidence beyond `action_close_tick`.
- [ ] Later outcome information is removed from the reviewer view.
- [ ] Intent is included only when genuinely captured before judgement.
- [ ] Unknowns and data-quality warnings remain visible.
- [ ] Phase A hides the system answer.
- [ ] Phase B uses the exact evaluated output without rewriting it.
- [ ] Evidence references are auditable or explicitly marked uninspectable.
- [ ] Dataset split was assigned before evaluation.

## Reviewer-session checklist

- [ ] Reviewer alias, expertise, and conflicts are recorded.
- [ ] Reviewer understands that decision quality differs from outcome.
- [ ] Reviewer understands all four verdict labels.
- [ ] Practice fixture is excluded from evaluation counts.
- [ ] Phase A is submitted before Phase B is shown.
- [ ] Later outcomes remain hidden.
- [ ] Missing facts and ambiguity can be recorded freely.
- [ ] Original responses are preserved.
- [ ] Contamination or technical failures are recorded.

## Completion criteria

The human-review activity is complete only when:

- real case and reviewer counts are recorded;
- case provenance and masking are verified;
- responses are stored in anonymized structured form;
- exclusions and disagreements are retained;
- results show raw counts and denominators;
- internal versus external reviewers are distinguished;
- no outcome-contaminated case appears in masked metrics; and
- the status, deck, and submission claims match the actual evidence.

If recruitment or case generation remains unavailable, the honest final status
is:

> The masked review protocol was prepared, but formal knowledgeable-reviewer
> evaluation was not completed within the hackathon timeline.

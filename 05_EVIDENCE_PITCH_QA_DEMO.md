# RE:DECIDE - Person 5: User Evidence, QA, Pitch Deck, and Demo

Paste this entire file into a fresh Codex or Claude session. This role includes research, evaluation, documentation, and presentation work; do not let the agent turn it into a software feature task.

## Your mission

Prove that **RE:DECIDE** solves a real problem, that its coaching is acceptably correct, and that the team can demonstrate the complete workflow in five minutes. You own the human evidence, test cases, honest metrics, narrative, slide content, demo script, submission checklist, and third-party disclosure inventory.

The challenge requires a maximum 15-slide PDF, a working end-to-end source-code repository with setup/architecture/prompts/disclosures, and a maximum five-minute demo video. Judging weights are Problem-Solution Fit 40%, Build Quality 30%, and Originality 30%.

## Product thesis

**RE:DECIDE: "Don't replay the match. Replay the decision."**

Existing post-match tools often report outcomes and statistics. RE:DECIDE focuses on the decision boundary: it reconstructs what a Counter-Strike 2 player could know when first damage contact occurred, asks what they intended, evaluates the immediate re-engage/reset/reload/support choice without seeing the later result, links every claim to replay evidence, and creates one practice quest for the next match.

The claim is not "AI knows the perfect move." The claim is: **structured evidence + intent + an outcome-blind rubric produces more trustworthy and actionable reflection than generic outcome-based feedback.**

## Your owned paths

```text
docs/**
data/eval/human/**
submission checklists and content drafts
```

You may suggest README text, but Person 1 owns the final root README. Do not edit teammates' code. File bugs with a decision ID, screenshot, expected behavior, actual behavior, severity, and reproduction steps.

## Day 1 research - do not overdo it

Interview at least five CS2 players and, if possible, two higher-skill players/coaches. Fifteen-minute interviews are enough. Ask behavior questions, not leading product questions:

1. Tell me about the last time you reviewed a bad round. What did you actually do?
2. How do you decide whether a death came from a bad decision or poor execution?
3. Which post-match tools do you use, and what do they fail to explain?
4. Show me a moment where stats did not tell you what to improve.
5. Would stating your intent change whether advice feels fair? Why?
6. What evidence would make you trust or reject an AI coach?

Record anonymized notes and exact short quotes only with consent. Do not invent testimonials. Summarize recurring pains and dissenting views.

## Human review protocol

You do not manually approve every future result. You validate a representative sample to learn whether the system is trustworthy.

For each decision window, give reviewers only:

- pre-decision evidence;
- the observed short action window;
- player intent if available;
- no later kill/death/win/outcome.

Ask each reviewer to mark:

- acceptable verdicts (one or more);
- acceptable alternatives (one or more);
- material facts missing;
- whether the case is too ambiguous and should abstain;
- one-sentence reasoning;
- confidence 1-5.

Prefer two or three reviewers per case. When experts disagree, do not force a fake gold label. Mark the acceptable set or ambiguous case. This becomes evidence that calibrated alternatives and abstention are needed.

## Evaluation set

Target 30 to 50 cases; minimum credible set is 20. Split before tuning:

- 60% development;
- 20% validation;
- 20% untouched final holdout.

Track in CSV/JSON without personal identifiers:

- decision ID;
- map/round alias;
- evidence completeness;
- reviewer acceptable verdict set;
- reviewer acceptable options;
- ambiguous/abstain flag;
- system version;
- factual-error count;
- unsupported-claim count;
- valid evidence-reference rate;
- model verdict acceptable yes/no;
- recommendation acceptable yes/no;
- appropriate abstention yes/no;
- latency;
- reviewer usefulness score;
- notes.

Coordinate with Person 3 to compare:

1. generic narrative prompt;
2. structured evidence only;
3. full RE:DECIDE with intent, rubric, evidence links, verification, and abstention.

Report raw counts and denominators. Never advertise a percentage from fewer than ten cases without the sample size directly beside it.

## QA test matrix

Test at minimum:

- bundled happy-path demo;
- second demo/map;
- player with no eligible contact decision;
- malformed or unsupported demo;
- missing API key;
- model timeout;
- malformed model JSON;
- model references nonexistent evidence;
- low data-quality packet;
- future/outcome field deliberately inserted;
- contradictory evidence;
- very long intent text;
- frontend refresh/back navigation;
- clean-machine setup;
- fixture fallback.

Severity:

- P0: demo cannot complete, secret exposed, false evidence presented.
- P1: major card section wrong, future leakage, common parser failure.
- P2: confusing copy/layout, uncommon recoverable error.
- P3: cosmetic.

Only P0/P1 bugs should threaten feature freeze.

## Fifteen-slide deck outline

Aim for 12-14 slides, not the maximum by habit.

1. Title: RE:DECIDE and the one-line promise.
2. Problem: outcomes and stats do not reveal decision quality.
3. User evidence: interview patterns and one consented quote.
4. Insight: a bad outcome can follow a good decision, and vice versa.
5. Product flow: demo -> knowledge boundary -> intent -> Decision Card -> quest.
6. Signature innovation: Knowledge-Boundary Decision Loop.
7. Product screen: annotated Decision Card.
8. Why AI: context-sensitive trade-offs and language, bounded by deterministic facts and rubric.
9. Architecture: parser -> evidence packet -> intent/rubric -> LLM -> validators -> UI.
10. Reliability: evidence IDs, future firewall, contradiction checks, confidence, abstention.
11. Validation method: masked expert review and three-condition comparison.
12. Results: honest metrics with sample sizes; leave placeholders until measured.
13. Impact and future loop: next-match transfer receipt; clearly label future work.
14. Scope, limitations, privacy, third parties, and why this can expand.

Do not claim automatic learning or behavior improvement unless measured across repeated matches. Describe the next-match transfer receipt as future work unless genuinely implemented and tested.

## Five-minute demo script

Target 4:20 so edits stay below five minutes.

### 0:00-0:25 - hook

"Most tools explain that you died. RE:DECIDE asks whether the choice was reasonable before anyone knew the outcome."

### 0:25-0:55 - input

Select bundled demo and player. Explain that `.dem` telemetry is parsed locally into facts; the LLM does not watch the full video or invent game state.

### 0:55-1:25 - decision boundary

Show the detected first-contact moment and knowledge-boundary timeline. Point to the future region hidden from the coach.

### 1:25-1:50 - intent

Select the player's intent and add one short note. Explain why intent affects decision quality.

### 1:50-3:05 - Decision Card

Show verdict, confidence, evidence chips, alternatives/trade-offs, limitations, and practice quest. Open one evidence reference.

### 3:05-3:35 - reveal the counterintuitive outcome

Only now reveal later outcome. Use a case where outcome and decision quality differ. State that later outcome was not in the model input.

### 3:35-4:05 - trust and architecture

Show simple architecture plus automatic evidence/future/schema checks and abstention.

### 4:05-4:20 - close

"RE:DECIDE turns one match into one decision you can recognize and change next time."

Avoid switching to code or terminal unless it directly proves the end-to-end path.

## Your seven-day plan

### Day 1

- Run interviews and collect competitor/problem evidence.
- Freeze research questions and evaluation sheet.
- Draft deck story without fabricated metrics.

### Day 2

- Review initial decision packets with two knowledgeable reviewers.
- Identify missing facts and ambiguous cases for Persons 2 and 3.
- Start third-party licence/API/model inventory.

### Day 3

- Build 20+ case evaluation set and execute QA matrix against fixtures.
- Draft slides 1-11 and demo script.

### Day 4

- Run the three-condition model comparison.
- Conduct five usability tests on frontend.
- File prioritized P0-P2 issues and summarize comprehension failures.

### Day 5 - freeze

- Run untouched holdout once with Person 3.
- Fill results slide honestly.
- Finalize deck content, architecture diagram, README contributions, and disclosure table.

### Day 6

- Conduct two timed rehearsals.
- Record the final demo with clean audio and readable resolution.
- Export slide deck to PDF and visually inspect all pages.
- Assemble submission folder.

### Day 7

- Verify links/permissions, repository collaborator, no secrets, video duration, PDF slide count, and README setup.
- Only blocker fixes.
- Upload early and preserve immutable final copies.

## Submission checklist

- PDF deck is 15 slides or fewer.
- Video is 5:00 or shorter and shows the complete working flow.
- Repository is private if required and includes the Garena collaborator.
- README includes setup, architecture, prompts/agent configuration, models, APIs, libraries, datasets, licences, limitations, privacy, and exception handling.
- `.env.example` contains placeholders only.
- Repository history and frontend bundles contain no secret.
- Google Drive folder name matches team name.
- All Drive links work in a logged-out/incognito check where appropriate.
- Nothing is modified after submission.

## Definition of done

- At least five user interviews and two knowledgeable reviewers, or explicit disclosure if recruitment falls short.
- Minimum 20 masked review cases with held-out split.
- Metrics have denominators and no unsupported claims.
- P0/P1 test paths are closed or clearly mitigated.
- Deck, demo, README contributions, disclosures, and submission checklist are complete one day early.

## How to work with the AI assistant

Use the assistant to structure interview notes, create the evaluation template, identify contradictions, draft concise slide copy, check the narrative against judging criteria, and rehearse hostile judge questions. Do not ask it to invent research, quotes, metrics, screenshots, or legal conclusions. Keep placeholders visibly marked until real evidence exists.


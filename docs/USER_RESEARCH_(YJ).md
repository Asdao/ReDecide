# RE:DECIDE Secondary User and Market Research

Last updated: 2026-08-05 (Asia/Singapore)

Owner: YJ (Person 5 - User Evidence, QA, Pitch Deck, and Demo)

Status: Initial secondary-research draft for team review

## Executive summary

Public product material shows an established CS2 improvement ecosystem built
around match statistics, performance benchmarks, demo viewers, clips, training
modes, and manual review. Leetify publicly emphasizes match reports and
benchmark-based aim, utility, and positioning ratings. SCOPE.GG emphasizes
detailed statistics, mistake identification, progress tracking, clips, map
performance, and a 2D demo viewer. Refrag emphasizes practice routines,
training modes, and demo review.

Research on outcome bias provides a relevant general foundation for
RE:DECIDE's outcome-blind design: people can evaluate the same decision more
favorably when told it produced a successful outcome. A large preregistered
replication reported the same direction of effect in medical decision
scenarios. This evidence is not CS2-specific, but it supports testing whether
post-match coaching should separate information available at the decision from
what happened later.

NIST's explainable-AI guidance also supports an evidence-bounded design. Its
four principles call for an explanation, an explanation meaningful to the
recipient, an explanation that accurately reflects the process, and operation
within the system's knowledge limits. This does not prove that explanations
automatically create trust. For RE:DECIDE, evidence references, limitations,
confidence, and abstention should be treated as controls to be evaluated, not
as proof that the coaching is trustworthy.

The resulting opportunity is a **product hypothesis**, not a validated market
claim: a player may benefit from a compact review of one decision that
distinguishes decision quality from outcome, exposes the supporting replay
facts, and gives one actionable next-match cue. Direct user interviews and
formal human review have not yet been completed.

## Research questions

1. What kinds of post-match improvement support do public CS2 products offer?
2. What does public community discussion suggest about statistics and manual
   demo review?
3. Is there research support for separating decision quality from outcome?
4. What principles are relevant when presenting AI-generated coaching?
5. Which parts of RE:DECIDE's proposed value remain unvalidated?

## Method

This is a rapid secondary-research review conducted on 2026-08-05. It uses:

- official public product pages and documentation for competitor capabilities;
- peer-reviewed or primary institutional material for outcome bias and
  explainable AI; and
- a small number of public Reddit discussions as anecdotal community signals.

No account-only competitor functionality was tested. No competitor was given a
full hands-on evaluation. Search-result absence was not treated as proof that a
feature does not exist. Public marketing claims, including user counts and
performance claims, were not independently verified.

No personal interviews, survey responses, or formal usability sessions are
included. Reddit posts are self-selected public comments and are not a
representative sample of CS2 players. They are used only to identify questions
for later validation.

## Finding 1 - Existing products provide extensive performance feedback

### Leetify

Leetify's public material describes automatic match reports and quantitative
ratings. Its CS2 benchmark documentation explains that aim statistics are
compared with player benchmarks and that similar principles apply to utility
and positioning ratings. It also lists Leetify Rating, ADR, K/D, and other
statistics and describes color-coded performance bands.

Evidence:

- [Leetify: Updated Benchmarks for CS2](https://leetify.com/blog/cs2-benchmarks/)
- [Leetify: CS2 rating update](https://leetify.com/blog/leetify-rating-update/)

What can be claimed:

> Existing CS2 analytics products provide automated match reports and
> benchmarked performance metrics across areas such as aim, utility, and
> positioning.

What cannot be concluded from these pages:

- that statistics are insufficient for every player;
- that Leetify lacks all decision-level analysis;
- that RE:DECIDE is more accurate or more useful; or
- that Leetify users would switch products.

### SCOPE.GG

SCOPE.GG's public page describes detailed performance statistics, map
performance, mistake identification, clips, progress tracking, and a 2D demo
viewer. Its FAQ lists measures including ADR, K/D, KAST, accuracy, first-bullet
accuracy, time to kill, and grenade use.

Evidence:

- [SCOPE.GG official product page](https://scope.gg/)

What can be claimed:

> CS2 players can already access detailed statistics and replay-oriented tools
> outside the game's ordinary scoreboard.

What cannot be concluded from this page:

- that the published user counts are independently verified;
- that its mistake-identification advice is equivalent to or different from
  RE:DECIDE's proposed decision evaluation; or
- that users distrust its results.

### Refrag

Refrag's public documentation describes a CS2 training platform with practice
modes, professional or community routines, an Academy, and a 2D demo viewer.
This makes it an adjacent training and review product rather than evidence of
an unmet market by itself.

Evidence:

- [Refrag official wiki](https://wiki.refrag.gg/en/home)
- [Refrag 2D Demo Viewer](https://wiki.refrag.gg/en/2d-demo-viewer)

What can be claimed:

> The CS2 improvement ecosystem includes both post-match review tools and
> dedicated practice environments.

## Finding 2 - Public discussions suggest a translation problem worth testing

Several public discussions show players asking how to turn statistics or demos
into improvement. Examples include:

- a player who reported a mismatch between Leetify aim/positioning ratings and
  perceived match performance, then asked for demo-review advice;
- a player asking how to improve game sense despite an average aim rating, with
  replies requesting a demo to diagnose movement and decision-making; and
- a discussion advising that statistics be treated as a general guide rather
  than a complete representation of decision-making.

Evidence:

- [Reddit: Looking to improve / Demo review](https://www.reddit.com/r/LearnCSGO/comments/18f4ftt/)
- [Reddit: Improve game sense](https://www.reddit.com/r/LearnCSGO/comments/1h5oof7/)
- [Reddit: What helped you improve the most in CS?](https://www.reddit.com/r/counterstrike2/comments/1tt5qwi/)
- [Reddit: How to do demo review?](https://www.reddit.com/r/GlobalOffensive/comments/uhi1vy/)

These posts are anecdotal and must not be converted into prevalence claims.
They support a research question, not a market statistic:

> Can a bounded, evidence-linked explanation help a player translate replay
> data into one understandable decision lesson with less review effort?

This question still requires direct user testing.

## Finding 3 - Outcome knowledge can distort decision evaluation

Baron and Hershey's 1988 experiments introduced evidence that people evaluated
the quality of decision-making more favorably when the described outcome was
favorable, even when outcome information should not determine the quality of
the original reasoning.

A 2023 preregistered replication and extension used a larger online sample and
reported the same direction of outcome bias in medical decision scenarios. The
replication is particularly useful because it addresses the small sample in the
original first experiment, although it still does not study esports.

Evidence:

- [Baron and Hershey (1988), Outcome Bias in Decision Evaluation](https://bear.warrington.ufl.edu/brenner/mar7588/Papers/baron-hershey-jpsp1988.pdf)
- [Aiyer et al. (2023), preregistered replication and extension](https://rips-irsp.com/articles/10.5334/irsp.751)

Supported product rationale:

> Later success or failure can bias evaluation of an earlier decision. It is
> therefore reasonable to test an outcome-blind coaching design that judges a
> choice using only information available at the decision boundary.

Limitations:

- The cited experiments use medical and monetary decision scenarios, not CS2.
- They support the general risk of outcome bias, not the accuracy of
  RE:DECIDE's detector, rubric, model, or recommendations.
- The product must still demonstrate that it actually excludes future
  information from model inputs and decision selection.

## Finding 4 - Explanations need evidence and knowledge limits

NIST's Four Principles of Explainable Artificial Intelligence describes four
high-level expectations:

1. provide evidence or reasons for an output;
2. make the explanation meaningful to the intended recipient;
3. ensure the explanation accurately reflects the system's process; and
4. operate only within the system's designed conditions and knowledge limits.

Evidence:

- [NISTIR 8312: Four Principles of Explainable Artificial Intelligence](https://www.nist.gov/publications/four-principles-explainable-artificial-intelligence)
- [NIST AI Risk Management Framework 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10)

Application to RE:DECIDE:

| NIST principle | Possible RE:DECIDE control | Verification still required |
| --- | --- | --- |
| Explanation | Link coaching claims to replay evidence | Confirm final response exposes resolvable evidence |
| Meaningful | Use concise CS2 language and one actionable cue | Run comprehension/usability testing |
| Explanation accuracy | Keep replay facts deterministic and separate from model prose | Test unsupported references and contradictions |
| Knowledge limits | Show unknowns, confidence, limitations, and abstention | Test low-quality and incomplete cases |

The existence of an explanation does not establish appropriate trust. The team
must still test whether explanations help users identify correct advice and
reject unsupported advice. The deck should therefore say "designed for
inspectability" or "evidence-bounded," not "proven trustworthy," unless human
evaluation supports the stronger claim.

## Competitor and workflow comparison

This table compares public positioning, not every account-only capability.

| Product or workflow | Publicly described strengths | Relevant observation | Research limitation |
| --- | --- | --- | --- |
| Leetify | Automatic match reports; benchmarked aim, utility, positioning, ADR, K/D, and ratings | Strong quantitative performance framing | Full paid/account experience not tested |
| SCOPE.GG | Detailed statistics, mistake summaries, map performance, clips, progress, and 2D demo viewer | Combines metrics and replay-oriented review | Advice behavior not tested hands-on |
| Refrag | Practice modes, routines, Academy content, and 2D demo viewer | Strong training and deliberate-practice orientation | Not evaluated as a direct analytics substitute |
| Manual demo review | Flexible contextual inspection of a full match | Potentially rich but requires time and review skill | Evidence here is anecdotal community discussion |
| RE:DECIDE hypothesis | One outcome-blind decision, bounded evidence, concise coaching, and a next-match cue | Attempts to reduce review scope and separate choice from outcome | Usefulness, accuracy, and differentiation are not yet validated |

## Product opportunity hypothesis

RE:DECIDE should not position itself as another general statistics dashboard or
full-match viewer. Its proposed focus is narrower:

1. select one supported post-contact decision;
2. freeze what was knowable at that moment;
3. separate the immediate action from later outcomes;
4. present evidence and uncertainty alongside coaching; and
5. offer one cue the player can recognize in a future match.

This may complement existing tools rather than replace them. Statistics can
identify broad patterns, demo viewers can support detailed review, training
tools can support practice, and RE:DECIDE can test a focused decision-reflection
workflow.

## Claims matrix for the pitch deck

| Proposed claim | Evidence strength | Safe wording |
| --- | --- | --- |
| CS2 players have access to detailed third-party analytics and demo tools | Strong for product availability | "Existing tools provide extensive statistics, match reports, and replay or training workflows." |
| Outcome knowledge can bias evaluation of decision quality | Strong general research; not CS2-specific | "Decision research shows later outcomes can distort evaluation, motivating an outcome-blind design." |
| Players find statistics difficult to translate into improvement | Exploratory public anecdotes only | "Public discussions suggest a translation problem worth testing." |
| Evidence-linked explanations make RE:DECIDE trustworthy | Not established | "RE:DECIDE is designed to make its coaching inspectable and bounded." |
| RE:DECIDE improves player performance | No evidence | Do not claim; label as future longitudinal validation. |
| Players prefer RE:DECIDE over existing tools | No evidence | Do not claim. |
| RE:DECIDE coaching is acceptably correct | Pending human review | Report only after reviewed cases with counts and denominators. |

## Implications for the product and demo

- Lead with the distinction between decision quality and outcome, supported by
  the outcome-bias research.
- Present existing analytics and demo tools respectfully; RE:DECIDE is a
  focused complementary workflow, not proof that other tools fail.
- Demonstrate the knowledge boundary using the exact final implementation.
- Show evidence, limitations, and abstention only when those controls are
  present and verified in the demo build.
- Do not include player intent, a complete Decision Card, evidence expansion,
  or a practice quest in the recorded flow unless they are implemented.
- Describe results with exact sample sizes and denominators.

## Limitations and unanswered questions

- No direct user interviews were conducted.
- No formal survey or representative sample was collected.
- No full hands-on competitor audit was conducted.
- Public Reddit discussions are anecdotal and self-selected.
- Outcome-bias research cited here is not esports-specific.
- The preferred review duration and acceptable coaching latency are unknown.
- User comprehension of the knowledge boundary has not been measured.
- Willingness to upload a replay and trust the processing model is unknown.
- The value of collecting player intent is not validated.
- Coaching correctness and appropriate abstention have not been human-reviewed.

## Recommended validation after the hackathon

1. Interview at least five players across different skill levels.
2. Observe how they currently use statistics and demo review.
3. Compare statistics-only feedback with RE:DECIDE on the same decisions.
4. Ask knowledgeable reviewers to assess masked cases without later outcomes.
5. Measure comprehension, perceived usefulness, appropriate reliance, and time
   to identify one actionable lesson.
6. Test whether the practice cue is recognized in a later match before claiming
   behavior improvement.

## Source register

All sources were accessed on 2026-08-05.

| ID | Source | Type | Used for |
| --- | --- | --- | --- |
| S1 | [Leetify CS2 benchmarks](https://leetify.com/blog/cs2-benchmarks/) | Official product material | Ratings, benchmarks, match-report framing |
| S2 | [Leetify rating update](https://leetify.com/blog/leetify-rating-update/) | Official product material | CS2 performance-rating context |
| S3 | [SCOPE.GG](https://scope.gg/) | Official product material | Statistics, progress, clips, and demo viewer |
| S4 | [Refrag wiki](https://wiki.refrag.gg/en/home) | Official documentation | Training platform and routines |
| S5 | [Refrag 2D Demo Viewer](https://wiki.refrag.gg/en/2d-demo-viewer) | Official documentation | Demo-review capability |
| S6 | [Baron and Hershey (1988)](https://bear.warrington.ufl.edu/brenner/mar7588/Papers/baron-hershey-jpsp1988.pdf) | Peer-reviewed research | Outcome-bias foundation |
| S7 | [Aiyer et al. (2023)](https://rips-irsp.com/articles/10.5334/irsp.751) | Preregistered peer-reviewed replication | Outcome-bias replication |
| S8 | [NISTIR 8312](https://www.nist.gov/publications/four-principles-explainable-artificial-intelligence) | Primary institutional guidance | Explainability principles |
| S9 | [NIST AI RMF 1.0](https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10) | Primary institutional guidance | Trustworthiness and evaluation context |
| S10 | [Reddit demo-review discussion](https://www.reddit.com/r/LearnCSGO/comments/18f4ftt/) | Anecdotal public discussion | Stats-to-improvement research question |
| S11 | [Reddit game-sense discussion](https://www.reddit.com/r/LearnCSGO/comments/1h5oof7/) | Anecdotal public discussion | Decision-making and demo-review question |
| S12 | [Reddit improvement discussion](https://www.reddit.com/r/counterstrike2/comments/1tt5qwi/) | Anecdotal public discussion | Limits of treating statistics as complete feedback |
| S13 | [Reddit demo-review workflow discussion](https://www.reddit.com/r/GlobalOffensive/comments/uhi1vy/) | Anecdotal public discussion | Manual review effort and uncertainty |

# RE:DECIDE - Person 4: Frontend, Product Experience, and Demo UI

Paste this entire file into a fresh Codex or Claude coding session opened at the shared repository root.

## Your mission

Build the complete user-facing experience for **RE:DECIDE**, an outcome-blind Counter-Strike 2 decision coach. Your frontend must make the originality visible in under sixty seconds: knowledge boundary, player intent, evidence-linked reasoning, multiple defensible options, and a transferable practice quest.

You are not building the replay parser or deciding coaching logic. Work from checked-in JSON fixtures on Day 1, then connect to Person 1's API without changing its contract.

## Product promise

**"Don't replay the match. Replay the decision."**

The user uploads or selects a CS2 demo, selects a player, sees one post-contact decision, states what they were trying to do, and receives a Decision Card. The product must never feel like a generic chatbot or a wall of match statistics.

## Your owned paths

```text
frontend/**
frontend tests and assets
```

Do not edit backend code. If the API is unavailable, use the shared fixtures through a typed local mock adapter. Keep mock and live modes visually identical.

## The four-screen experience

### 1. Landing / choose match

Show:

- one-sentence problem and product promise;
- `Try a sample match` as the primary path;
- `.dem` upload as a secondary path;
- small privacy message: replay is processed for analysis and no API key is exposed in the browser.

For the recorded demo, the sample path should take one click and never rely on a file picker.

### 2. Analysis progress

Show truthful stages, not fake AI theatre:

- Parse replay events.
- Find a post-contact decision.
- Freeze what was knowable.
- Compare action with stated intent.
- Verify evidence and limitations.

If the synchronous API takes time, animate these labels while waiting without claiming a completed stage the backend has not confirmed. Include a clear timeout/retry message.

### 3. Intent checkpoint

Before revealing the judgement, show the timestamp, neutral event summary, and ask:

**"What were you trying to achieve here?"**

Options:

- Take the duel.
- Create space.
- Help a teammate.
- Escape/reset.
- I am not sure.

Allow an optional one-sentence note. Explain that intent changes what a good decision means. Do not show the later outcome.

### 4. Decision Card

Visually prioritize:

1. Verdict and calibrated confidence.
2. "What you knew" evidence chips.
3. "What you chose" neutral action summary.
4. Assessment relative to stated intent.
5. Two or three alternative options and trade-offs.
6. One next-match quest with cue, action, and success check.
7. Unknowns and limitations.

Every factual claim or evidence chip must expose evidence ID, timestamp/tick, source, and exact statement. Use a drawer, popover, or expanded row. Never hide limitations in tiny text.

## Signature visual: the knowledge boundary

Create one compact timeline:

```text
known evidence  | decision opens | observed action | hidden future
----------------|----------------|-----------------|/////////////
```

Label the right side **"hidden from the coach"**. This single visual communicates why the system is different from outcome-based VOD review. It can use a real timestamp but must not reveal death/win until an optional demo-only reveal after the card.

## Design direction

- Dark, restrained competitive-game aesthetic; avoid copying CS2 official branding.
- One warm accent for the decision point, green only for verified evidence, amber for uncertainty, red only for errors or genuinely poor decisions.
- Readable typography and strong spacing; no dense dashboard grid.
- Desktop-first at 1440x900, but functional at common laptop width.
- Motion should clarify state transitions, not decorate.
- Use aliases for player names in screenshots unless consented.

## Required states

Implement from fixtures before live integration:

- normal card;
- `REASONABLE_BUT_RISKY` card;
- `INSUFFICIENT_EVIDENCE` card;
- parser/upload error;
- API timeout/model failure;
- empty/no eligible decision;
- fallback sample selection;
- loading state;
- keyboard focus and readable contrast.

The abstention screen is a feature, not an error. Explain which facts are missing and offer another decision/sample.

## API contract

Consume only:

- `GET /api/health`
- `GET /api/samples`
- `POST /api/analyze`
- optionally `POST /api/analyze-json` for fixture/fallback testing.

Generate or hand-write strict TypeScript types matching Person 1's `DecisionPacket`, `IntentInput`, and `DecisionCard`. Do not use `any` at the API boundary. Display only values in the response; do not invent missing facts in the browser.

## Demo resilience

Build three selectable run modes controlled by environment/configuration, not secret UI hacks:

1. `live`: real parser and real model.
2. `sample`: bundled demo through the real path.
3. `fixture`: checked-in packet/card for rehearsal or catastrophic recovery.

The recorded submission should use the genuine end-to-end sample path. The fixture is insurance and testing support, not evidence of AI behavior.

Add a small internal-only demo control if necessary to reset the flow. Do not expose model API keys or backend secrets to frontend bundles.

## Your seven-day plan

### Day 1

- Scaffold frontend and theme.
- Render full four-screen flow from typed fixtures.
- Agree API types and error shapes with Person 1.
- Put the knowledge-boundary timeline on screen.

### Day 2

- Connect samples and fixture analysis endpoint.
- Implement intent checkpoint and card.
- Add evidence expansion and limitations.

### Day 3

- Connect real `/api/analyze`.
- Implement loading, timeout, retry, abstention, and no-decision states.
- Complete one browser-based end-to-end flow.

### Day 4

- Run five usability tests with Person 5.
- Measure whether users can answer: what happened, why the judgement was made, what was hidden, and what to try next.
- Fix the top three comprehension failures.

### Day 5 - freeze

- No new screens.
- Polish typography, spacing, responsive behavior, errors, and demo reset.
- Capture clean screenshots for deck.

### Days 6-7

- Support video recording and live rehearsal.
- Fix blockers only; preserve the frozen demo path.

## Acceptance criteria

- A first-time viewer understands the product difference in under one minute.
- Complete sample flow takes at most five user actions before analysis.
- Intent is collected before judgement.
- Knowledge-boundary visual clearly marks hidden future.
- Evidence claims are inspectable and map to real evidence IDs.
- Unknowns and abstention are visible and understandable.
- Live, sample, and fixture paths are tested.
- No secret is present in browser code or network responses.
- No horizontal overflow or clipped content at demo resolution.

## Do not build

No login, profile, match history, leaderboard, social feed, 3D map, embedded full VOD player, live game overlay, mobile app, or conversational chat. If time remains, improve comprehension and reliability rather than adding pages.

## How to work with the coding agent

Inspect existing frontend conventions and shared fixtures first. Create a short plan and implement only `frontend/**`. Use reusable components, but do not invent a design system. Keep a typed mock adapter so progress never depends on backend availability. Test the exact recorded-demo route every day.


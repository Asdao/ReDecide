# RE:DECIDE - Person 1: Team Lead, Platform, and Integration

Paste this entire file into a fresh Codex or Claude coding session opened at the shared repository root.

## Your mission

You are the integration owner for a seven-day hackathon build. Create the skeleton, freeze the interfaces, connect all four teammates' work, keep the main branch runnable, and own the final end-to-end path.

The product is **RE:DECIDE for Counter-Strike 2**: an outcome-blind decision coach that analyzes a CS2 demo, finds a post-contact reset decision, reconstructs only what the player could know, asks what the player intended, and produces one evidence-linked Decision Card plus one cue-based practice quest.

The product promise is: **"Don't replay the match. Replay the decision."**

The narrow MVP decision family is: **after first damage contact, should the player immediately re-engage, reset/reposition, reload, or wait for support?**

## What winning means

The challenge scores Problem-Solution Fit 40%, Build Quality 30%, and Originality 30%. A working vertical slice is worth more than broad features. By the end, the judges must be able to watch this exact flow:

1. Select a bundled CS2 `.dem` sample or upload one.
2. Select the player POV/name.
3. The system extracts a post-contact decision window.
4. The user selects their intent and may add one sentence.
5. The AI returns a Decision Card with timestamped facts, a calibrated verdict, alternatives and trade-offs, limitations, and one next-match quest.
6. Every factual claim opens or highlights its evidence.
7. If evidence is insufficient, the product says so instead of bluffing.

## Non-negotiable scope

Build one excellent decision card for one game and one decision family. Do not build live coaching, multi-game support, accounts, social features, payments, a vector database, model training, or automatic video analysis.

Use parsed CS2 demo telemetry, not full-match video. The LLM must never parse a raw `.dem` file. It receives a small, validated JSON packet.

## Recommended stack

- Backend: Python 3.11+, FastAPI, Pydantic.
- Replay parsing: Awpy or another actively maintained CS2 demo parser selected by Person 2 after a same-day spike.
- Frontend: Next.js with TypeScript and Tailwind, owned by Person 4.
- LLM: one provider API behind an adapter, owned by Person 3.
- Storage: local files/in-memory only. SQLite is optional only if already working.
- Deployment: local demo is acceptable. Add Docker only after the native setup works.

Important: ChatGPT Pro and Claude Pro are not to be assumed to include API usage for an application. Confirm access to one model API on Day 1. Never commit keys. Provide `.env.example`. Keep a deterministic `DEMO_MODE=1` fallback response for rehearsals, visibly labelled in internal documentation; the judged AI path must genuinely call the model.

## Repository ownership

Create this structure and do not let teammates edit outside their owned areas without asking:

```text
backend/
  app/
    main.py                 # You own
    contracts.py            # You own; freeze early
    orchestration.py        # You own
    replay/                  # Person 2 owns
    coach/                   # Person 3 owns
  tests/
frontend/                    # Person 4 owns
data/
  samples/                   # Person 2 owns
  eval/                      # Persons 3 and 5 coordinate
docs/                        # Person 5 owns
.env.example                # You own
README.md                   # You own final version
```

Set branch names:

- `lead/integration`
- `data/replay-pipeline`
- `ai/coach-reliability`
- `ux/decision-card`
- `story/evidence-demo`

Require small commits and daily merges. Do not wait until Day 6 to combine branches.

## Freeze this contract on Day 1

You own the exact Pydantic/TypeScript versions, but preserve these semantics.

### `DecisionPacket` - created by replay pipeline, consumed by coach

```json
{
  "schema_version": "1.0",
  "decision_id": "match-round-player-tick",
  "match_id": "string",
  "map": "de_mirage",
  "round_number": 7,
  "player": "PlayerName",
  "decision_type": "POST_CONTACT_RESET",
  "decision_open_tick": 12345,
  "decision_open_seconds": 96.45,
  "action_close_tick": 12665,
  "known_before_decision": [
    {
      "evidence_id": "E1",
      "tick": 12345,
      "category": "health",
      "statement": "Player had 34 HP at first damage contact",
      "value": 34,
      "source": "demo_parser"
    }
  ],
  "observed_action": {
    "label": "IMMEDIATE_REENGAGE",
    "description": "Player exposed again 0.9 seconds after contact",
    "evidence_ids": ["E4", "E5"]
  },
  "unknowns": [
    "Exact enemy intention is unknowable",
    "Voice communications are unavailable"
  ],
  "data_quality": {
    "score": 0.86,
    "warnings": []
  }
}
```

Hard rule: `known_before_decision` may contain only information available at or before `decision_open_tick`. `observed_action` may use the short action window ending at `action_close_tick`. Nothing after `action_close_tick` may be sent to the coaching model.

### `IntentInput` - created by frontend

```json
{
  "tag": "TAKE_DUEL | CREATE_SPACE | HELP_TEAMMATE | ESCAPE | UNKNOWN",
  "text": "I thought the enemy was reloading"
}
```

### `DecisionCard` - created by coach, displayed by frontend

```json
{
  "schema_version": "1.0",
  "decision_id": "string",
  "title": "The second peek was the real decision",
  "verdict": "GOOD_DECISION | REASONABLE_BUT_RISKY | POOR_DECISION | INSUFFICIENT_EVIDENCE",
  "confidence": 0.0,
  "assessment": "short explanation",
  "player_intent_summary": "short summary",
  "facts_used": ["E1", "E4", "E5"],
  "options": [
    {
      "action": "Reset behind cover",
      "tradeoff": "Gives up immediate pressure but preserves a low-HP rifle",
      "when_best": "When no teammate can trade the repeat peek"
    }
  ],
  "recommended_action": "Reset behind cover",
  "why": "evidence-linked explanation",
  "execution_note": "optional mechanical observation or null",
  "next_match_quest": {
    "cue": "After taking first contact below 50 HP",
    "action": "Break line of sight for two seconds before deciding to re-peek",
    "success_check": "You reset before the second exposure"
  },
  "limitations": ["No voice communications available"],
  "checks": {
    "unsupported_evidence_ids": [],
    "future_information_detected": false,
    "contradiction_detected": false
  }
}
```

## Minimal API

Implement and document only these endpoints unless a concrete need appears:

- `GET /api/health`
- `GET /api/samples` - sample ID, map, player options, description.
- `POST /api/analyze` - accepts sample ID or `.dem`, player, intent tag, and intent text; returns a `DecisionCard`. A synchronous request with progress animation is acceptable for the prototype.
- `POST /api/analyze-json` - accepts a saved `DecisionPacket`; critical fallback for integration and live demo reliability.

The frontend must be able to work against one checked-in fixture before the real parser and LLM are ready.

## Your seven-day execution plan

### Day 1 - contract and walking skeleton

- Initialize repository, branches, setup commands, linting, and `.env.example`.
- Add contracts and checked-in request/response fixtures.
- Make `/api/analyze-json` return a fixture card through a stub adapter.
- Give Person 2 and Person 3 contract tests they must pass.
- Get the frontend to render the fixture by end of day.

### Day 2 - first real vertical slice

- Integrate Person 2's first parser output for one known demo.
- Integrate Person 3's first real model call.
- Confirm one sample travels from backend to Decision Card.
- Record latency and every failure manually.

### Day 3 - complete happy path

- Integrate player selection, intent input, evidence expansion, and abstention.
- Add clear errors for parser failure, unsupported demo, no candidate decision, missing API key, timeout, and invalid model output.
- Confirm setup works on a second teammate's machine.

### Day 4 - reliability and evidence

- Run Person 5's test set through the full system.
- Fix contract mismatches and high-frequency failures only.
- Add logging with decision ID, stage, latency, and failure type; never log API keys.

### Day 5 - feature freeze

- No new features after noon.
- Tag `demo-candidate-1`.
- Make native setup one command for frontend and one for backend, or provide a single launcher.
- Create a clean-machine rehearsal checklist.

### Day 6 - rehearsal and submission candidate

- Support the 5-minute demo recording.
- Test live path, bundled fallback sample, and `analyze-json` recovery path.
- Freeze prompt/model/version and sample demo.
- Tag `submission-candidate`.

### Day 7 - final QA and submission

- Only blocker fixes.
- Confirm repository has no secrets and lists all third-party components/licences.
- Verify private-repository collaborator and Drive permissions.
- Target final upload by 20:00 SGT on 8 August, not the last minute on 9 August.

## Integration gates

Every evening, require these demonstrations:

- Day 1: fixture packet renders in the browser.
- Day 2: real parser output reaches a real model call.
- Day 3: complete path works for one bundled demo.
- Day 4: at least ten reviewed cases run without unsupported factual claims.
- Day 5: clean-machine setup and full rehearsal.
- Day 6: final video captured and submission package complete.

## Acceptance criteria

- One command or documented two-command local start.
- One reliable bundled sample, one secondary sample, and JSON fixture fallback.
- No raw demo or future information reaches the LLM.
- All model output is schema-validated.
- Every `facts_used` ID exists in the packet.
- Invalid or weak evidence produces `INSUFFICIENT_EVIDENCE`.
- No API keys or player personal data are committed.
- README covers setup, architecture, prompts/models/APIs, third-party disclosures, limitations, and fallback behavior.

## How to work with the coding agent

First inspect the repository and report conflicts with this brief. Then create a short plan and implement only your owned files. Run tests after each milestone. Do not silently change the frozen contract: propose the smallest migration and notify all owners. Prefer boring, testable code over framework expansion. Keep the main branch demoable every day.


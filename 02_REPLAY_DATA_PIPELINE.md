# RE:DECIDE - Person 2: CS2 Replay Data and Decision Detection

Paste this entire file into a fresh Codex or Claude coding session opened at the shared repository root.

## Your mission

Own the deterministic truth layer. Convert a Counter-Strike 2 `.dem` replay into a compact, evidence-linked `DecisionPacket` for exactly one coaching question: after first damage contact, did the player immediately re-engage, reset/reposition, reload, or wait for support?

You are not building the AI coach or the user interface. Your output must be factual enough that another component can reason without inventing game state.

## Product context

The product is **RE:DECIDE**: "Don't replay the match. Replay the decision." It is outcome-blind. The model may see what was knowable at the decision moment and what action the player took during a short action window, but not what happened afterward.

The key technical novelty is the **Knowledge-Boundary Decision Loop**:

1. Detect a decision opportunity without judging it by whether the player later won or died.
2. Freeze known state at first contact.
3. Observe the player's immediate action for a short fixed window.
4. Remove all later events before sending the packet to the coach.

## Your owned paths

```text
backend/app/replay/**
data/samples/**
backend/tests/test_replay_*.py
```

Do not edit `backend/app/contracts.py`; Person 1 owns it. Import and satisfy the contract. If it is missing, work against the semantic schema below and give the lead a patch proposal.

## Day 1 spike - make the risky decision early

Time-box parser selection to three hours. Try the current maintained Python-friendly CS2 parser route first, such as Awpy. Confirm with a real CS2 demo that you can obtain, at minimum:

- ticks and round boundaries;
- player identities and sides;
- damage events;
- HP, armor, ammo, weapon where available;
- positions for the target and teammates;
- fire/reload events if available;
- kills only for internal debugging, never model evidence after cutoff.

If the preferred parser fails on the team's sample after three hours, switch to a maintained alternative or use its CLI/JSON output through a narrow adapter. Do not spend the week repairing a replay library. Preserve the adapter interface so the parser can be swapped.

By end of Day 1, produce a capability matrix with `reliable`, `approximate`, or `unavailable` for each fact. Never manufacture an unavailable fact.

## Fixed decision-window definition

Use this MVP definition unless evidence forces one documented adjustment:

- `decision_open_tick`: the tick where the target player first takes or deals player damage in an engagement after at least five seconds without player damage involving that target.
- `known_before_decision`: state at or before `decision_open_tick` only.
- `action_close_tick`: approximately 2.5 seconds after `decision_open_tick`, converted using actual demo tick rate.
- `observed_action`: classify what the target does between open and close.
- No event after `action_close_tick` may enter the packet.

Do not select only decisions followed by death. That leaks outcome into which examples the product shows. Rank candidates by evidence completeness, clear action classification, and whether the player had at least two plausible choices—not later outcome.

## Observed-action labels

Use deterministic rules and expose their evidence. Start with:

- `IMMEDIATE_REENGAGE`: renewed shot or renewed exposure/contact shortly after first contact without a meaningful reset.
- `RESET_REPOSITION`: meaningful movement away from the contact position or line of fire before renewed contact.
- `RELOAD_EXPOSED`: reload begins before a safe reset, when reload events are reliable.
- `HOLD_FOR_SUPPORT`: player stays in/near cover without renewed exposure while teammate support approaches or remains close.
- `UNCLASSIFIED`: evidence cannot support a stable label.

Keep thresholds in one documented configuration file. If line-of-sight or cover cannot be computed reliably in time, do not pretend it can. Use measurable proxies such as displacement, time until next shot, ammo change, and teammate distance, and label the limitation.

## Evidence policy

Every fact must be atomic and traceable:

```json
{
  "evidence_id": "E3",
  "tick": 12345,
  "category": "ammo",
  "statement": "Player had 7 rounds in the magazine at first contact",
  "value": 7,
  "source": "demo_parser"
}
```

Allowed categories include health, armor, ammo, weapon, position, displacement, teammate distance, teammate alive count, recent damage, recent shot, reload, and timing. Phrase statements conservatively. "Nearest teammate was 8.2 metres away" is acceptable if calculable. "Teammate could trade" is an inference and belongs to the coach, not the truth layer.

Maintain explicit `unknowns`, including unavailable voice communication, player attention, exact intent, and any uncertain visibility calculation.

## Required packet semantics

Your output must match the lead's `DecisionPacket` contract:

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
  "known_before_decision": [],
  "observed_action": {
    "label": "IMMEDIATE_REENGAGE",
    "description": "Player fired again 0.9 seconds after contact",
    "evidence_ids": []
  },
  "unknowns": [],
  "data_quality": {
    "score": 0.86,
    "warnings": []
  }
}
```

## Privacy and licensing

- Use team-owned, consented, or clearly permissible demo files.
- Store only the minimum samples needed for evaluation.
- Replace public player names with aliases in screenshots and fixtures unless consented.
- Record parser name, version, licence, and source URL for Person 5.
- Do not download datasets of uncertain licence.

## Your seven-day plan

### Day 1

- Select parser and prove it on one demo.
- Obtain two legal sample demos and identify target players.
- Produce one hand-inspected JSON packet manually if necessary so other teammates can proceed.
- Send capability matrix and parser risks to Person 1.

### Day 2

- Implement parser adapter and normalized event timeline.
- Detect candidate first-contact windows.
- Export at least three packets from one demo.
- Add a CLI/debug report that prints the candidate timestamp and all evidence.

### Day 3

- Implement action classification and evidence IDs.
- Add data-quality score and warnings.
- Integrate with `/api/analyze` through Person 1's adapter.
- Compare five windows against manual replay viewing.

### Day 4

- Run on a second demo and different map if possible.
- Fix only systematic extraction errors.
- Give Person 5 ten to twenty candidate packets for masked review.

### Day 5 - freeze

- Freeze thresholds and sample demos.
- Add regression fixtures and leakage tests.
- Document known limitations and average parse time.

### Days 6-7

- Support rehearsals and blocker fixes only.
- Ensure the bundled sample produces the same decision ID and evidence on a clean machine.

## Tests you must provide

- Every `facts_used` candidate evidence ID is unique.
- No `known_before_decision.tick` exceeds `decision_open_tick`.
- No observed-action evidence tick exceeds `action_close_tick`.
- Packet does not contain kill/death/winner/outcome fields.
- Round and player selection are stable for bundled sample.
- Missing fields create warnings or `UNCLASSIFIED`, not guessed values.
- Two runs over the same file produce the same packet.
- Invalid/unsupported demos return a clear typed error.

Create a leakage test that recursively inspects serialized packets for forbidden keys such as `death`, `winner`, `round_winner`, `later_damage`, and post-window ticks.

## Definition of done

- One bundled sample reliably yields at least one high-quality decision packet.
- A second sample demonstrates the parser is not hard-coded.
- Ten manually inspected windows have no known false factual statements in the displayed evidence.
- Candidate selection does not depend on later death/win.
- Parse latency and limitations are documented.
- Person 3 can run the coach entirely from your saved JSON fixture.

## How to work with the coding agent

Inspect existing contracts and tests first. Make a short plan, then implement only your owned paths. Use the smallest reliable parser adapter. Run a real sample early. Never ask the LLM to compensate for missing telemetry. When uncertain, emit an unknown or abstain; correctness is more persuasive than breadth.


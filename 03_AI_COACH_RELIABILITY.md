# RE:DECIDE - Person 3: AI Coach, Rubric, and Reliability

Paste this entire file into a fresh Codex or Claude coding session opened at the shared repository root.

## Your mission

Build the reasoning layer that turns a deterministic `DecisionPacket` plus player-stated intent into a useful, evidence-linked `DecisionCard`. You also own the guardrails that prevent unsupported claims, future-information leakage, malformed output, and false certainty.

You are not training a model from scratch. Use a strong pretrained LLM through an API, give it a narrow CS2 coaching rubric, require structured output, and validate every factual reference in code.

## Product context

**RE:DECIDE** is an outcome-blind Counter-Strike 2 decision gym. It does not say "you died, therefore your choice was bad." It assesses a post-contact choice using only what was knowable at the decision boundary, the action taken during a short window, and the player's retrospectively reported intent.

The one MVP question is: after first damage contact, should this player immediately re-engage, reset/reposition, reload, or wait for support?

## Your owned paths

```text
backend/app/coach/**
backend/tests/test_coach_*.py
data/eval/model/**
```

Coordinate with Person 5 on labels. Do not edit the shared contract directly; propose changes to Person 1.

## Model and API rule

Implement one primary provider behind a tiny adapter with model name in configuration. Do not build a multi-agent system. One model call plus deterministic verification is sufficient; a second repair call is allowed only for invalid JSON, with a strict retry cap.

ChatGPT Pro and Claude Pro web subscriptions must not be assumed to provide application API credits. Confirm one API key and a small spend limit on Day 1. Never commit the key. Provide a deterministic fixture mode for integration and rehearsals, while preserving a genuine model path for judging.

## Coaching rubric

Put the rubric in a versioned text/YAML file, not scattered prompt strings. It should enforce these principles:

1. Separate **decision quality**, **execution quality**, and **eventual outcome**.
2. Never use or infer information after `action_close_tick`.
3. Judge whether the action was reasonable given HP, ammo, timing, support, recent contact, position proxies, and stated intent.
4. Present multiple defensible options and their trade-offs when the state is ambiguous.
5. Do not claim an alternative would have guaranteed a win.
6. Treat missing voice comms, uncertain visibility, and inferred enemy state as limitations.
7. If evidence cannot support the judgement, return `INSUFFICIENT_EVIDENCE`.
8. The practice quest must be observable and binary enough to attempt next match.

Suggested verdict meanings:

- `GOOD_DECISION`: evidence and intent support the choice even if execution/outcome may have failed.
- `REASONABLE_BUT_RISKY`: defensible choice with a clear risk or a safer alternative.
- `POOR_DECISION`: available evidence strongly conflicts with the stated intent or basic reset principles.
- `INSUFFICIENT_EVIDENCE`: material facts are absent or contradictory.

## Input boundary

The prompt may receive only:

- the serialized `DecisionPacket`;
- the user's `IntentInput`;
- the versioned rubric;
- at most two reviewed few-shot examples with the same schema.

It may not receive the raw demo, match winner, later kills/deaths/damage, a full event log, or an internet search. The parser establishes facts; the LLM applies and explains the rubric.

## Required output

Return the lead's `DecisionCard` schema exactly, including:

- calibrated verdict and confidence;
- short assessment;
- summary of player intent;
- `facts_used` containing only existing evidence IDs;
- two or three alternatives with trade-offs;
- one recommendation without certainty theatre;
- optional execution note kept separate from decision judgement;
- one cue/action/success-check practice quest;
- limitations;
- deterministic check fields added after validation.

Do not let the model fill `checks`; your code computes them.

## Deterministic validators

Run validation after every model response:

1. **Schema check**: required fields, enums, lengths, ranges.
2. **Evidence check**: every ID in `facts_used` and option/reason references exists in the input.
3. **Future-information check**: input packet already passes Person 2's cutoff test; additionally reject forbidden outcome language and any unknown timestamp.
4. **Contradiction check**: flag direct contradictions such as calling ammo low when the cited fact is high, or saying no teammate was nearby when cited distance is close. Implement only reliable, explicit checks.
5. **Confidence gate**: cap confidence when `data_quality.score` is low or material unknowns exist.
6. **Abstention gate**: convert to `INSUFFICIENT_EVIDENCE` when required evidence is missing or checks fail after one repair attempt.

Do not create a validator that merely asks the same LLM if it was correct. Code should verify identities, timestamps, forbidden terms, ranges, and simple contradictions. Human evaluation verifies coaching judgement.

## Evaluation plan

You are validating the system, not manually approving every future match.

Use 30 to 50 masked decision windows if time permits; minimum credible set is 20. Person 5 will obtain human reviews. Keep development and held-out cases separate:

- Development: 60% - inspect errors and improve rubric/parser.
- Validation: 20% - choose thresholds and prompt version.
- Final holdout: 20% - run once after freeze; do not tune on it.

Compare three conditions on the same cases:

1. Generic LLM prompt with narrative event text.
2. Structured evidence packet plus basic prompt.
3. Full RE:DECIDE system: intent, rubric, evidence references, validators, and abstention.

Score:

- factual precision;
- unsupported-claim rate;
- future-information leakage;
- expert acceptability of verdict/recommendation;
- evidence citation validity;
- appropriate abstention;
- usefulness rated by players/coaches;
- latency and token/cost per card.

Do not claim 95% accuracy unless the data supports it. Report sample size and confidence honestly. For subjective cases, measure whether the answer falls within the reviewers' acceptable options rather than forcing a fake single truth.

## Your seven-day plan

### Day 1

- Confirm API access and make one structured-output call from a saved fixture.
- Draft rubric v0.1 with a CS2-knowledgeable teammate or coach.
- Provide a deterministic fixture card so frontend integration proceeds.

### Day 2

- Implement provider adapter, prompt assembly, schema parsing, timeouts, and one repair retry.
- Implement evidence-ID and forbidden-field checks.
- Generate cards for five saved packets.

### Day 3

- Integrate intent and practice quest.
- Implement confidence/abstention logic and basic contradiction rules.
- Freeze the first prompt version for evaluation.

### Day 4

- Run the three-condition comparison with Person 5's labels.
- Categorize every error as parser fact, missing evidence, rubric judgement, model compliance, or validator failure.
- Fix the correct layer; do not randomly rephrase prompts case by case.

### Day 5 - freeze

- Select model, temperature, prompt/rubric version, thresholds, and examples.
- Run the untouched holdout once.
- Export honest metrics and anonymized examples for deck/demo.

### Days 6-7

- Support clean-machine and demo rehearsals.
- No prompt changes after final video unless fixing a blocker, because unmeasured changes invalidate evaluation claims.

## Acceptance criteria

- Valid card from at least 95% of well-formed fixture packets; the rest fail safely.
- Zero non-existent evidence IDs in accepted cards.
- Zero known post-window fields in model input.
- Unsupported/outcome claims are blocked or converted to limitations.
- Low-quality packets abstain.
- Prompt, rubric, model, parameters, examples, and third-party API are documented.
- Evaluation results include denominators and examples of failure, not just a headline score.

## Demonstration examples to preserve

Include at least one case where the player dies later but the decision is judged reasonable, and one where the player survives/wins but the decision is judged risky. The model must not see those outcomes; they are revealed only afterward in the demo to prove the point.

## How to work with the coding agent

Inspect the shared schema and fixtures first. Plan briefly, implement only owned paths, and run tests after each validator. Do not train or fine-tune a model. Do not let prompt wording hide weak data. When output is wrong, classify the failure before changing anything: parser facts go to Person 2, rubric/expert policy goes here, schema/integration goes to Person 1, and ambiguous cases should abstain.


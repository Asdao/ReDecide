---
name: analyze-cs2-round
description: Runs or explains a CS2 replay using approved tools. Use for first-damage coaching, tactical round analysis, legal-action explanations, or policy comparisons.
---

# Analyze a CS2 round

1. For a replay, call `analyze_replay` once with the supplied `.dem`, `.json`, or `.jsonl` path. It analyzes every player; use `player_id` and `decision_id` to narrow a follow-up explanation.
2. Treat `decision_candidates[].contact_tick` as the first-damage coaching anchor. Do not select only kills or deaths: successful resets and surviving engagements are also valid decisions. If `summary.analysis_available` is false, say that the replay had no damage stream and abstain from coaching.
3. Use `simulate_round` for one bounded scenario and seed.
4. Use `inspect_legal_actions` only when a simulator state is supplied, and `compare_policies` only for a small seeded comparison.
5. Base claims on returned events, ticks, observed actions, and estimator values; do not invent hidden state or future outcomes. The report is outcome-blind by design.
6. Write a complete sentence for each coaching point. Name the player, identify the decision window and observed action, explain the evidence, and state one concrete alternative. Never emit placeholder fragments such as `xxxx` or a bare action label.
7. Distinguish replay facts and model inference from real professional CS2 advice. Use uncertainty when the estimator is unavailable or weak.

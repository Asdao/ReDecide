---
name: analyze-cs2-round
description: Runs and explains a seeded CS2 simulation using approved tools. Use for tactical round analysis, legal-action explanations, or policy comparisons.
---

# Analyze a CS2 round

1. Use `simulate_round` for one bounded scenario and seed.
2. Use `inspect_legal_actions` only when a simulator state is supplied.
3. Use `compare_policies` for a small seeded comparison, never an unbounded batch.
4. Base claims on returned events and metrics; do not invent hidden state.
5. Distinguish simulator behavior from real professional CS2 advice.

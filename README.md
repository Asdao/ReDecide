# RE:DECIDE

> **Don't replay the match. Replay the decision.**

RE:DECIDE is a Counter-Strike 2 replay coach. A player uploads a `.dem`
match, chooses who to review, and receives focused feedback on post-contact
decisions, especially whether to reset or re-engage after taking damage.

## How it works

```text
.dem upload -> replay parsing -> player selection -> decision and win-chance analysis
            -> coaching advice -> interactive radar and timeline
```

## Main parts

| Part | Purpose | Software |
|---|---|---|
| Frontend | Uploads replays and shows the radar, timeline, players, events, and advice | Next.js, React, TypeScript, Tailwind CSS, Zod |
| Unified backend | Connects upload, analysis, player selection, coaching, and results | Python, FastAPI, Pydantic, Uvicorn |
| Replay parser | Turns CS2 `.dem` telemetry into structured match events | Python, Awpy |
| Replay model | Estimates win chances and produces decision signals | LightGBM, Python |
| LLM agent harness | Turns safe replay evidence into readable coaching | Node.js, TypeScript, Pi SDK, configured model provider |
| Contracts and reliability | Validates data, preserves the evidence cutoff, and keeps outputs consistent | Pydantic, deterministic checks |
| Runtime data | Stores temporary replay, analysis, and visualization files | Local JSON files under `data/runtime/` |

The trained replay model supplies probabilities and decision signals. The LLM
is an explanation layer; it does not parse the replay or replace the evidence
checks.

## Project guides

- [Setup and run guide](docs/README.md)
- [Current product state](docs/CURRENT_STATE.md)

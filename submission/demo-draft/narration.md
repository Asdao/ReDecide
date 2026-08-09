# RE:DECIDE submission demo narration

Target duration: **4:20**. Hard limit: **4:59**.

## 0:00-0:20 — The problem and promise

In Counter-Strike, replaying a whole match rarely tells a player what to do differently at the moment that mattered. RE:DECIDE turns a CS2 demo into focused decision coaching. Our promise is simple: **don’t replay the match; replay the decision.**

## 0:20-0:45 — Start with a real replay

I can explore a prepared example immediately, or upload a native `.dem` from my own match. For this demo, I’ll upload a real replay. The file goes to our FastAPI backend, where the replay is parsed once into structured telemetry. The browser is not sending video frames to an AI model.

## 0:45-1:05 — Choose the player

The parser returns the players found in the match, so I can choose whose decisions to review. I’ll select this player and start the analysis. RE:DECIDE detects first-damage contact moments for that player and spreads the selected moments across the match instead of always choosing the earliest event.

## 1:05-1:25 — Explain the pipeline while it runs

There are three clear responsibilities. The replay engine establishes facts from telemetry. The value model estimates how the round state changes. The coach turns bounded evidence into useful advice. The language model never parses the demo and does not decide which replay facts are valid.

## 1:25-2:05 — Replay viewer and timeline

Here is the result. The radar reconstructs player movement, and the timeline lets me move through the round. Damage and death events are visible as replay markers, while analyzed first-contact decisions are highlighted as coaching moments. The win-chance strip shows the latest model estimate available at this point in the round. It is a signal about the game state, not proof that one player made a good or bad decision.

## 2:05-2:35 — Inspect one decision

I’ll jump to an analyzed contact. Instead of searching through the entire match, I’m taken directly to the moment where damage first changed the decision. The coaching panel explains a practical adjustment for the immediate response: whether to reset, reposition, use utility, wait for support, or re-engage. The recommendation is tied to parser-owned evidence rather than a generic match summary.

## 2:35-3:15 — Add player intent

Telemetry can show what happened, but it cannot know what the player intended. Here I can add that missing human context: “I wanted to get information and fall back.” The backend resolves the exact player and exact decision, interprets the tactical goal, and returns contextual coaching for this moment. The model chooses only from a bounded set of adjustments and evidence references; the backend validates those references and renders the factual wording shown to the player.

## 3:15-3:45 — Reliability and knowledge boundary

The key safeguard is the knowledge cutoff. Coaching may use the state at contact and the immediate reaction window, but not a later death, the round winner, or the final match result. Missing details such as line of sight, voice communication, or enemy intent remain unknown. If the provider fails or returns unsupported claims, the backend rejects the response instead of inventing coaching.

## 3:45-4:08 — Architecture and prototype boundaries

The product is a Next.js and TypeScript frontend connected to a FastAPI and Pydantic backend. Awpy parses CS2 telemetry, LightGBM provides the replay-value estimates, and a configurable language-model provider supplies bounded coaching choices. Local uploads work without Vercel Blob; Blob storage is an optional hosted deployment path.

## 4:08-4:20 — Closing

RE:DECIDE combines machine-readable replay evidence with the player’s own intent to make review faster, more specific, and more accountable. **Don’t replay the match. Replay the decision.**

## Shortened lines if the recording runs long

Cut these in order:

1. At 0:45, remove “instead of always choosing the earliest event.”
2. At 1:05, remove the first sentence.
3. At 3:45, remove the sentence about Vercel Blob.
4. At 4:08, say only: “RE:DECIDE makes replay review faster, specific, and accountable. Don’t replay the match. Replay the decision.”

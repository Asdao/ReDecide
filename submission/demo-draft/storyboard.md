# RE:DECIDE submission demo storyboard

Target duration: **4:20**. Record at 1920×1080, 30 fps. Keep the cursor deliberate and large enough to follow.

| Time | Screen and action | What the viewer must understand |
|---|---|---|
| 0:00-0:20 | Clean title card, then product landing page. Show the line “Don’t replay the match. Replay the decision.” | Product name, game, and narrow value proposition. |
| 0:20-0:45 | Show both entry choices. Choose upload, select a genuine `.dem`, and submit. Keep the filename non-sensitive. | The product accepts native telemetry, not full video. |
| 0:45-1:05 | On the prepared replay screen, briefly point to map, rounds, players found, and the player picker. Select one player and start analysis. | Parsing discovers players before player-specific coaching begins. |
| 1:05-1:25 | Stay on the progress screen. Add three small editor labels in post: “Parser → facts”, “Value model → estimates”, “Coach → bounded advice”. | The components have separate responsibilities. |
| 1:25-1:45 | Result screen: let radar playback run for several seconds. Move the timeline and switch round once. | The viewer is interactive and reconstructs the match from telemetry. |
| 1:45-2:05 | Point to damage/death markers, an analysis marker, and the win-chance strip. Do not imply that every replay marker has coaching. | Markers and analyzed decisions are different; win chance is an estimate. |
| 2:05-2:35 | Click one analyzed first-contact marker. Pause on the coaching panel and the matching replay moment. | The user jumps to one decision rather than reviewing the whole match. |
| 2:35-2:48 | Focus the intent input. Type: “I wanted to get information and fall back.” | The player contributes information telemetry cannot establish. |
| 2:48-3:15 | Submit once. Show the returned coaching long enough to read the first recommendation. If structured evidence fields are not visible in the UI, do not claim that they are displayed; say they are validated by the backend. | Intent changes the coaching for the exact selected decision. |
| 3:15-3:45 | Keep the result on screen. Add a simple editor overlay: “Uses: contact + immediate reaction” and “Excludes: later death, round result, match result”. Briefly show a safe error/abstention card only if one already exists and can be reproduced reliably. | Future information is excluded and unsafe provider output fails closed. |
| 3:45-4:08 | Show a compact architecture slide: Next.js UI → FastAPI/Pydantic → Awpy replay facts + LightGBM estimates → bounded LLM coaching. Label Vercel Blob “optional hosted storage”. | The implementation is a working vertical slice with clear boundaries. |
| 4:08-4:20 | Return to the strongest replay/coaching frame, then end card with product name and promise. | Memorable close. |

## Required on-screen proof

- A real `.dem` filename being selected.
- A successful upload/preparation state with discovered players.
- Player selection followed by analysis.
- Radar playback and round/timeline navigation.
- Damage or death replay markers and at least one analyzed decision marker.
- A visible win-chance estimate, described only as an estimate.
- One coaching recommendation at an analyzed first-contact moment.
- One intent submission for that exact moment and its returned coaching.
- A concise knowledge-cutoff explanation.
- A clear architecture view and honest limitations.

## Truthfulness guardrails

- Do not say that every damage/death marker is analyzed.
- Do not call win probability a decision verdict or ground truth.
- Do not claim that static bundled processed replays support live intent.
- Do not claim line of sight, voice communication, enemy intent, or exact cover geometry is known.
- Do not say provider-backed coaching works without a configured provider key.
- Do not show secrets, raw authorization headers, local usernames, absolute paths, private replay IDs, or provider dashboards.
- Do not claim a deployed Blob flow was tested unless it was actually smoke-tested before recording.
- If a live request fails, record a clean second take; do not edit a failure into a success.

## Capture fallback

If live provider latency makes a single take unreliable, record the upload, parsing, player selection, radar, timeline, and saved analysis continuously. Record the intent request as a second truthful take after confirming the provider works, then join the takes with a simple cut. Do not substitute fabricated UI or claim that a static processed replay made the live request.

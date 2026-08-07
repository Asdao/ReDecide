# Current state of RE:DECIDE

## The current flow

```text
Upload .dem directly
  OR upload it to public Vercel Blob and send the URL
  -> backend parses the replay once
  -> backend returns the map and player list
  -> backend prepares replay events and win chances
  -> user chooses one player
  -> coach reviews that player's first-damage decisions
  -> frontend receives the events, win timeline, and coaching advice
```

## What works now

- FastAPI can receive a `.dem` file.
- A Vercel Blob URL endpoint is ready but switched off by default.
- The replay parser can turn it into match data.
- The backend returns a replay ID, map, rounds, and player list.
- The replay engine creates a win-chance timeline.
- The backend finds first-damage moments for each player.
- The backend can run the coach for one selected player.
- The final result contains player events, decision moments, win chances, and
  coaching advice.
- Full minimap and timeline data is saved for the frontend.

## What is not ready yet

- The frontend upload button is not connected to the backend yet.
- A real `.dem` file has not completed the full flow yet.
- A real Vercel Blob upload has not completed the full flow yet.
- The Blob URL endpoint accepts public Vercel Blob URLs only, not private ones.
- Asking about the player's intent is not implemented.
- Follow-up questions are not implemented.
- The Blob URL endpoint stays disabled until the frontend is ready.
- Live coaching uses the Python HTTP adapter by default when a provider base
  URL and API key are configured. The legacy Pi/Node path remains available
  with `REDECIDE_COACH_MODE=pi`.
- Analysis jobs disappear when the backend restarts.

## What each main folder does

- `backend/replay_api/` receives the `.dem` and saves replay data.
- `backend/replay_engine/` parses the replay and calculates win chances.
- `backend/app/` joins the replay, player selection, and coaching flow.
- `backend/app/coach/pi_connector.py` provides the Python HTTP coach by default
  when provider settings are present; `agent-harness/` remains the optional
  legacy Pi process for `REDECIDE_COACH_MODE=pi`.
- `frontend/` contains the user interface.
- `data/runtime/` stores temporary replay and analysis files while running.

## Frontend flow to build next

1. Upload the `.dem` directly to `/api/replay/upload`, or upload it to public
   Vercel Blob first.
2. For Blob uploads, send its URL and original filename to
   `/api/replay/import-url`.
3. Show the players returned by the backend.
4. Send the replay ID to `/api/analysis/prepare`.
5. Wait until preparation is ready.
6. Send the selected player ID to `/api/analysis/{analysis_id}/run`.
7. Show the returned timeline, decision moments, and advice.

The Blob route is currently off. Set `REDECIDE_BLOB_IMPORT_ENABLED=true` and
restart FastAPI only after the frontend Blob upload is ready.

Do not build the intent text box yet. The uploaded-replay backend does not
support it yet.

## Update — 2026-08-06

### The three user flows

| Flow | Current state |
|---|---|
| Upload a `.dem` | The frontend is connected to the upload and analysis APIs. The complete chain has not yet been proven with a real `.dem` and a live model provider. |
| Use a sample match | The old sample screen finds a sample and player, but stops before the replay viewer. |
| Open a processed replay | The Inferno example opens the replay viewer and includes one saved coaching result. This is the strongest demo path today. |

### What the timeline means

- For the selected player, the timeline marks damage they received and their
  deaths.
- It does not mark damage they dealt or kills they made.
- The backend may find several eligible post-contact decisions, but it
  currently uses `candidates[0]`: the earliest eligible decision for the
  selected player.
- Therefore, one analysis run produces advice for one decision. The other
  damage and death markers are replay navigation points, not separate AI
  reviews. 
- but justin thinks that this is sufficient to showcase for the hackathon?

### Where the advice appears

The frontend is designed to show advice in the replay viewer's **Moment
inspector**. For the saved Inferno example, the user selects `flameZ` and opens
the blue analysis marker. The advice appears under **What could be done
better**.

### What is verified and what is not

- The parser, replay engine, API, frontend, and agent-harness automated tests
  pass.
- A real `.dem` has not yet completed the full upload-to-viewer flow.
- A real provider call has not yet completed the full chain. Tests use fake
  provider responses, and this checkout has no configured provider key.
- Player intent and follow-up questions are not implemented.
- Replay playback, seeking, marker selection, and inspector opening still need
  a clean manual browser test before the demo.

### The trained model and the language model

The trained replay model produces probabilities and recommendation signals.
The optional live language model turns safe replay facts into readable coaching
text. These are separate parts. Initial coaching can later use a deterministic
text fallback, so the whole product does not have to fail when the provider is
unavailable. No model retraining is required for that fallback.

### Main operational gaps

- The frontend timeout and backend provider timeout are not aligned.
- Direct uploads need a configured size limit.
- Vercel Blob import is disabled and untested end to end.
- Runtime replay files need a clear expiry and cleanup policy.

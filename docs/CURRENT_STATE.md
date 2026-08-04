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
- Live coaching needs Node dependencies and a valid provider API key.
- Analysis jobs disappear when the backend restarts.

## What each main folder does

- `backend/replay_api/` receives the `.dem` and saves replay data.
- `backend/replay_engine/` parses the replay and calculates win chances.
- `backend/app/` joins the replay, player selection, and coaching flow.
- `agent-harness/` calls the language model for coaching advice.
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

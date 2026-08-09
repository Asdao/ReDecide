# RE:DECIDE demo recording checklist

## Before recording

- [ ] Use a clean working copy and record from the intended submission commit.
- [ ] Confirm the demo `.dem` is legitimate, non-sensitive, and has a short readable filename.
- [ ] Copy the root environment template to `.env`; keep the real provider key only in `.env`.
- [ ] Set `frontend/.env.local` to the local FastAPI URL and direct upload mode.
- [ ] Confirm `.env` and `.env.local` are ignored by Git.
- [ ] Close terminals, tabs, notifications, password managers, and provider dashboards that could expose secrets.
- [ ] Set the browser to 100% zoom and 1920×1080 or another 16:9 resolution.
- [ ] Use a fresh browser session or clear stale Next.js state before the final take.
- [ ] Start the product with `./scripts/start-dev.ps1` from PowerShell.
- [ ] Confirm `http://127.0.0.1:8000/api/health` returns successfully.
- [ ] Confirm the frontend loads at `http://localhost:3000`.
- [ ] Run the entire chosen `.dem` flow once before recording: upload → prepare → select player → analyze → viewer → intent.
- [ ] Confirm the chosen match produces at least one analyzed marker and a readable coaching result.
- [ ] Confirm the provider model name, URL, key, latency, and quota are working.
- [ ] Keep a bundled processed replay ready as a viewer-only fallback, while remembering that its intent composer is disabled.

## Recording order

- [ ] Start with two seconds of silence before speaking.
- [ ] Show the product promise.
- [ ] Upload the `.dem` and show discovered players.
- [ ] Select one player and run analysis.
- [ ] Show radar playback, a round change, timeline navigation, replay markers, and win chance.
- [ ] Open one analyzed first-contact decision and show its advice.
- [ ] Submit the intent: “I wanted to get information and fall back.”
- [ ] Show the returned intent coaching without exposing raw internal JSON or identifiers.
- [ ] Explain the knowledge cutoff and fail-closed behavior.
- [ ] Show the architecture slide.
- [ ] End on the RE:DECIDE promise and hold for two seconds.

## Quality and claim check

- [ ] Total duration is under 5:00; aim for 4:10-4:30.
- [ ] Narration is clear at normal speed; do not accelerate it to meet the limit.
- [ ] UI text is legible on a laptop screen.
- [ ] No loading pause longer than five seconds; trim dead time without hiding an error.
- [ ] Mouse movement is slow and purposeful.
- [ ] Audio has no clipping, fan noise, or notification sounds.
- [ ] The video distinguishes replay markers from analyzed coaching moments.
- [ ] Win chance is called an estimate, not proof of decision quality.
- [ ] Intent is described as subjective player context, not telemetry.
- [ ] The coach is not credited with parsing the `.dem` or validating its own evidence.
- [ ] No later kill, death, round result, or match result is presented as evidence for an earlier decision.
- [ ] No unverified geometry, communication, or enemy intent is claimed.
- [ ] Known prototype limits are stated briefly and confidently.

## Export and final verification

- [ ] Export as MP4 using H.264 video and AAC audio.
- [ ] Use 1920×1080, 30 fps, and a bitrate that keeps text sharp.
- [ ] Name the file `redecide-submission-demo.mp4`.
- [ ] Play the exported file from beginning to end with headphones.
- [ ] Verify duration is below 300 seconds in file properties or with `ffprobe`.
- [ ] Check the first and final frames, audio sync, cursor visibility, and every cut.
- [ ] Upload the exported file privately once and replay the uploaded copy before submission.
- [ ] Keep a local backup and the narration/storyboard beside it.

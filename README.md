# RE:DECIDE

> **Don't replay the match. Replay the decision.**

RE:DECIDE is a Counter-Strike 2 replay-coaching prototype. It parses `.dem`
telemetry, lets the user choose a player, identifies post-contact decision
moments, and presents win-chance signals and coaching in an interactive radar
and timeline.

## How it works

```text
.dem or sample -> parse replay -> choose player -> select safe decision moments
               -> generate coaching -> inspect the replay and timeline
               -> optionally explain the player's intent at one analyzed moment
```

## Main parts

| Part | What it does | Main software |
|---|---|---|
| Frontend | Upload, player selection, radar, timeline, events, and advice | Next.js, React, TypeScript, Tailwind CSS, Zod |
| Backend | Upload, preparation, player analysis, coaching, and results | Python, FastAPI, Pydantic |
| Replay engine | Parses CS2 telemetry and calculates replay/model signals | Awpy, LightGBM, Python |
| Coach | Generates baseline advice, then answers an optional intent follow-up using the exact selected decision and bounded contact/reaction evidence | Python HTTP adapter; optional Node.js Pi harness |
| Storage | Keeps replay and analysis artifacts | Local filesystem; optional Vercel Blob |

The replay pipeline selects the evidence and prevents later match information
from entering the coaching prompt. For intent follow-up, the language model
selects a bounded tactical adjustment and evidence IDs; the backend renders
the visible factual text from typed, parser-owned evidence. Feasibility and
team coordination remain explicitly unestablished until deterministic rules
can prove them. The model does not parse the `.dem`, author public replay
facts, or decide which replay facts are valid.

Intent follow-up is available for uploaded and backend-sample analyses. Bundled
processed replays have no live `analysis_id`, so their intent composer remains
disabled.

## Run locally

Requirements:

- Python 3.12+ and `uv`
- Node.js 24 and `pnpm` 11
- A provider API key only when testing live coaching

From the repository root in PowerShell:

```powershell
Copy-Item .env.example .env
@(
  'NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000'
  'NEXT_PUBLIC_REPLAY_UPLOAD_MODE=direct'
) | Set-Content frontend/.env.local
notepad .env
```

For live HTTP coaching, add the key to the root `.env`:

```text
DEEPSEEK_API_KEY=your-real-key-here
```

Then start both services:

```powershell
.\scripts\start-dev.ps1
```

Open:

- Product: `http://localhost:3000`
- Backend API: `http://127.0.0.1:8000/docs`

The launcher installs locked dependencies and creates either local environment
file if it is missing. The bundled processed-replay viewer can run without a
provider key; live coaching cannot.

### Environment files

| Location | Setting | When it is needed |
|---|---|---|
| Root `.env` | `DEEPSEEK_API_KEY` | Required only for live HTTP coaching |
| Root `.env` | `HARNESS_MODEL_BASE_URL` and `HARNESS_MODEL` | Provider endpoint and a model name supported by that provider; template values still require a live smoke test |
| Root `.env` | `REDECIDE_COACH_MODE` | Optional: blank selects automatically, `http` forces provider HTTP, and `pi` uses the legacy Node harness |
| Root `.env` | `REDECIDE_ANALYSES_PER_PLAYER` | Optional analysis quota from 1 to 10; default is 10 |
| `frontend/.env.local` | `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000` | Connects local Next.js to local FastAPI |
| `frontend/.env.local` | `NEXT_PUBLIC_REPLAY_UPLOAD_MODE=direct` | Uses direct local `.dem` upload |

Keep provider keys only in the root `.env`; never put secrets in a
`NEXT_PUBLIC_*` variable or commit a real `.env` file. Vercel Blob is not
required for the local product flow.

## Project guides

- [Detailed setup and run guide](docs/README.md)
- [Current product state](docs/CURRENT_STATE.md)
- [Dependency security](docs/DEPENDENCY_SECURITY.md)

This root README, `docs/README.md`, and `docs/CURRENT_STATE.md` are the current
project-level documentation. Component-level `API.md`, `STATUS.md`, plan, and
deployment notes are useful implementation history but may lag behind the
integrated branch.
